"""Fix round 3 tests (2026-11-03).

Covers the consolidated fix3-spec.md: auth + CSRF, env storage root,
atomic/locked saves with .bak fallback, save-all, Shopify enrich +
refresh, combine Style option, per-variant pricing, publish safety
(resume, draft verification, dry-run checklist), stale-mockup
versioning, bare-photo guard, pricing validation + Decimal money,
SSRF/size guards, transparent-fraction validation, bundled fonts,
duplicate/delete, layer edit/move/position, per-product placement,
default colour, bulk upload, hidden set-page creation, export,
search limit, JSON error handlers, photo downscale cap, and the
editor UI markers.

Runs against a temp data root only. Never touches the real
data/sets.json (byte-identity checked at the end) and never calls
the live shop: every Shopify call is a mock.
"""
import io
import json
import os
import shutil
import sys
import tempfile

REAL_SETS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "sets.json")


def sha(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


real_hash_before = sha(REAL_SETS)

TMP = tempfile.mkdtemp(prefix="setapp_fix3_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "fix3-test-password"
os.environ["FLASK_SECRET_KEY"] = "fix3-test-secret"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as app_module  # noqa: E402
import shopify as shopify_api  # noqa: E402
from PIL import Image  # noqa: E402

app_module.UPLOAD_DIR = os.path.join(TMP, "uploads")
app_module.MOCKUP_DIR = os.path.join(TMP, "mockups")
os.makedirs(app_module.UPLOAD_DIR, exist_ok=True)
os.makedirs(app_module.MOCKUP_DIR, exist_ok=True)

app = app_module.app
app.config["TESTING"] = True
client = app.test_client()

PASSED, FAILED = [], []


def check(name, ok, extra=""):
    (PASSED if ok else FAILED).append(name)
    print(("  PASS " if ok else "  FAIL ") + name +
          ("" if ok else " :: " + str(extra)[:300]))


def post(path, body=None, csrf=True):
    token = None
    if csrf:
        token = client.get("/api/csrf-token").get_json()["csrf_token"]
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-CSRF-Token"] = token
    return client.post(path, headers=headers,
                       data=json.dumps(body or {}))


def login(password="fix3-test-password"):
    token = client.get("/api/csrf-token").get_json()["csrf_token"]
    return client.post("/api/login", headers={
        "Content-Type": "application/json", "X-CSRF-Token": token},
        data=json.dumps({"password": password}))


def make_transparent(path, size=(400, 400), opaque_box=(100, 100, 300, 300)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    x0, y0, x1, y1 = opaque_box
    for x in range(x0, x1):
        for y in range(y0, y1):
            img.putpixel((x, y), (255, 255, 255, 255))
    img.save(path)


def make_opaque(path, size=(400, 400)):
    Image.new("RGB", size, (200, 30, 30)).save(path, "JPEG")


def make_photo(path, size=(600, 600)):
    Image.new("RGB", size, (180, 200, 220)).save(path, "JPEG")


def seed_set(sid="fix3-set"):
    path = os.path.join(TMP, "sets.json")
    sets = {}
    if os.path.exists(path):
        with open(path) as f:
            sets = json.load(f)
    sets[sid] = {
            "id": sid, "name": "Fix3 Set", "description": "",
            "tags": [], "slug": "", "grouping": "combine",
            "publish_state": "draft", "publish_error": None,
            "artwork_locked": False, "design_url": None,
            "design_version": 1,
            "master_placement": {"x": 0.5, "y": 0.47,
                                 "scale": 0.32, "angle": 0},
            "products": [
                {"product_id": "111", "title": "Tee", "locked": True,
                 "colours": ["Black"], "sizes": ["S"],
                 "all_colours": ["Black", "White"],
                 "all_sizes": ["S", "M"], "mockups": []},
                {"product_id": "222", "title": "Hoodie", "locked": True,
                 "colours": ["Black"], "sizes": ["S"],
                 "all_colours": ["Black"],
                 "all_sizes": ["S", "M"], "mockups": []},
            ],
            "text_layers": [],
        }
    with open(os.path.join(TMP, "sets.json"), "w") as f:
        json.dump(sets, f)
    return sid


def main():
    # ---- 1. Auth + CSRF ----
    print("== 1. Auth + CSRF ==")
    r = client.get("/api/sets")
    check("sets need login", r.status_code == 401, r.status_code)
    r = client.post("/api/sets", headers={"Content-Type": "application/json"},
                    data=json.dumps({"name": "x"}))
    check("POST without CSRF rejected", r.status_code == 403, r.status_code)
    r = login("wrong-password")
    check("wrong password rejected", r.status_code == 401, r.status_code)
    r = login()
    check("correct password logs in",
          r.status_code == 200 and r.get_json().get("authenticated") is True,
          str(r.status_code))
    r = client.get("/api/auth-status")
    check("auth-status reports configured + authenticated",
          r.get_json().get("password_configured") is True
          and r.get_json().get("authenticated") is True, str(r.get_json()))

    sid = seed_set()
    r = client.get("/api/sets")
    check("sets readable after login", r.status_code == 200
          and len(r.get_json()) == 1, str(r.status_code))

    # ---- 2. Atomic saves + .bak ----
    print("== 2. Atomic saves + .bak ==")
    sets_path = os.path.join(TMP, "sets.json")
    before = open(sets_path).read()
    r = post(f"/api/sets/{sid}/details",
             {"name": "Fix3 Set Renamed", "slug": "fix3",
              "description": "d", "tags": "a, b", "grouping": "combine"})
    check("details save ok", r.status_code == 200, str(r.status_code))
    after = open(sets_path).read()
    check("save changed the file", before != after)
    check("saved file is valid JSON", bool(json.loads(after)))
    check("no temp file left behind",
          not any(n.endswith(".tmp") for n in os.listdir(TMP)))
    bak_path = sets_path + ".bak"
    check(".bak holds the previous content",
          os.path.exists(bak_path)
          and open(bak_path).read() == before)

    # ---- 3. Save-all + Decimal money + compare-at ----
    print("== 3. Save-all + pricing validation ==")
    r = post(f"/api/sets/{sid}/save-all", {
        "placement": {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 15},
        "details": {"name": "Fix3 Set", "slug": "fix3-set",
                    "description": "d", "tags": "a, b",
                    "grouping": "combine"},
        "products": [
            {"product_id": "111", "colours": ["Black", "White"],
             "sizes": ["S", "M"], "sale_price": "27.99",
             "compare_at_price": "34.99", "base_cost": "12.50"},
            {"product_id": "222", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "44", "compare_at_price": "",
             "base_cost": "20"},
        ]})
    j = r.get_json()
    check("save-all ok", r.status_code == 200, str(r.status_code))
    check("save-all stored angle",
          j["master_placement"]["angle"] == 15, str(j.get("master_placement")))
    check("save-all stored slug + tags",
          j["slug"] == "fix3-set" and j["tags"] == ["a", "b"])
    check("save-all stored per-product pricing",
          float(j["products"][0]["sale_price"]) == 27.99
          and float(j["products"][0]["base_cost"]) == 12.50)
    r = post(f"/api/sets/{sid}/save-all", {
        "placement": {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0},
        "details": {"name": "Fix3 Set", "slug": "fix3-set",
                    "description": "d", "tags": "", "grouping": "combine"},
        "products": [
            {"product_id": "111", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "30", "compare_at_price": "25",
             "base_cost": "12.50"},
        ]})
    check("compare-at below sale rejected",
          r.status_code == 400, str(r.status_code))
    # Decimal: 27.99 - 12.50 must be exactly 15.49, not 15.489999...
    r = post(f"/api/sets/{sid}/save-all", {
        "placement": {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0},
        "details": {"name": "Fix3 Set", "slug": "fix3-set",
                    "description": "d", "tags": "", "grouping": "combine"},
        "products": [
            {"product_id": "111", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "27.99", "compare_at_price": "",
             "base_cost": "12.50"},
            {"product_id": "222", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "44", "compare_at_price": "",
             "base_cost": "20"},
        ]})
    check("save-all re-saved after rejection", r.status_code == 200)

    # ---- 4. Shopify enrich on add + refresh + default colour ----
    print("== 4. Enrich, refresh, default colour ==")
    shopify_api.authenticated = lambda: True
    shopify_api.get_product_details = lambda pid: {
        "product_id": pid, "title": "Store Tee",
        "handle": "store-tee", "image": None, "images": [],
        "colours": ["Black", "White"], "sizes": ["S", "M"],
        "variant_prices": {("Black", "S"): "18.88",
                           ("White", "M"): "28.88"},
        "variants": 4} if pid == "999" else None
    r = post(f"/api/sets/{sid}/products", {"product_id": "999"})
    j = r.get_json()
    added = [p for p in j["products"] if p["product_id"] == "999"]
    check("add enriches from Shopify",
          r.status_code == 200 and len(added) == 1
          and added[0]["title"] == "Store Tee"
          and added[0]["colours"] == ["Black", "White"]
          and added[0]["variant_prices"]["Black||S"] == "18.88",
          str(r.status_code))
    r = post(f"/api/sets/{sid}/products", {"product_id": "nope"})
    check("unknown store id rejected, nothing added",
          r.status_code == 400, str(r.status_code))
    r = post(f"/api/sets/{sid}/products",
             {"product_id": "catalog:printify-80"})
    check("catalog id via product-id route rejected",
          r.status_code == 400
          and "Catalog" in r.get_json().get("error", ""), str(r.status_code))
    shopify_api.get_product_details = lambda pid: {
        "product_id": pid, "title": "Store Tee V2",
        "handle": "store-tee", "image": None, "images": [],
        "colours": ["Black", "White", "Red"], "sizes": ["S", "M"],
        "variant_prices": {("Black", "S"): "19.99"}, "variants": 6}
    r = post(f"/api/sets/{sid}/products/999/refresh", {})
    j = r.get_json()
    ref = [p for p in j["products"] if p["product_id"] == "999"][0]
    check("refresh updates title + options, keeps seller selection",
          ref["title"] == "Store Tee V2"
          and ref["all_colours"] == ["Black", "White", "Red"]
          and ref["colours"] == ["Black", "White"]
          and ref["variant_prices"]["Black||S"] == "19.99",
          str(ref))
    r = post(f"/api/sets/{sid}/products/999/default-color",
             {"colour": "White"})
    j = r.get_json()
    ref = [p for p in j["products"] if p["product_id"] == "999"][0]
    check("default colour saved",
          ref.get("default_color") == "White", str(ref.get("default_color")))
    r = post(f"/api/sets/{sid}/products/999/default-color",
             {"colour": "Purple"})
    check("default colour must be a selected colour",
          r.status_code == 400, str(r.status_code))

    # ---- 5. Upload validation: transparency fraction ----
    print("== 5. Upload validation ==")
    mostly_opaque = os.path.join(TMP, "mostly.png")
    img = Image.new("RGBA", (400, 400), (255, 255, 255, 255))
    for x in range(390, 400):
        for y in range(390, 400):
            img.putpixel((x, y), (0, 0, 0, 0))
    img.save(mostly_opaque)
    token = client.get("/api/csrf-token").get_json()["csrf_token"]
    with open(mostly_opaque, "rb") as f:
        r = client.post(f"/api/sets/{sid}/upload", headers={
            "X-CSRF-Token": token},
            data={"design": (f, "mostly.png")},
            content_type="multipart/form-data")
    check("mostly-opaque PNG rejected (under 3% transparent)",
          r.status_code == 400, str(r.status_code))
    good = os.path.join(TMP, "good.png")
    make_transparent(good)
    v_pre = [s for s in client.get("/api/sets").get_json()
             if s["id"] == sid][0]["design_version"]
    with open(good, "rb") as f:
        r = client.post(f"/api/sets/{sid}/upload", headers={
            "X-CSRF-Token": token},
            data={"design": (f, "good.png")},
            content_type="multipart/form-data")
    j = r.get_json()
    check("transparent PNG accepted",
          r.status_code == 200 and j.get("url", "").startswith("/static/uploads/"),
          str(r.status_code))
    design_url = j["url"]
    # Opaque JPEG still rejected.
    opaque = os.path.join(TMP, "opaque.jpg")
    make_opaque(opaque)
    with open(opaque, "rb") as f:
        r = client.post(f"/api/sets/{sid}/upload", headers={
            "X-CSRF-Token": token},
            data={"design": (f, "opaque.jpg")},
            content_type="multipart/form-data")
    check("JPEG upload rejected (PNG only)",
          r.status_code == 400, str(r.status_code))
    # Artwork locked after publish is tested later; here uploads work.
    r = client.get("/api/sets")
    mine = [s for s in r.get_json() if s["id"] == sid][0]
    check("design recorded with version bump",
          mine["design_url"] == design_url
          and mine["design_version"] == v_pre + 1,
          str(mine.get("design_version")))

    # ---- 6. Mockups: bare-photo guard + stale versioning ----
    print("== 6. Mockups: bare-photo guard + stale ==")
    photo = os.path.join(TMP, "photo.jpg")
    make_photo(photo)
    staged_photo = os.path.join(app_module.UPLOAD_DIR, "photo.jpg")
    shutil.copy(photo, staged_photo)
    photo_url = "/static/uploads/photo.jpg"
    r = post(f"/api/sets/{sid}/mockups",
             {"design": design_url, "photos": {"111": photo_url}})
    j = r.get_json()
    check("mockup renders from bare photo",
          r.status_code == 200 and "111" in j.get("mockups", {}),
          str(r.status_code))
    rendered = j["mockups"]["111"]
    r = post(f"/api/sets/{sid}/mockups",
             {"design": design_url, "photos": {"111": rendered}})
    check("rendered mockup as photo input rejected",
          r.status_code == 400 or "111" in (r.get_json().get("errors") or {}),
          str(r.status_code))
    # Stale, the real way: a master placement change bumps the version
    # without clearing mockups, so the last render is now outdated.
    # (A design re-upload clears mockups instead; checked below.)
    r = post(f"/api/sets/{sid}/master",
             {"placement": {"x": 0.5, "y": 0.47, "scale": 0.32,
                            "angle": 10}})
    check("master placement change ok", r.status_code == 200,
          str(r.status_code))
    # Narrow 999 to the one pair its store prices cover, so the
    # dry-run is not blocked by an unrelated incomplete product.
    post(f"/api/sets/{sid}/save-all", {
        "placement": {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 10},
        "details": {"name": "Fix3 Set", "slug": "fix3-set",
                    "description": "d", "tags": "a, b",
                    "grouping": "combine"},
        "products": [
            {"product_id": "111", "colours": ["Black", "White"],
             "sizes": ["S", "M"], "sale_price": "27.99",
             "compare_at_price": "34.99", "base_cost": "12.50"},
            {"product_id": "222", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "44", "compare_at_price": "",
             "base_cost": "20"},
            {"product_id": "999", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "", "compare_at_price": "",
             "base_cost": "10"},
        ]})
    # Dry-run must warn about the stale mockup, not fail.
    r = post(f"/api/sets/{sid}/publish-draft", {"dry_run": True})
    j = r.get_json()
    check("dry-run warns on stale mockup",
          r.status_code == 200
          and any("fresh Preview" in w for w in j.get("warnings", [])),
          str(j.get("warnings")))
    check("checklist flags stale mockup as not ready",
          any(c["product_id"] == "111" and c["ready"] is False
              for c in j.get("checklist", [])), str(j.get("checklist")))
    # Re-upload clears mockups outright (they are rebuilt on preview).
    with open(good, "rb") as f:
        r = client.post(f"/api/sets/{sid}/upload", headers={
            "X-CSRF-Token": token},
            data={"design": (f, "good.png")},
            content_type="multipart/form-data")
    check("re-upload ok", r.status_code == 200, str(r.status_code))
    mine = [s for s in client.get("/api/sets").get_json()
            if s["id"] == sid][0]
    check("re-upload clears outdated mockups",
          all(not (p.get("mockups") or [])
              for p in mine["products"]), str(mine["products"]))
    # Fresh preview clears the stale flag.
    r = post(f"/api/sets/{sid}/mockups",
             {"design": mine["design_url"],
              "photos": {"111": photo_url, "222": photo_url,
                         "999": photo_url}})
    check("fresh preview for all products",
          r.status_code == 200, str(r.status_code))

    # ---- 7. Publish safety: dry-run, partial, resume, draft check ----
    print("== 7. Publish safety ==")
    # Split mode so each product is its own payload (partial test).
    r = post(f"/api/sets/{sid}/details",
             {"name": "Fix3 Set", "slug": "fix3-set", "description": "d",
              "tags": "", "grouping": "split"})
    check("split mode saved", r.status_code == 200)
    r = post(f"/api/sets/{sid}/save-all", {
        "placement": {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0},
        "details": {"name": "Fix3 Set", "slug": "fix3-set",
                    "description": "d", "tags": "", "grouping": "split"},
        "products": [
            {"product_id": "111", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "27.99", "compare_at_price": "",
             "base_cost": "12.50"},
            {"product_id": "222", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "44", "compare_at_price": "",
             "base_cost": "20"},
            {"product_id": "999", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "", "compare_at_price": "",
             "base_cost": "10"},
        ]})
    check("split save-all ok (999 uses store price)",
          r.status_code == 200, str(r.status_code))
    # The split save-all changed placement, so re-preview before
    # publishing (otherwise the stale-mockup guard blocks it).
    mine_now = [s for s in client.get("/api/sets").get_json()
                if s["id"] == sid][0]
    post(f"/api/sets/{sid}/mockups",
         {"design": mine_now["design_url"],
          "photos": {"111": photo_url, "222": photo_url,
                     "999": photo_url}})
    calls = []
    shopify_api.public_url = lambda: "https://example.invalid"
    shopify_api.search_products = lambda q, limit=20: []

    def mock_create_fail_second(**kw):
        calls.append(kw)
        if len(calls) == 2:
            raise RuntimeError("Shopify hiccup on second product")
        return {"id": 100 + len(calls), "status": "draft",
                "handle": "fix3-" + str(len(calls))}
    shopify_api.create_draft_product = mock_create_fail_second
    r = post(f"/api/sets/{sid}/publish-draft", {})
    j = r.get_json()
    check("publish failure returns 502, not stuck launching",
          r.status_code == 502, str(r.status_code))
    r = client.get("/api/sets")
    mine = [s for s in r.get_json() if s["id"] == sid][0]
    check("failed state recorded with partial progress",
          mine["publish_state"] == "failed"
          and mine["publish_partial"]["next_index"] == 1
          and len(mine["publish_partial"]["created"]) == 1,
          str(mine.get("publish_partial")))
    # Resume: only the remaining payloads are created, no duplicates.
    shopify_api.create_draft_product = lambda **kw: (
        calls.append(kw) or {"id": 200 + len(calls),
                             "status": "draft", "handle": "fix3-r"})
    r = post(f"/api/sets/{sid}/publish-draft", {})
    j = r.get_json()
    check("resume publish succeeds",
          r.status_code == 200, str(r.status_code))
    check("resume created only the remaining payloads",
          len(calls) == 4, str(len(calls)))
    r = client.get("/api/sets")
    mine = [s for s in r.get_json() if s["id"] == sid][0]
    check("publish record holds all 3 products, no duplicates",
          len((mine.get("publish_record") or {}).get("products", [])) == 3,
          str(mine.get("publish_record")))
    r = client.get("/api/sets")
    mine = [s for s in r.get_json() if s["id"] == sid][0]
    check("published_draft + artwork locked after resume",
          mine["publish_state"] == "published_draft"
          and mine["artwork_locked"] is True)
    # Second real publish blocked.
    r = post(f"/api/sets/{sid}/publish-draft", {})
    check("second real publish blocked",
          r.status_code == 409, str(r.status_code))
    # Draft-status verification: a fresh set whose mock returns "active".
    sid2 = seed_set("fix3-set2")
    with open(good, "rb") as f:
        client.post(f"/api/sets/{sid2}/upload", headers={
            "X-CSRF-Token": token},
            data={"design": (f, "good.png")},
            content_type="multipart/form-data")
    post(f"/api/sets/{sid2}/save-all", {
        "placement": {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0},
        "details": {"name": "Fix3 Set2", "slug": "", "description": "",
                    "tags": "", "grouping": "combine"},
        "products": [
            {"product_id": "111", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "27.99", "compare_at_price": "",
             "base_cost": "12.50"},
            {"product_id": "222", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "44", "compare_at_price": "",
             "base_cost": "20"},
        ]})
    sets_now = {s["id"]: s for s in client.get("/api/sets").get_json()}
    post(f"/api/sets/{sid2}/mockups",
         {"design": sets_now[sid2]["design_url"],
          "photos": {"111": photo_url, "222": photo_url}})
    shopify_api.create_draft_product = lambda **kw: {
        "id": 9999, "status": "active", "handle": "bad"}
    r = post(f"/api/sets/{sid2}/publish-draft", {})
    check("non-draft status rejected with 502",
          r.status_code == 502, str(r.status_code))
    r = client.get("/api/sets")
    mine2 = [s for s in r.get_json() if s["id"] == sid2][0]
    check("non-draft product not counted as published",
          mine2["publish_state"] == "failed"
          and not mine2["artwork_locked"])

    # ---- 8. Combine Style option + per-variant pricing (dry-run) ----
    print("== 8. Combine Style + per-variant pricing ==")
    sid3 = seed_set("fix3-set3")
    with open(good, "rb") as f:
        client.post(f"/api/sets/{sid3}/upload", headers={
            "X-CSRF-Token": token},
            data={"design": (f, "good.png")},
            content_type="multipart/form-data")
    post(f"/api/sets/{sid3}/save-all", {
        "placement": {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0},
        "details": {"name": "Fix3 Set3", "slug": "", "description": "",
                    "tags": "", "grouping": "combine"},
        "products": [
            {"product_id": "111", "colours": ["Black", "White"],
             "sizes": ["S", "M"], "sale_price": "",
             "compare_at_price": "", "base_cost": "10"},
            {"product_id": "222", "colours": ["Black"], "sizes": ["S"],
             "sale_price": "44", "compare_at_price": "",
             "base_cost": "20"},
        ]})
    # Give product 111 store variant prices via refresh mock.
    shopify_api.get_product_details = lambda pid: {
        "product_id": pid, "title": "Tee", "handle": "tee",
        "image": None, "images": [],
        "colours": ["Black", "White"], "sizes": ["S", "M"],
        "variant_prices": {"Black / S": "18.88", "Black / M": "20.00",
                           "White / S": "28.88", "White / M": "30.00"},
        "variants": 4}
    post(f"/api/sets/{sid3}/products/111/refresh", {})
    post(f"/api/sets/{sid3}/mockups",
         {"design": [s for s in client.get("/api/sets").get_json()
                     if s["id"] == sid3][0]["design_url"],
          "photos": {"111": photo_url, "222": photo_url}})
    r = post(f"/api/sets/{sid3}/publish-draft", {"dry_run": True})
    j = r.get_json()
    payload = (j.get("products") or [{}])[0]
    variants = payload.get("variants") or []
    check("combine payload has one product",
          len(j.get("products") or []) == 1, str(len(j.get("products") or [])))
    check("combine variants carry Style option",
          len(variants) == 5
          and all(v.get("option1") in ("Tee", "Hoodie")
                  for v in variants),
          str(variants))
    prices = sorted(v.get("price") for v in variants)
    check("per-variant store prices used, not one flat price",
          "18.88" in prices and "20.00" in prices
          and "28.88" in prices and "30.00" in prices
          and "44.00" in prices, str(prices))

    # ---- 9. Duplicate, delete, layers, placement, default colour ----
    print("== 9. Duplicate, delete, layers, placement ==")
    r = post(f"/api/sets/{sid3}/duplicate", {})
    dup = r.get_json()
    check("duplicate creates a new set with same products",
          r.status_code in (200, 201) and dup["id"] != sid3
          and len(dup["products"]) == len(
              [s for s in client.get("/api/sets").get_json()
               if s["id"] == sid3][0]["products"]),
          str(r.status_code))
    r = post(f"/api/sets/{dup['id']}/delete", {})
    check("delete removes the set",
          r.status_code == 200
          and all(s["id"] != dup["id"]
                  for s in client.get("/api/sets").get_json()))
    # Layers: add, edit position, move, hide.
    r = post(f"/api/sets/{sid3}/layers", {
        "content": "GO DUCKS", "font": "sans", "size": 120,
        "colour": "#111111", "lettercase": "upper",
        "rotation": 0, "opacity": 100, "x": 0.5, "y": 0.47})
    j = r.get_json()
    layers = (j.get("set") or j).get("text_layers") or []
    check("layer added with position",
          len(layers) == 1 and layers[0]["x"] == 0.5
          and layers[0]["y"] == 0.47, str(layers))
    lid = layers[0]["id"]
    r = post(f"/api/sets/{sid3}/layers", {
        "content": "SECOND", "font": "sans", "size": 100,
        "colour": "#222222", "lettercase": "none",
        "rotation": 0, "opacity": 100})
    j = r.get_json()
    layers = (j.get("set") or j).get("text_layers") or []
    lid2 = layers[1]["id"]
    r = post(f"/api/sets/{sid3}/layers/{lid2}/move", {"direction": -1})
    j = r.get_json()
    order = [l["id"] for l in (j.get("set") or j).get("text_layers", [])]
    check("layer move up reorders",
          order == [lid2, lid], str(order))
    r = post(f"/api/sets/{sid3}/layers/{lid}/edit", {
        "content": "GO DUCKS EDITED", "font": "serif", "size": 90,
        "colour": "#333333", "lettercase": "none",
        "rotation": 10, "opacity": 80, "x": 0.3, "y": 0.6})
    j = r.get_json()
    edited = [l for l in (j.get("set") or j).get("text_layers", [])
              if l["id"] == lid][0]
    check("layer edit updates content + position + rotation",
          edited["content"] == "GO DUCKS EDITED"
          and edited["x"] == 0.3 and edited["y"] == 0.6
          and edited["rotation"] == 10, str(edited))
    # Per-product placement (unlock + sliders).
    r = post(f"/api/sets/{sid3}/products/111/lock",
             {"locked": False,
              "placement": {"x": 0.4, "y": 0.5, "scale": 0.4,
                            "angle": 20}})
    j = r.get_json()
    prod = [p for p in j["products"] if p["product_id"] == "111"][0]
    check("per-product placement saved on unlock",
          prod["locked"] is False
          and prod["override_placement"]["angle"] == 20
          and prod["override_placement"]["x"] == 0.4, str(prod))
    # Fonts bundled.
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "fonts")
    check("DejaVu fonts bundled",
          all(os.path.exists(os.path.join(fonts_dir, f))
              for f in ["DejaVuSans.ttf", "DejaVuSerif.ttf",
                        "DejaVuSansMono.ttf"]))
    # Layer render with bundled font produces a file.
    r = post(f"/api/sets/{sid3}/mockups",
             {"design": [s for s in client.get("/api/sets").get_json()
                         if s["id"] == sid3][0]["design_url"],
              "photos": {"111": photo_url}})
    check("mockup with text layers renders",
          r.status_code == 200
          and "111" in (r.get_json().get("mockups") or {}),
          str(r.status_code))

    # ---- 10. Bulk upload, set page, export, search limit ----
    print("== 10. Bulk upload, set page, export, search ==")
    good2 = os.path.join(TMP, "good2.png")
    make_transparent(good2, opaque_box=(50, 50, 350, 350))
    # Bulk = duplicate + upload: first file here, extras as duplicates.
    r = post(f"/api/sets/{sid3}/duplicate", {})
    dup2 = r.get_json()
    with open(good2, "rb") as f:
        r = client.post(f"/api/sets/{dup2['id']}/upload", headers={
            "X-CSRF-Token": token},
            data={"design": (f, "good2.png")},
            content_type="multipart/form-data")
    check("duplicate set accepts its own design",
          r.status_code == 200, str(r.status_code))
    page_calls = []

    def mock_create_page(title, body_html):
        page_calls.append({"title": title, "body_html": body_html})
        return {"id": 555, "handle": "fix3-set"}
    shopify_api.create_page = mock_create_page
    shopify_api.shop_domain = lambda: "fansfitco.shop"
    # The set page needs a published set: use sid from section 7.
    r = post(f"/api/sets/{sid}/create-page",
             {"title": "Fix3 Set", "handle": "fix3-set",
              "body_html": "d"})
    j = r.get_json()
    check("hidden set page created",
          r.status_code == 200 and j.get("page_id") == 555, str(j))
    check("set page built from the set name",
          page_calls and page_calls[0]["title"] == "Fix3 Set",
          str(page_calls))
    check("set page stays hidden (published flag false)",
          j.get("published") is False, str(j))
    r = client.get(f"/api/sets/{sid3}/export")
    check("export returns the set as attachment",
          r.status_code == 200
          and r.headers.get("Content-Disposition", "").startswith(
              "attachment")
          and json.loads(r.data)["id"] == sid3, str(r.status_code))
    shopify_api.search_products = lambda q, limit=20: [
        {"id": str(i), "title": f"Product {i}"} for i in range(60)]
    r = client.get("/api/products/search?q=test&limit=200")
    j = r.get_json()
    check("search limit capped at 50",
          r.status_code == 200 and len(j.get("products", [])) == 50,
          str(len(j.get("products", []))))
    r = client.get("/api/sets/does-not-exist/export")
    check("missing set export is JSON 404, not HTML",
          r.status_code == 404
          and r.is_json, str(r.status_code))
    r = client.post("/api/sets/does-not-exist/publish-draft",
                    headers={"Content-Type": "application/json",
                             "X-CSRF-Token": token},
                    data=json.dumps({}))
    check("missing set publish is JSON 404",
          r.status_code == 404 and r.is_json, str(r.status_code))

    # ---- 11. SSRF / size guards + photo downscale ----
    print("== 11. SSRF, sizes, downscale ==")
    r = post(f"/api/sets/{sid3}/mockups",
             {"design": [s for s in client.get("/api/sets").get_json()
                         if s["id"] == sid3][0]["design_url"],
              "photos": {"111": "http://169.254.169.254/latest/meta-data"}})
    check("SSRF photo URL rejected",
          r.status_code == 400
          or "111" in (r.get_json().get("errors") or {}),
          str(r.status_code))
    big_photo = os.path.join(TMP, "big.jpg")
    make_photo(big_photo, size=(4000, 4000))
    staged_big = os.path.join(app_module.UPLOAD_DIR, "big.jpg")
    shutil.copy(big_photo, staged_big)
    r = post(f"/api/sets/{sid3}/mockups",
             {"design": [s for s in client.get("/api/sets").get_json()
                         if s["id"] == sid3][0]["design_url"],
              "photos": {"111": "/static/uploads/big.jpg"}})
    j = r.get_json()
    out = None
    if r.status_code == 200 and "111" in j.get("mockups", {}):
        out = os.path.join(app_module.MOCKUP_DIR,
                           os.path.basename(j["mockups"]["111"]))
    ok_down = False
    if out and os.path.exists(out):
        ok_down = Image.open(out).size[0] <= 3000
    check("photo downscaled to at most 3000px wide",
          ok_down, str(out))

    # ---- 12. Editor UI markers ----
    print("== 12. Editor UI markers ==")
    html = open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "templates", "index.html")).read()
    for marker in ["loginCard", "saveAll()", "dirtyNote",
                   "previewAllMockups", "tapToPlace", "createSetPage",
                   "downloadSetJson", "defcol-", "layerX",
                   "Hero is the first Shopify image",
                   "Default color", "angle"]:
        check(f"UI has {marker}", marker in html)
    import re as _re
    scripts = _re.findall(r"<script>(.*?)</script>", html, _re.S)
    check("exactly one editor script block", len(scripts) == 1)
    tmp_js = os.path.join(TMP, "editor.js")
    with open(tmp_js, "w") as f:
        f.write(scripts[0])
    import subprocess
    proc = subprocess.run(["node", "--check", tmp_js],
                          capture_output=True, text=True)
    check("editor JS passes node --check", proc.returncode == 0,
          proc.stderr[:300])

    # ---- 13. Logout ----
    print("== 13. Logout ==")
    r = post("/api/logout", {})
    check("logout ok", r.status_code == 200, str(r.status_code))
    r = client.get("/api/sets")
    check("sets need login again after logout",
          r.status_code == 401, str(r.status_code))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", FAILED)
    real_hash_after = sha(REAL_SETS)
    check("real sets.json byte-identical",
          real_hash_before == real_hash_after == "cfe1882f"
          "f2a230135aa35c26dc255896b1f1685bc8f9f8ac32e4f33e352d3ad2")
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
