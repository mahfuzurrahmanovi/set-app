"""Round-2 rebuild tests for the set app (2026-11-03).

Gearlaunch-layout editor + ShopBase folds: URL slug, explicit Save Draft
state, artwork spec line, product remove, mockup reorder, text layers
(add/validate/hide/delete, per-product hide, per-product design hide),
mockup compositing with layers, and round-1 regressions.

Runs against a COPY of the data dir, never the real sets.json.
Shopify is never called: only dry-run publish is used.
Run: .venv/bin/python server/rebuild2_test.py
"""

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from PIL import Image, ImageDraw  # noqa: E402

import app as app_module  # noqa: E402
import text_layers  # noqa: E402

REAL_SETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "sets.json",
)

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"  PASS {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name} {detail}")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_photo(path, size=(600, 600), colour=(180, 200, 220)):
    Image.new("RGB", size, colour).save(path, "JPEG", quality=92)


def make_design(path, size=(800, 800)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([300, 300, 500, 500], fill=(200, 30, 30, 255))
    img.save(path, "PNG")


def main():
    real_hash_before = sha(REAL_SETS)
    tmp = tempfile.mkdtemp(prefix="setapp-r2-test-")
    try:
        data_dir = os.path.join(tmp, "data")
        os.makedirs(data_dir)
        shutil.copy(REAL_SETS, os.path.join(data_dir, "sets.json"))
        app_module.DATA_FILE = os.path.join(data_dir, "sets.json")
        app_module.UPLOAD_DIR = os.path.join(tmp, "uploads")
        app_module.MOCKUP_DIR = os.path.join(tmp, "mockups")
        os.makedirs(app_module.UPLOAD_DIR, exist_ok=True)
        client = app_module.app.test_client()

        # Fix round 3: POSTs now need a CSRF token. Wrap post() so every
        # call in this file fetches the session token first.
        _raw_post = client.post

        def _post(*args, **kwargs):
            token = client.get("/api/csrf-token").get_json()["csrf_token"]
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["X-CSRF-Token"] = token
            return _raw_post(*args, headers=headers, **kwargs)

        client.post = _post

        print("== 1. Seeded Oregon set intact ==")
        r = client.get("/api/sets")
        oregon = [s for s in r.get_json()
                  if s["id"] == "oregon-ducks-set"][0]
        check("oregon 3 products", len(oregon["products"]) == 3)
        check("oregon master kept",
              oregon["master_placement"]["scale"] == 0.32)

        print("== 2. URL slug ==")
        r = client.post("/api/sets", json={"name": "R2 Set"})
        sid = r.get_json()["id"]
        r = client.post(f"/api/sets/{sid}/details",
                        json={"slug": "oregon-ducks-set"})
        check("good slug saved",
              r.status_code == 200 and r.get_json()["slug"] == "oregon-ducks-set",
              str(r.status_code))
        for bad in ("Oregon Ducks", "-lead", "trail-", "has space",
                    "UPPER", "x" * 101):
            r = client.post(f"/api/sets/{sid}/details", json={"slug": bad})
            check(f"bad slug rejected: {bad[:12]}", r.status_code == 400,
                  str(r.status_code))
        r = client.post(f"/api/sets/{sid}/details", json={"slug": ""})
        check("empty slug clears", r.status_code == 200
              and r.get_json()["slug"] == "")

        print("== 3. Save Draft state ==")
        r = client.post(f"/api/sets/{sid}/save-draft", json={})
        check("save-draft stamps time",
              r.status_code == 200 and r.get_json()["draft_saved_at"],
              str(r.get_json()))
        r = client.post(f"/api/sets/{sid}/details",
                        json={"name": "R2 Set Renamed"})
        check("details save also stamps draft time",
              bool(r.get_json()["draft_saved_at"]))

        print("== 4. Upload stores artwork spec ==")
        design = os.path.join(tmp, "design.png")
        make_design(design)
        with open(design, "rb") as fh:
            r = client.post(f"/api/sets/{sid}/upload",
                            data={"design": (fh, "design.png")},
                            content_type="multipart/form-data")
        j = r.get_json()
        check("upload ok", r.status_code == 200, str(j))
        r = client.get("/api/sets")
        mine = [s for s in r.get_json() if s["id"] == sid][0]
        check("artwork dims stored",
              mine["design_width"] == 800 and mine["design_height"] == 800
              and mine["design_dpi"] == 67, str(mine))
        check("artwork dpi estimate is 800/12",
              mine["design_dpi"] == round(800 / 12))

        print("== 5. Remove product ==")
        r = client.post(f"/api/sets/{sid}/catalog-templates",
                        json={"all": True})
        check("3 templates added", len(r.get_json()["added"]) == 3)
        pid80 = "catalog:printify-80"
        r = client.post(f"/api/sets/{sid}/products/{pid80}/remove", json={})
        check("remove works",
              r.status_code == 200 and pid80 not in
              [p["product_id"] for p in r.get_json()["products"]])
        r = client.post(f"/api/sets/{sid}/products/{pid80}/remove", json={})
        check("re-remove 404", r.status_code == 404)
        # Published-draft guard: flip state in the TEST copy only.
        with open(app_module.DATA_FILE) as f:
            sets = json.load(f)
        sets[sid]["publish_state"] = "published_draft"
        with open(app_module.DATA_FILE, "w") as f:
            json.dump(sets, f)
        r = client.post(
            f"/api/sets/{sid}/products/catalog:printify-945/remove", json={})
        check("remove blocked once published", r.status_code == 409,
              str(r.status_code))
        sets[sid]["publish_state"] = "draft"
        with open(app_module.DATA_FILE, "w") as f:
            json.dump(sets, f)

        print("== 6. Mockup reorder ==")
        # Give the remaining template a couple of mockups first.
        r = client.get("/api/sets")
        mine = [s for s in r.get_json() if s["id"] == sid][0]
        pid945 = "catalog:printify-945"
        prod = [p for p in mine["products"]
                if p["product_id"] == pid945][0]
        with open(app_module.DATA_FILE) as f:
            sets = json.load(f)
        target = [p for p in sets[sid]["products"]
                  if p["product_id"] == pid945][0]
        target["mockups"] = ["m1.jpg", "m2.jpg", "m3.jpg"]
        target["hero_image"] = "m1.jpg"
        with open(app_module.DATA_FILE, "w") as f:
            json.dump(sets, f)
        r = client.post(
            f"/api/sets/{sid}/products/{pid945}/mockups/reorder",
            json={"order": ["m3.jpg", "m1.jpg", "m2.jpg"]})
        check("reorder accepted",
              r.status_code == 200 and
              [p for p in r.get_json()["products"]
               if p["product_id"] == pid945][0]["mockups"] ==
              ["m3.jpg", "m1.jpg", "m2.jpg"], str(r.status_code))
        check("reorder keeps hero",
              [p for p in r.get_json()["products"]
               if p["product_id"] == pid945][0]["hero_image"] == "m1.jpg")
        r = client.post(
            f"/api/sets/{sid}/products/{pid945}/mockups/reorder",
            json={"order": ["m1.jpg", "m2.jpg"]})
        check("bad reorder rejected", r.status_code == 400)

        print("== 7. Text layers ==")
        layer, err = text_layers.validate_layer({
            "content": "go ducks", "font": "sans", "size": 120,
            "colour": "#C00000", "lettercase": "upper", "rotation": 0,
            "opacity": 100})
        check("lettercase upper applied",
              err is None and layer["content"] == "GO DUCKS", str(err))
        for bad_body, why in [
                ({"content": ""}, "empty content"),
                ({"content": "x", "colour": "red"}, "bad colour"),
                ({"content": "x", "size": 5}, "size too small"),
                ({"content": "x", "opacity": 101}, "opacity over 100"),
                ({"content": "x", "font": "comic"}, "bad font"),
                ({"content": "x", "rotation": 200}, "rotation out of range")]:
            _, err = text_layers.validate_layer(bad_body)
            check(f"layer validation rejects {why}", err is not None)
        r = client.post(f"/api/sets/{sid}/layers", json={
            "content": "GO DUCKS", "font": "sans", "size": 120,
            "colour": "#C00000", "lettercase": "none", "rotation": 0,
            "opacity": 100})
        check("layer added via API", r.status_code == 201, str(r.status_code))
        lid = r.get_json()["layer"]["id"]
        png = os.path.join(app_module.UPLOAD_DIR, f"text_{sid}_{lid}.png")
        check("layer PNG rendered", os.path.exists(png))
        img = Image.open(png).convert("RGBA")
        check("layer PNG has opaque text pixels",
              img.split()[3].getextrema()[1] == 255)
        r = client.post(f"/api/sets/{sid}/layers/{lid}/hide",
                        json={"hidden": True})
        check("layer eye hide",
              r.status_code == 200 and
              [l for l in r.get_json()["text_layers"]
               if l["id"] == lid][0]["hidden"] is True)
        r = client.post(f"/api/sets/{sid}/layers/{lid}/hide",
                        json={"hidden": False})
        check("layer eye show",
              [l for l in r.get_json()["text_layers"]
               if l["id"] == lid][0]["hidden"] is False)
        r = client.post(
            f"/api/sets/{sid}/products/{pid945}/layers/{lid}/hide",
            json={"hidden": True})
        check("per-product layer hide",
              r.status_code == 200 and lid in
              [p for p in r.get_json()["products"]
               if p["product_id"] == pid945][0].get("hidden_layers", []))
        r = client.post(
            f"/api/sets/{sid}/products/{pid945}/layers/{lid}/hide",
            json={"hidden": False})
        check("per-product layer show",
              lid not in
              [p for p in r.get_json()["products"]
               if p["product_id"] == pid945][0].get("hidden_layers", []))

        print("== 8. Mockups with layers + design hide ==")
        photo = os.path.join(tmp, "photo.jpg")
        make_photo(photo)
        # Fix round 3: renders only accept server-issued /static/ URLs.
        shutil.copy(design, os.path.join(app_module.UPLOAD_DIR, "design.png"))
        shutil.copy(photo, os.path.join(app_module.UPLOAD_DIR, "photo.jpg"))
        r = client.post(f"/api/sets/{sid}/mockups", json={
            "design": "/static/uploads/design.png",
            "photos": {pid945: "/static/uploads/photo.jpg"}})
        check("mockup with layers ok",
              r.status_code == 200 and pid945 in r.get_json()["mockups"],
              str(r.get_json()))
        with_layers = os.path.join(
            app_module.MOCKUP_DIR,
            os.path.basename(r.get_json()["mockups"][pid945]))
        check("mockup file exists", os.path.exists(with_layers))
        # NOTE: every render writes the same per-product path, so copy
        # this output aside before the next render overwrites it.
        with_layers_copy = os.path.join(tmp, "with_layers.jpg")
        shutil.copy(with_layers, with_layers_copy)
        with_layers = with_layers_copy
        # Hide the design on this product: output must differ and must
        # still carry the text layer (so it differs from the bare photo).
        client.post(f"/api/sets/{sid}/products/{pid945}/design-hide",
                    json={"hidden": True})
        r = client.post(f"/api/sets/{sid}/mockups", json={
            "design": "/static/uploads/design.png",
            "photos": {pid945: "/static/uploads/photo.jpg"}})
        hidden_out = os.path.join(
            app_module.MOCKUP_DIR,
            os.path.basename(r.get_json()["mockups"][pid945]))
        a = Image.open(with_layers).convert("RGB")
        b = Image.open(hidden_out).convert("RGB")
        check("design-hide changes the mockup",
              list(a.getdata()) != list(b.getdata()))
        # Hide the text layer globally too: now output must equal the
        # bare photo (design hidden + no visible layers).
        client.post(f"/api/sets/{sid}/layers/{lid}/hide",
                    json={"hidden": True})
        r = client.post(f"/api/sets/{sid}/mockups", json={
            "design": "/static/uploads/design.png",
            "photos": {pid945: "/static/uploads/photo.jpg"}})
        bare_out = os.path.join(
            app_module.MOCKUP_DIR,
            os.path.basename(r.get_json()["mockups"][pid945]))
        c = Image.open(bare_out).convert("RGB")
        orig = Image.open(photo).convert("RGB")
        check("design hidden + layers hidden = bare photo",
              list(c.getdata()) == list(orig.getdata()))
        client.post(f"/api/sets/{sid}/products/{pid945}/design-hide",
                    json={"hidden": False})
        client.post(f"/api/sets/{sid}/layers/{lid}/hide",
                    json={"hidden": False})
        r = client.post(f"/api/sets/{sid}/design/remove", json={})
        check("design remove clears server-side",
              r.status_code == 200 and r.get_json()["design_url"] is None
              and r.get_json()["design_width"] is None, str(r.status_code))
        r = client.post(f"/api/sets/{sid}/layers/{lid}/delete", json={})
        check("global layer delete",
              r.status_code == 200 and
              all(l["id"] != lid for l in r.get_json()["text_layers"]))
        check("deleted layer PNG removed", not os.path.exists(png))

        print("== 9. Publish guards still work (regression) ==")
        for pid in ("catalog:printify-945", "catalog:printify-48"):
            client.post(f"/api/sets/{sid}/products/{pid}/pricing",
                        json={"sale_price": 10, "base_cost": 12})
        # Section 8 removed the design, so re-upload it first: without
        # a design the dry-run is (correctly) blocked by the design
        # guard, which would mask the profit point being tested.
        with open(design, "rb") as fh:
            r = client.post(f"/api/sets/{sid}/upload",
                            data={"design": (fh, "design.png")},
                            content_type="multipart/form-data")
        check("design re-uploaded for guard test",
              r.status_code == 200, str(r.status_code))
        r = client.post(f"/api/sets/{sid}/publish-draft",
                        json={"dry_run": True})
        # Gearlaunch flow (2026-11-03): profit removed, Shopify owns
        # profit, so a price below base cost no longer blocks.
        check("price below base cost does NOT block dry-run",
              r.status_code == 200 and r.get_json().get("dry_run") is True,
              str(r.status_code) + str(r.get_json())[:200])
        r = client.get("/api/sets")
        mine = [s for s in r.get_json() if s["id"] == sid][0]
        check("api shape extended not narrowed",
              "slug" in mine and "text_layers" in mine
              and "draft_saved_at" in mine
              and mine["master_placement"]["scale"] == 0.5)

        print("== 10. Editor JS syntax ==")
        html = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "server", "templates", "index.html")).read()
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        check("exactly one script block", len(scripts) == 1)
        tmp_js = os.path.join(tmp, "editor.js")
        with open(tmp_js, "w") as f:
            f.write(scripts[0])
        proc = subprocess.run(["node", "--check", tmp_js],
                              capture_output=True, text=True)
        check("editor JS passes node --check", proc.returncode == 0,
              proc.stderr[:300])
        check("editor HTML has Gearlaunch markers",
              all(m in html for m in
                  ["placeBox", "detailSlug", "saveDraft", "FRONT",
                   "Default color", "Add products"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    real_hash_after = sha(REAL_SETS)
    check("real sets.json byte-identical",
          real_hash_before == real_hash_after == "cfe1882f"
          "f2a230135aa35c26dc255896b1f1685bc8f9f8ac32e4f33e352d3ad2")

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    main()
