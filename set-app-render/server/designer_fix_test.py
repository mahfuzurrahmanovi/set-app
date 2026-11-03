"""Designer fix tests (Ovi, 2026-11-03 22:18, 4 fixes).

1. Designer topbar hides half the phone screen -> topbar removed,
   Save/Publish/Log out preserved elsewhere.
2. Campaigns explanatory paragraph removed.
3. Bulk clone must start with NO design (duplicate blank).
4. Design must be movable: touch + drag handlers, placement save
   round-trip, centre mockup uses the BARE photo, never a rendered
   mockup.

FAILS before the fix, PASSES after. Temp data root only, mock
Shopify only, never touches the real data/sets.json, never
publishes anything live.
"""

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile

REAL_SETS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "sets.json")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


real_hash_before = sha(REAL_SETS)

TMP = tempfile.mkdtemp(prefix="setapp_designerfix_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "designerfix-test-password"
os.environ["FLASK_SECRET_KEY"] = "designerfix-test-secret"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as app_module  # noqa: E402
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


def post(path, body=None):
    token = client.get("/api/csrf-token").get_json()["csrf_token"]
    return client.post(path, headers={
        "Content-Type": "application/json", "X-CSRF-Token": token},
        data=json.dumps(body or {}))


def login():
    return post("/api/login", {"password": "designerfix-test-password"})


def write_sets(sets):
    with open(os.path.join(TMP, "sets.json"), "w") as f:
        json.dump(sets, f)


def seed_set():
    return {
        "id": "orig12345678", "name": "Oregon Ducks Set",
        "description": "Test", "tags": ["oregon"], "slug": "oregon-ducks-set",
        "grouping": "split", "publish_state": "draft",
        "publish_error": None, "artwork_locked": False,
        "design_url": "/static/uploads/old-design.png",
        "design_width": 1536, "design_height": 1024,
        "design_dpi": 128, "design_warnings": ["low dpi"],
        "design_version": 3,
        "master_placement": {"x": 0.5, "y": 0.45,
                             "scale": 0.5, "angle": 0},
        "text_layers": [{"id": "lay12345", "text": "GO DUCKS",
                         "font": "sans", "size": 120}],
        "campaign": {"status": "active", "fulfillment": "LAUNCH_END",
                     "end_date": None, "storefront_homepage": False,
                     "show_countdown": True, "fudge_factor": 30,
                     "hide_purchases": False,
                     "hide_from_search_engines": False,
                     "social_buttons": True, "upsell_discount": 2.0,
                     "tiktok_pixel": "", "snapchat_pixel": "",
                     "facebook": {"custom_audience": "",
                                  "conversions_api_token": "",
                                  "page_view_pixel": "",
                                  "add_to_cart_pixel": "",
                                  "checkout_pixel": ""}},
        "products": [
            {"product_id": "15469998538906", "title": "Oregon Tee",
             "locked": True, "colours": ["Black", "White"],
             "all_colours": ["Black", "White"],
             "sizes": ["S", "M"], "all_sizes": ["S", "M"],
             "sale_price": 18.88, "compare_at_price": None,
             "base_cost": 12.5, "mockups": ["/static/mockups/old.jpg"],
             "mockup_versions": {"/static/mockups/old.jpg": 3},
             "mockup_version": 3,
             "hero_image": "/static/mockups/old.jpg",
             "hidden_layers": ["lay12345"],
             "image": "https://example.test/tee.jpg",
             "images": ["https://example.test/tee.jpg"],
             "variant_prices": {}},
            {"product_id": "15470002929818", "title": "Oregon Hoodie",
             "locked": True, "colours": ["Black"],
             "all_colours": ["Black"], "sizes": ["S", "M"],
             "all_sizes": ["S", "M"], "sale_price": 44,
             "compare_at_price": None, "base_cost": 20,
             "mockups": [], "mockup_versions": {},
             "mockup_version": None, "hero_image": None,
             "hidden_layers": [],
             "image": "https://example.test/hoodie.jpg",
             "images": ["https://example.test/hoodie.jpg"],
             "variant_prices": {}},
        ],
    }


def make_transparent_png():
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    for x in range(100, 300):
        for y in range(100, 300):
            img.putpixel((x, y), (255, 255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def main():
    print("== Fix 1 + 2: pages ==")
    check("login ok", login().status_code == 200)
    write_sets({"orig12345678": seed_set()})
    designer = client.get("/campaigns/orig12345678/designer")
    dbody = designer.get_data(as_text=True)
    check("designer page loads", designer.status_code == 200,
          designer.status_code)
    check("designer has NO topbar card",
          'class="card topbar"' not in dbody and 'id="topSetName"' not in dbody,
          dbody[:200])
    check("designer has NO 'Save stores everything' paragraph",
          "Save stores everything" not in dbody)
    check("designer still has Publish to Shopify (live)",
          "Publish to Shopify (live)" in dbody)
    check("designer still has Download set JSON",
          "Download set JSON" in dbody)
    check("designer nav still has Log out", "Log out" in dbody)
    check("designer opens with mockup area (editor) before publish card",
          dbody.find('class="editor"') != -1 and
          dbody.find('class="editor"') < dbody.find("Variants and publish"))
    campaigns = client.get("/campaigns")
    cbody = campaigns.get_data(as_text=True)
    check("campaigns page loads", campaigns.status_code == 200)
    check("campaigns has NO explanatory paragraph",
          "Every set is a campaign" not in cbody and
          "Tap a campaign name for its settings" not in cbody)

    print("== Fix 3: duplicate is blank ==")
    r = post("/api/sets/orig12345678/duplicate", {})
    check("duplicate returns 201", r.status_code == 201, r.status_code)
    dup = r.get_json()
    dup_id = dup["id"]
    check("duplicate keeps name with (copy)",
          dup["name"] == "Oregon Ducks Set (copy)", dup["name"])
    check("duplicate design_url is None", dup.get("design_url") is None,
          dup.get("design_url"))
    check("duplicate design dims/dpi cleared",
          dup.get("design_width") is None and
          dup.get("design_height") is None and
          dup.get("design_dpi") is None)
    check("duplicate design warnings cleared",
          dup.get("design_warnings") in (None, []))
    check("duplicate design_version reset to 1",
          dup.get("design_version") == 1, dup.get("design_version"))
    check("duplicate text_layers empty", dup.get("text_layers") == [])
    check("duplicate products kept (2)",
          len(dup.get("products", [])) == 2)
    tee = [p for p in dup["products"]
           if p["product_id"] == "15469998538906"][0]
    check("duplicate keeps colours/sizes/prices",
          tee["colours"] == ["Black", "White"] and
          tee["sizes"] == ["S", "M"] and tee["sale_price"] == 18.88 and
          tee["base_cost"] == 12.5)
    check("duplicate product mockups cleared", tee.get("mockups") == [])
    check("duplicate mockup versions cleared",
          tee.get("mockup_versions") == {} and
          tee.get("mockup_version") is None)
    check("duplicate mockup hero cleared",
          not (tee.get("hero_image") or "").startswith("/static/mockups/"),
          tee.get("hero_image"))
    check("duplicate hidden layers cleared",
          tee.get("hidden_layers") == [])
    check("duplicate master placement kept",
          dup.get("master_placement") == {"x": 0.5, "y": 0.45,
                                          "scale": 0.5, "angle": 0})
    check("duplicate campaign settings kept (countdown/fudge)",
          dup.get("campaign", {}).get("show_countdown") is True and
          dup.get("campaign", {}).get("fudge_factor") == 30)
    check("duplicate campaign status draft",
          dup.get("campaign", {}).get("status") == "draft")
    check("duplicate publish_state draft",
          dup.get("publish_state") == "draft")
    orig = client.get("/api/sets").get_json()
    orig = [s for s in orig if s["id"] == "orig12345678"][0]
    check("original set unchanged by duplicate",
          orig["design_url"] == "/static/uploads/old-design.png" and
          len(orig["text_layers"]) == 1 and
          orig["products"][0]["mockups"] == ["/static/mockups/old.jpg"])

    print("== Fix 3b: upload after clone = one design only ==")
    token = client.get("/api/csrf-token").get_json()["csrf_token"]
    buf = make_transparent_png()
    r = client.post(f"/api/sets/{dup_id}/upload",
                    headers={"X-CSRF-Token": token},
                    content_type="multipart/form-data",
                    data={"design": (buf, "booshit.png")})
    check("upload to clone ok", r.status_code == 200, r.status_code)
    new_url = r.get_json().get("url", "")
    check("upload gives one new design url",
          new_url.startswith("/static/uploads/") and
          new_url != "/static/uploads/old-design.png", new_url)
    after = [s for s in client.get("/api/sets").get_json()
             if s["id"] == dup_id][0]
    check("clone after upload has exactly that design",
          after["design_url"] == new_url)
    check("clone after upload has no rendered mockups",
          all(p.get("mockups") == [] for p in after["products"]))
    bare = client.get(
        f"/api/sets/{dup_id}/products/15469998538906/photo?bare=1")
    bare_j = bare.get_json()
    check("bare photo endpoint returns bare photo, never a mockup",
          bare_j.get("photo") == "https://example.test/tee.jpg" and
          "/static/mockups/" not in (bare_j.get("photo") or ""),
          bare_j)

    print("== Fix 4: movable design ==")
    js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "static", "app.js")
    with open(js_path) as f:
        js = f.read()
    css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "static", "app.css")
    with open(css_path) as f:
        css = f.read()
    check("app.js passes node --check",
          subprocess.run(["node", "--check", js_path],
                         capture_output=True).returncode == 0)
    check("touch handlers present (touchstart/touchend)",
          "touchstart" in js and "touchend" in js)
    check("drag handlers present (pointerdown/move/up on placeBox)",
          "pointerdown" in js and "pointermove" in js and
          "pointerup" in js and "placeBox" in js)
    check("last-touch click guard present",
          "lastTouch" in js or "lastTouchAt" in js)
    check("designer still has a Save button",
          "saveAll()" in dbody)
    check("designer restores publish status / draft line / unsaved line",
          'id="publishStatus"' in dbody and 'id="draftLine"' in dbody and
          'id="dirtyNote"' in dbody)
    # Real drag execution (node stub DOM): placeAt must move BOTH
    # the sliders AND the live master placement, so positionPlaceBox
    # (which reads the saved master) actually moves the box.
    import subprocess as _sp
    _harness = """
var window = { fetch: async function() { return { json: async function() { return {}; } }; } };
var _els = {};
function _el(id) {
  if (!_els[id]) _els[id] = { style: {}, textContent: '', value: '', innerHTML: '', className: '',
    getBoundingClientRect: function() { return { left: 0, top: 0, width: 400, height: 400 }; },
    naturalWidth: 400, naturalHeight: 400, addEventListener: function() {}, setAttribute: function() {}, getAttribute: function() { return ''; },
    querySelectorAll: function() { return []; }, appendChild: function() {}, remove: function() {} };
  return _els[id];
}
var document = { getElementById: _el, addEventListener: function() {}, querySelectorAll: function() { return []; }, querySelector: function() { return null; } };
var alert = function() {};
"""
    _tmp = os.path.join(TMP, "drag.js")
    with open(_tmp, "w") as _f:
        _f.write(_harness)
        _f.write(js)
        _f.write("""
currentSet = { master_placement: { x: 0.5, y: 0.45, scale: 0.5, angle: 0 },
  products: [{ product_id: 'p1', locked: true }] };
selectedPid = 'p1'; viewSide = 'front';
var beforeLeft = null;
positionPlaceBox(); beforeLeft = _el('placeBox').style.left;
placeAt(100, 300);
console.log(JSON.stringify({ mx: currentSet.master_placement.x, my: currentSet.master_placement.y,
  xv: _el('x').value, yv: _el('y').value, left: _el('placeBox').style.left, top: _el('placeBox').style.top, beforeLeft: beforeLeft }));
""")
    _proc = _sp.run(["node", _tmp], capture_output=True, text=True)
    try:
        _out = json.loads(_proc.stdout.strip().splitlines()[-1])
    except Exception:
        _out = {}
    # Mockup fix (2026-11-03 22:43): the print area box is FIXED at
    # 25%/20%/50%/50% and only the design moves, clamped to the box.
    # placeAt(100, 300) on a 400x400 mockup is x 0.25 (box left edge)
    # and y 0.75 clamped to the box bottom edge 0.70; the box itself
    # stays at 25%/20% before and after.
    check("drag execution: placeAt moves master + sliders, box fixed",
          _proc.returncode == 0 and _out.get("mx") == 0.25 and
          _out.get("my") == 0.70 and _out.get("xv") == "0.25" and
          _out.get("yv") == "0.70" and _out.get("left") == "25%" and
          _out.get("top") == "20%",
          _proc.stdout[:300] + _proc.stderr[:300])
    _seg = js.split("function centreImageUrl")[1].split(
        "function renderCentreMockup")[0] if "function centreImageUrl" in js else ""
    _code = "\n".join(l for l in _seg.splitlines()
                       if not l.strip().startswith("//"))
    check("centreImageUrl never returns a rendered mockup",
          "centreImageUrl" in js and "p.mockups" not in _code and
          "mockups[0]" not in _code and
          "indexOf('/static/mockups/')" in _code, _code[:200])
    # Server placement save round-trip: move the design, reload it.
    r = post(f"/api/sets/{dup_id}/master",
             {"placement": {"x": 0.35, "y": 0.6, "scale": 0.42,
                            "angle": 5}})
    check("master placement save ok", r.status_code == 200, r.status_code)
    moved = [s for s in client.get("/api/sets").get_json()
             if s["id"] == dup_id][0]
    check("moved placement persists",
          moved["master_placement"]["x"] == 0.35 and
          moved["master_placement"]["y"] == 0.6 and
          moved["master_placement"]["scale"] == 0.42 and
          moved["master_placement"]["angle"] == 5,
          moved["master_placement"])
    check("separate pages still separate (no stacked index)",
          not os.path.exists(os.path.join(
              os.path.dirname(os.path.abspath(__file__)),
              "templates", "index.html")))
    check("real sets.json byte-identical",
          sha(REAL_SETS) == real_hash_before)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        sys.exit(1)


if __name__ == "__main__":
    main()
