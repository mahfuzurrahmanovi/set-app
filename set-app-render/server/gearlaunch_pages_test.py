"""Separate Gearlaunch pages tests (2026-11-03).

The 2026-11-03 Gearlaunch build stacked Campaigns, Campaign settings
and Designer into one index.html. Ovi (21:28) said that is not user
friendly and wants the EXACT Gearlaunch pages as separate pages.
Scope change 21:30: Publish is DIRECT (live/active), not draft only.

This suite FAILS before the fix (new routes 404, / serves stacked
markup) and PASSES after. Runs against a temp data root only, mock
Shopify clients only, never touches the real data/sets.json and
never publishes anything live.
"""

import hashlib
import json
import os
import re
import sys
import tempfile

REAL_SETS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "sets.json")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


real_hash_before = sha(REAL_SETS)

TMP = tempfile.mkdtemp(prefix="setapp_pages_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "pages-test-password"
os.environ["FLASK_SECRET_KEY"] = "pages-test-secret"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as app_module  # noqa: E402
import shopify as shopify_api  # noqa: E402

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
    return client.post(path, headers={
        "Content-Type": "application/json", "X-CSRF-Token": token},
        data=json.dumps(body or {}))


def login():
    return post("/api/login", {"password": "pages-test-password"})


def write_sets(sets):
    with open(os.path.join(TMP, "sets.json"), "w") as f:
        json.dump(sets, f)


def base_set(sid, name, slug="", tags=None, products=None):
    return {
        "id": sid, "name": name, "description": "Test description",
        "tags": tags or [], "slug": slug, "grouping": "split",
        "publish_state": "draft", "publish_error": None,
        "artwork_locked": False, "design_url": "/static/uploads/d.png",
        "design_version": 1,
        "master_placement": {"x": 0.5, "y": 0.47,
                             "scale": 0.32, "angle": 0},
        "products": products or [], "text_layers": [],
        "campaign": {"status": "draft", "fulfillment": "LAUNCH_END",
                     "end_date": "3/1/26"},
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


def html_of(path):
    r = client.get(path)
    return r.status_code, r.get_data(as_text=True)


def main():
    # Unauthenticated pages must NOT leak page content: the login
    # page is served instead (API remains the data gate as before).
    print("== 0. Auth gating on new page routes ==")
    code, body = html_of("/campaigns")
    check("unauthenticated /campaigns serves login, not the table",
          code == 200 and "Log in" in body and "<table" not in body,
          f"{code} {body[:120]}")
    check("login ok", login().status_code == 200)

    # Seed one set via the API, then check each page in isolation.
    r = post("/api/campaigns", {"name": "Golden State Of",
                                "slug": "mind", "tags": ["warriors"]})
    check("seed campaign created", r.status_code == 201, r.status_code)
    sid = r.get_json()["id"]

    print("== 1. GET / redirects to /campaigns ==")
    r = client.get("/", follow_redirects=False)
    check("GET / redirects to /campaigns",
          r.status_code in (301, 302, 308)
          and "/campaigns" in (r.headers.get("Location") or ""),
          f"{r.status_code} {r.headers.get('Location')}")

    print("== 2. /campaigns is ONLY the list page ==")
    code, body = html_of("/campaigns")
    check("/campaigns 200", code == 200, code)
    headers = ["ART", "NAME", "PATH", "TAGS", "ORDERS", "ITEMS",
               "STATUS", "FULFILLMENT", "END"]
    positions = [body.find(f">{h}<") for h in headers]
    check("campaigns table headers in Gearlaunch order",
          all(p >= 0 for p in positions)
          and positions == sorted(positions), str(positions))
    check("campaigns table has horizontal-scroll wrapper",
          "tableWrap" in body, "")
    for marker in ["Create campaign", "Filter by name, path, tags",
                   "Activate", "Deactivate", "Delete", "Tag"]:
        check(f"campaigns page has {marker}", marker in body)
    check("campaigns page links to a settings page",
          f"/campaigns/{sid}" in body)
    check("campaigns page links to its designer page",
          f"/campaigns/{sid}/designer" in body)
    for forbidden in ['id="campaignSettingsCard"', 'id="centreImg"',
                      'id="pickColorsModal"', "PRODUCTS ("]:
        check(f"campaigns page has no {forbidden}",
              forbidden not in body)

    print("== 3. /campaigns/<id> is ONLY the settings page ==")
    code, body = html_of(f"/campaigns/{sid}")
    check("settings page 200", code == 200, code)
    for marker in ["Golden State Of", "Designer", "Delete campaign",
                   "Details", "Storefront", "Conversion tools",
                   "Cloak &amp; Dagger", "Upsells",
                   "Description", "Use How To Order text",
                   "fansfit.shop/"]:
        check(f"settings page has {marker}", marker in body)
    # Mockup fix (2026-11-03 22:43, Fix 5): pixel + End fields removed.
    for removed in ["Tik Tok Pixel", "Snapchat Pixel",
                    "Override default pixels", "Custom Audience",
                    "Conversions API", "campTiktok", "campSnapchat",
                    "campFbAudience", "campEnd"]:
        check(f"settings page has no {removed}", removed not in body)
    check("settings page links back to /campaigns",
          'href="/campaigns"' in body)
    check("settings page links to its designer",
          f"/campaigns/{sid}/designer" in body)
    for forbidden in ["<table", 'id="centreImg"',
                      'id="pickColorsModal"']:
        check(f"settings page has no {forbidden}",
              forbidden not in body)

    print("== 4. /campaigns/<id>/designer is ONLY the designer ==")
    code, body = html_of(f"/campaigns/{sid}/designer")
    check("designer page 200", code == 200, code)
    for marker in ["FRONT", "BACK", 'id="centreImg"', "PRODUCTS",
                   "Pick colors", 'id="pickColorsModal"',
                   "Select All", "Upload design", "Master placement",
                   "Add products", "Catalog products",
                   "Variants and publish",
                   "Publish to Shopify (live)"]:
        check(f"designer page has {marker}", marker in body)
    check("designer page links back to /campaigns",
          'href="/campaigns"' in body)
    check("designer page links to its settings",
          f'href="/campaigns/{sid}"' in body)
    for forbidden in ['id="campaignSettingsCard"', "<table"]:
        check(f"designer page has no {forbidden}",
              forbidden not in body)

    print("== 5. No profit, no draft publish wording ==")
    for path in ("/campaigns", f"/campaigns/{sid}",
                 f"/campaigns/{sid}/designer"):
        _, b = html_of(path)
        check(f"no profit display on {path}",
              "Profit:" not in b and "profitOf" not in b
              and "Profit per unit" not in b, "")
        check(f"no draft publish wording on {path}",
              "Publish as DRAFT" not in b
              and "DRAFT products only" not in b
              and "never live" not in b, "")

    print("== 6. Direct publish (mock Shopify only) ==")
    write_sets({"live-set": base_set(
        "live-set", "Live Set", slug="live",
        products=[product("l1", "Live Tee", ["Black"], ["S"],
                          sale=20, cost=12)])})
    calls = []

    def mock_create(**kw):
        calls.append(kw)
        return {"id": 99, "status": "active", "handle": "live-set"}

    orig_create = shopify_api.create_live_product
    shopify_api.create_live_product = mock_create
    orig_auth = shopify_api.authenticated
    shopify_api.authenticated = lambda: True
    try:
        r = post("/api/sets/live-set/publish", {})
        j = r.get_json()
        check("direct publish 200 with state published",
              r.status_code == 200 and j.get("state") == "published"
              and j.get("published") is True, str(j)[:300])
        check("mock Shopify create was called",
              bool(calls), str(calls)[:200])
        # The server-side payload builder must send active status:
        # verified via shopify.create_product below, not via calls
        # kwargs (the app passes title/description/tags/options/
        # variants/images; status is set inside create_product).
        src = open(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "shopify.py")).read()
        check("shopify.create_live_product sends status active",
              '"status": "active"' in src, "")
        check("old publish-draft endpoint is gone",
              post("/api/sets/live-set/publish-draft", {}).status_code
              in (404, 405), "")
        r = post("/api/sets/live-set/publish", {})
        check("second publish rejected as already published",
              r.status_code == 409, str(r.status_code))
    finally:
        shopify_api.authenticated = orig_auth
        shopify_api.create_live_product = orig_create

    print("== 7. Guards intact ==")
    big = base_set("big-set", "Big Set", slug="big",
                   products=[
                       product("t1", "Tee", [f"C{i}" for i in range(12)],
                               ["S", "M", "L", "XL", "2XL", "3XL",
                                "4XL", "5XL"], sale=20),
                       product("t2", "Hoodie",
                               [f"C{i}" for i in range(8)],
                               ["S", "M", "L", "XL", "2XL", "3XL"],
                               sale=40),
                       product("t3", "Crewneck",
                               [f"C{i}" for i in range(8)],
                               ["S", "M", "L", "XL", "2XL", "3XL"],
                               sale=34)])
    big["grouping"] = "combine"
    write_sets({"big-set": big})
    r = post("/api/sets/big-set/publish", {"dry_run": True})
    check("combine over 100 variants still blocked",
          r.status_code == 400 and "100" in (r.get_json().get("error") or ""),
          str(r.status_code))
    post("/api/sets/big-set/details", {"grouping": "split"})
    r = post("/api/sets/big-set/publish", {"dry_run": True})
    check("split same set passes variant guard",
          r.status_code == 200 and r.get_json().get("dry_run") is True,
          str(r.status_code))
    check("dry-run preview says live, not draft",
          "live" in (r.get_json().get("note") or "").lower()
          or "live" in json.dumps(r.get_json()).lower(), "")

    print("== 8. Designer JS guard executes without throwing ==")
    import subprocess as _sp
    js = open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "static", "app.js")).read()
    harness = """
var window = { fetch: async function() { return { json: async function() { return {}; } }; } };
var document = {
  getElementById: function(id) {
    if (typeof CASE_MISSING !== 'undefined' && CASE_MISSING && id.indexOf('camp') === 0) return null;
    return { style: {}, textContent: '', value: '', innerHTML: '', className: '', addEventListener: function() {} };
  },
  addEventListener: function() {},
  querySelectorAll: function() { return []; },
  querySelector: function() { return null; }
};
var alert = function() {};
"""
    for case, missing in (("designer (no camp fields)", True),
                          ("settings (camp fields present)", False)):
        tmp_js = os.path.join(TMP, "guard.js")
        with open(tmp_js, "w") as f:
            f.write(harness.replace("CASE_MISSING", "true" if missing else "false"))
            f.write(js)
            f.write("""
currentSet = { name: 'Guard Set', slug: 'guard', tags: [], description: '',
  campaign: { status: 'draft', facebook: {} }, products: [], master_placement: {} };
try { fillCampaignSettings(); console.log('GUARD_OK'); }
catch (e) { console.log('GUARD_FAIL ' + e.message); process.exit(1); }
""")
        proc = _sp.run(["node", tmp_js], capture_output=True, text=True)
        check(f"fillCampaignSettings does not throw on {case}",
              proc.returncode == 0 and "GUARD_OK" in proc.stdout,
              proc.stdout[:200] + proc.stderr[:200])
    check("fillCampaignSettings has the designer early-return guard",
          "if (!document.getElementById('campStorefrontHomepage')) return;" in js)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
    check("real sets.json byte-identical",
          sha(REAL_SETS) == real_hash_before)
    if FAILED:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
