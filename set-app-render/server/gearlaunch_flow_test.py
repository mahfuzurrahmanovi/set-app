"""Gearlaunch-style flow tests (2026-11-03).

Covers gearlaunch-flow-plan.md: campaigns list (create, filter, bulk),
campaign settings save/load, designer breadth (14 products), per-product
Front/Back position, pick-colors modal save, and the deliberate removal
of live profit (Shopify already has profit): no profit field, no profit
display, and price below base cost no longer blocks a dry-run, while
the 100-variant guard still blocks an over-limit combine set.

Runs against a temp data root only. Never touches the real
data/sets.json (byte-identity checked at the end) and never calls the
live shop: no Shopify client call is made by any test here.
"""

import hashlib
import json
import os
import sys
import tempfile

REAL_SETS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "sets.json")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


real_hash_before = sha(REAL_SETS)

TMP = tempfile.mkdtemp(prefix="setapp_gearlaunch_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "gearlaunch-test-password"
os.environ["FLASK_SECRET_KEY"] = "gearlaunch-test-secret"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as app_module  # noqa: E402

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


def post(path, body=None):
    token = client.get("/api/csrf-token").get_json()["csrf_token"]
    headers = {"Content-Type": "application/json",
               "X-CSRF-Token": token}
    return client.post(path, headers=headers,
                       data=json.dumps(body or {}))


def login():
    token = client.get("/api/csrf-token").get_json()["csrf_token"]
    return client.post("/api/login", headers={
        "Content-Type": "application/json", "X-CSRF-Token": token},
        data=json.dumps({"password": "gearlaunch-test-password"}))


def write_sets(sets):
    with open(os.path.join(TMP, "sets.json"), "w") as f:
        json.dump(sets, f)


def base_set(sid, name, slug="", tags=None, products=None):
    return {
        "id": sid, "name": name, "description": "",
        "tags": tags or [], "slug": slug, "grouping": "split",
        "publish_state": "draft", "publish_error": None,
        "artwork_locked": False, "design_url": "/static/uploads/d.png",
        "design_version": 1,
        "master_placement": {"x": 0.5, "y": 0.47,
                             "scale": 0.32, "angle": 0},
        "products": products or [], "text_layers": [],
    }


def product(pid, title, colours, sizes, sale=None, cost=None):
    return {
        "product_id": pid, "title": title, "locked": True,
        "colours": list(colours), "all_colours": list(colours),
        "sizes": list(sizes), "all_sizes": list(sizes),
        "sale_price": sale, "compare_at_price": None,
        "base_cost": cost, "mockups": [], "variant_prices": {},
        "default_color": colours[0] if colours else None,
        "image": f"https://example.test/{pid}.jpg",
        "images": [f"https://example.test/{pid}.jpg"],
    }


def main():
    check("login ok", login().status_code == 200)

    # ---- 1. Campaigns list: create, columns, filter ----
    print("== 1. Campaigns list ==")
    r = post("/api/campaigns", {"name": "Golden State Of",
                                "slug": "mind", "tags": ["warriors"]})
    check("create campaign 201", r.status_code == 201, r.status_code)
    golden = r.get_json()
    check("create campaign returns campaign defaults",
          golden.get("campaign", {}).get("status") == "draft"
          and golden.get("campaign", {}).get("fulfillment") == "LAUNCH_END",
          str(golden.get("campaign")))
    r = post("/api/campaigns", {"name": "Win The Day", "slug": "win"})
    check("second campaign created", r.status_code == 201, r.status_code)
    r = client.get("/api/campaigns")
    rows = r.get_json()
    check("campaigns list returns both", len(rows) == 2, str(rows))
    row = [x for x in rows if x["id"] == golden["id"]][0]
    check("campaign row has Gearlaunch columns",
          all(k in row for k in ("art_url", "name", "path", "tags",
                                 "orders", "items", "status",
                                 "fulfillment", "end"))
          and row["path"] == "/mind" and row["items"] == 0
          and row["orders"] is None and row["end"] is None, str(row))
    check("campaign row has NO profit field",
          "profit" not in json.dumps(rows).lower(), str(rows))
    r = client.get("/api/campaigns", query_string={"q": "warriors"})
    check("filter matches tag",
          len(r.get_json()) == 1
          and r.get_json()[0]["name"] == "Golden State Of",
          str(r.get_json()))
    r = client.get("/api/campaigns", query_string={"q": "mind"})
    check("filter matches path",
          len(r.get_json()) == 1, str(r.get_json()))
    r = client.get("/api/campaigns", query_string={"q": "nope"})
    check("filter hides non-matches", r.get_json() == [], str(r.get_json()))
    r = post("/api/campaigns", {"name": ""})
    check("campaign without name rejected", r.status_code == 400,
          r.status_code)
    r = post("/api/campaigns", {"name": "Bad", "slug": "Bad Slug!"})
    check("campaign bad slug rejected", r.status_code == 400, r.status_code)

    # ---- 2. Bulk actions ----
    print("== 2. Bulk actions ==")
    ids = [x["id"] for x in client.get("/api/campaigns").get_json()]
    r = post("/api/sets/bulk-campaign", {"action": "activate",
                                         "ids": ids})
    check("bulk activate", r.status_code == 200
          and r.get_json().get("updated") == 2, str(r.get_json()))
    r = client.get("/api/campaigns", query_string={"status": "active"})
    check("status filter active", len(r.get_json()) == 2, str(r.get_json()))
    r = post("/api/sets/bulk-campaign", {"action": "tag",
                                         "ids": ids[:1], "tag": "gold"})
    check("bulk tag", r.status_code == 200
          and "gold" in r.get_json()["sets"][0]["tags"],
          str(r.get_json()))
    r = post("/api/sets/bulk-campaign", {"action": "deactivate",
                                         "ids": ids})
    check("bulk deactivate", r.status_code == 200
          and r.get_json().get("updated") == 2, str(r.get_json()))
    r = post("/api/sets/bulk-campaign", {"action": "bogus", "ids": ids})
    check("bulk bogus action rejected", r.status_code == 400, r.status_code)
    r = post("/api/sets/bulk-campaign", {"action": "delete",
                                         "ids": ids[1:]})
    check("bulk delete", r.status_code == 200
          and r.get_json().get("deleted") == 1, str(r.get_json()))
    check("one campaign remains",
          len(client.get("/api/campaigns").get_json()) == 1)

    # ---- 3. Campaign settings ----
    print("== 3. Campaign settings ==")
    sid = client.get("/api/campaigns").get_json()[0]["id"]
    settings = {
        "name": "Golden State Of", "slug": "mind",
        "tags": ["warriors", "gold"],
        "description": "How To Order:\nSelect Product Color/Size",
        "campaign": {
            "storefront_homepage": True, "show_countdown": True,
            "fudge_factor": 30, "hide_purchases": False,
            "hide_from_search_engines": False, "social_buttons": True,
            "upsell_discount": 2.00, "end_date": "3/1/26",
            "tiktok_pixel": "tt-1", "snapchat_pixel": "sc-1",
            "facebook": {
                "custom_audience": "ca-1",
                "conversions_api_token": "capi-1",
                "page_view_pixel": "pv-1",
                "add_to_cart_pixel": "atc-1",
                "checkout_pixel": "co-1",
            },
        },
    }
    r = post(f"/api/sets/{sid}/campaign", settings)
    check("settings save 200", r.status_code == 200, str(r.get_json()))
    r = client.get(f"/api/sets/{sid}/campaign")
    j = r.get_json()
    check("settings load round-trip",
          j["campaign"]["fudge_factor"] == 30
          and j["campaign"]["upsell_discount"] == 2.00
          and j["campaign"]["facebook"]["checkout_pixel"] == "co-1"
          and j["campaign"]["end_date"] == "3/1/26"
          and j["slug"] == "mind" and j["tags"] == ["warriors", "gold"]
          and j["url_path"] == "/mind", str(j))
    check("settings load has no profit",
          "profit" not in json.dumps(j).lower(), str(j))
    # Disk round-trip: fresh read through the API after a reload.
    sets = app_module.load_sets()
    check("settings persisted on disk",
          sets[sid]["campaign"]["fudge_factor"] == 30
          and sets[sid]["campaign"]["facebook"]["ca"[:0] or
                                            "custom_audience"] == "ca-1",
          str(sets[sid].get("campaign")))
    bad = dict(settings)
    bad["campaign"] = dict(settings["campaign"], fudge_factor=-1)
    check("negative fudge factor rejected",
          post(f"/api/sets/{sid}/campaign", bad).status_code == 400)
    bad = dict(settings)
    bad["campaign"] = dict(settings["campaign"], upsell_discount=-5)
    check("negative upsell rejected",
          post(f"/api/sets/{sid}/campaign", bad).status_code == 400)
    bad = dict(settings)
    bad["campaign"] = dict(settings["campaign"],
                           show_countdown="yes")
    check("non-boolean toggle rejected",
          post(f"/api/sets/{sid}/campaign", bad).status_code == 400)
    check("failed settings save changed nothing",
          client.get(f"/api/sets/{sid}/campaign").get_json()
          ["campaign"]["fudge_factor"] == 30)
    check("locked campaign skipped by bulk activate",
          post(f"/api/sets/{sid}/campaign",
               {"campaign": {"status": "locked"}}).status_code == 200
          and post("/api/sets/bulk-campaign",
                   {"action": "activate", "ids": [sid]}).get_json()
          .get("skipped") == [sid],
          str(client.get(f"/api/sets/{sid}/campaign").get_json()))
    # Review fixes (2026-11-03): duplicate of a locked campaign must
    # start as a fresh draft (other campaign settings are copied);
    # a blank campaign name is rejected, like campaign create.
    r = post(f"/api/sets/{sid}/duplicate", {})
    copy_set = r.get_json()
    check("duplicate of locked campaign starts as draft",
          r.status_code == 201
          and copy_set["campaign"]["status"] == "draft"
          and copy_set["campaign"]["fudge_factor"] == 30
          and copy_set["publish_state"] == "draft", str(copy_set))
    check("blank campaign name rejected on settings save",
          post(f"/api/sets/{sid}/campaign",
               {"name": "   "}).status_code == 400)
    check("blank name save changed nothing",
          client.get(f"/api/sets/{sid}/campaign").get_json()["name"]
          == "Golden State Of")
    check("fractional fudge factor rejected",
          post(f"/api/sets/{sid}/campaign",
               {"campaign": {"fudge_factor": 30.5}}).status_code == 400)

    # ---- 4. Designer breadth, position, pick colors ----
    print("== 4. Designer breadth, position, pick colors ==")
    products = [product(f"p{i}", f"Product {i}",
                        ["Black", "White", "Navy", "Red"],
                        ["S", "M"], sale=29.99)
                for i in range(14)]
    write_sets({"wide-set": base_set("wide-set", "Wide Set",
                                     slug="wide", products=products)})
    r = client.get("/api/sets")
    mine = [s for s in r.get_json() if s["id"] == "wide-set"][0]
    check("set holds 14 products", len(mine["products"]) == 14,
          len(mine["products"]))
    check("every product has a price source",
          all(p.get("sale_price") is not None
              or p.get("variant_prices") for p in mine["products"]))
    pid = "p0"
    r = post(f"/api/sets/wide-set/products/{pid}/position",
             {"position": "back"})
    check("position back saved", r.status_code == 200
          and [p for p in r.get_json()["products"]
               if p["product_id"] == pid][0].get("position") == "back",
          str(r.get_json()))
    r = post(f"/api/sets/wide-set/products/{pid}/position",
             {"position": "side"})
    check("position side rejected", r.status_code == 400, r.status_code)
    # Pick colors: subset + default, then Select-All equivalent.
    r = post(f"/api/sets/wide-set/products/{pid}/colors",
             {"colours": ["White", "Navy"], "default_color": "Navy"})
    p = [x for x in r.get_json()["products"]
         if x["product_id"] == pid][0]
    check("pick colors saves subset + default first",
          r.status_code == 200 and p["colours"] == ["Navy", "White"]
          and p["default_color"] == "Navy", str(p))
    r = post(f"/api/sets/wide-set/products/{pid}/colors",
             {"colours": ["Black", "White", "Navy", "Red"],
              "default_color": "Red"})
    p = [x for x in r.get_json()["products"]
         if x["product_id"] == pid][0]
    check("pick colors select-all saved",
          p["colours"] == ["Red", "Black", "White", "Navy"]
          and p["default_color"] == "Red", str(p))
    r = post(f"/api/sets/wide-set/products/{pid}/colors",
             {"colours": ["Pink"]})
    check("pick colors outside all_colours rejected",
          r.status_code == 400, r.status_code)
    r = post(f"/api/sets/wide-set/products/{pid}/colors",
             {"colours": ["Black"], "default_color": "White"})
    check("pick colors default outside selection rejected",
          r.status_code == 400, r.status_code)

    # ---- 5. No profit + guards intact ----
    print("== 5. No profit, guards intact ==")
    write_sets({"cheap-set": base_set(
        "cheap-set", "Cheap Set", slug="cheap",
        products=[product("c1", "Cheap Tee", ["Black"], ["S"],
                          sale=10, cost=12)])})
    r = post("/api/sets/cheap-set/publish", {"dry_run": True})
    check("price below base cost does NOT block dry-run",
          r.status_code == 200 and r.get_json().get("dry_run") is True,
          str(r.status_code) + str(r.get_json())[:200])
    rows = r.get_json().get("checklist", [])
    check("checklist has no profit key",
          rows and all("profit" not in row for row in rows), str(rows))
    check("checklist ready does not need base cost math",
          rows and rows[0]["ready"] is True, str(rows))
    big_products = [
        product("t1", "Tee", [f"C{i}" for i in range(12)],
                ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
                sale=20),
        product("t2", "Hoodie", [f"C{i}" for i in range(8)],
                ["S", "M", "L", "XL", "2XL", "3XL"], sale=40),
        product("t3", "Crewneck", [f"C{i}" for i in range(8)],
                ["S", "M", "L", "XL", "2XL", "3XL"], sale=34),
    ]
    big = base_set("big-set", "Big Set", slug="big",
                   products=big_products)
    big["grouping"] = "combine"
    write_sets({"big-set": big})
    r = post("/api/sets/big-set/publish", {"dry_run": True})
    check("combine over 100 variants still blocked",
          r.status_code == 400 and "100" in (r.get_json().get("error") or ""),
          str(r.status_code) + str(r.get_json())[:200])
    post("/api/sets/big-set/details", {"grouping": "split"})
    r = post("/api/sets/big-set/publish", {"dry_run": True})
    check("split same set passes variant guard",
          r.status_code == 200 and r.get_json().get("dry_run") is True,
          str(r.status_code) + str(r.get_json())[:200])

    # ---- 6. UI markers + JS syntax ----
    print("== 6. UI markers ==")
    import re as _re
    import subprocess
    html = ""
    for _f in ("campaigns.html", "campaign_settings.html", "designer.html"):
        html += open(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "templates", _f)).read()
    html += open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "static", "app.js")).read()
    for marker in ["campaignsTbody", "Create campaign",
                   "Campaign settings", "How To Order",
                   "pickColorsModal", "Select All",
                   "Position", "Refresh", "FRONT", "BACK"]:
        check(f"UI has {marker}", marker in html)
    check("UI has no profit display",
          "Profit:" not in html and "profitOf" not in html
          and "negative profit" not in html.lower(), "")
    check("UI has no draft publish wording",
          "Publish as DRAFT" not in html, "")
    proc = subprocess.run(["node", "--check", os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "static", "app.js")], capture_output=True, text=True)
    check("editor JS passes node --check", proc.returncode == 0,
          proc.stderr[:300])

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
    check("real sets.json byte-identical",
          sha(REAL_SETS) == real_hash_before)
    if FAILED:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
