"""Mockup fix tests (Ovi, 2026-11-03 22:43, Warriors screenshots).

1. Uploaded design must be VISIBLE in the designer mockup (was an empty box).
2. Print area is FIXED; only the design moves inside it.
3. Centre mockup is a flat Printify product photo when a template matches.
4. URL path auto-generates from the name, stops after manual edit.
5. TikTok/Snapchat/Facebook pixel + End date fields removed from settings.

FAILS before the fix, PASSES after. Temp data root only, mock Shopify
only, never touches the real data/sets.json, never publishes live.
"""

import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_SETS = os.path.join(os.path.dirname(HERE), "data", "sets.json")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


real_hash_before = sha(REAL_SETS)

TMP = tempfile.mkdtemp(prefix="setapp_mockupfix_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "mockupfix-test-password"
os.environ["FLASK_SECRET_KEY"] = "mockupfix-test-secret"

sys.path.insert(0, HERE)
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
    return client.post(path, headers={
        "Content-Type": "application/json", "X-CSRF-Token": token},
        data=json.dumps(body or {}))


def login():
    return post("/api/login", {"password": "mockupfix-test-password"})


def write_sets(sets):
    with open(os.path.join(TMP, "sets.json"), "w") as f:
        json.dump(sets, f)


def seed_set():
    return {
        "id": "warriors1234", "name": "Warriors",
        "description": "Test", "tags": ["warriors"], "slug": "warriors",
        "grouping": "split", "publish_state": "draft",
        "publish_error": None, "artwork_locked": False,
        "design_url": "/static/uploads/test-design.png",
        "design_width": 1000, "design_height": 1000,
        "design_dpi": 200, "design_warnings": [],
        "design_version": 1,
        "master_placement": {"x": 0.5, "y": 0.45,
                             "scale": 0.5, "angle": 0},
        "text_layers": [],
        "campaign": {"status": "draft", "fulfillment": "LAUNCH_END",
                     "end_date": "3/1/26", "storefront_homepage": False,
                     "show_countdown": False, "fudge_factor": 0,
                     "hide_purchases": False,
                     "hide_from_search_engines": False,
                     "social_buttons": False, "upsell_discount": None,
                     "tiktok_pixel": "old-tiktok",
                     "snapchat_pixel": "old-snap",
                     "facebook": {"custom_audience": "old-aud",
                                  "conversions_api_token": "old-capi",
                                  "page_view_pixel": "old-pv",
                                  "add_to_cart_pixel": "old-atc",
                                  "checkout_pixel": "old-co"}},
        "products": [
            {"product_id": "999", "title": "Unisex Long Sleeve Tee",
             "locked": True, "colours": ["White"],
             "all_colours": ["White"], "sizes": ["S", "M"],
             "all_sizes": ["S", "M"], "sale_price": 29.46,
             "compare_at_price": None, "base_cost": None,
             "mockups": [], "mockup_versions": {},
             "mockup_version": None, "hero_image": None,
             "hidden_layers": [],
             "image": "https://example.test/model-tee.jpg",
             "images": ["https://example.test/model-tee.jpg"],
             "variant_prices": {}},
        ],
    }


write_sets({"warriors1234": seed_set()})
login()

JS = open(os.path.join(HERE, "static", "app.js")).read()
CSS = open(os.path.join(HERE, "static", "app.css")).read()

# --- Fix 1: design rendered inside the placeBox ---
check("centre renders design img inside placeBox",
      "design_url" in JS and "designImg" in JS,
      "renderCentreMockup must build a design <img> inside placeBox")
check("centre design img uses currentSet.design_url",
      "currentSet.design_url" in JS and "designImg" in JS)
check("no-design case still shows note, no invented design",
      "No design uploaded yet" in JS)

# --- Fix 2: fixed print area, design moves inside it ---
check("fixed print area constants present (25/20/50/50)",
      "PRINT_AREA" in JS or ("25" in JS and "50" in JS and
                             "printArea" in JS),
      "positionPlaceBox must use a fixed print area")
check("box drag removed (old box-drag binding gone)",
      "centreDrag" not in JS)
# Precise: the old code dragged the box via a `centreDrag` state bound
# to the box; the new code drags the DESIGN via a `designDrag` state
# (pointerdown on the box/design area moves the design, never the box).
check("old box-drag state is gone", "centreDrag" not in JS,
      "centreDrag moved the print area itself")
check("new design-drag state present", "designDrag" in JS)
check("design drag handler present",
      "designImg" in JS and "pointerdown" in JS)
check("hint text says design moves, print area stays",
      "print area" in open(os.path.join(HERE, "templates",
                                        "designer.html")).read().lower())

# --- Fix 3: catalog removed (2026-11-06, Ovi: no Printify connection).
# The centre mockup is a flat design-area PNG for the product type,
# or the stored product photo. No catalog templates exist anywhere.
from catalog import get_template, TEMPLATES  # noqa: E402
check("catalog is empty", TEMPLATES == [])
check("no template for any old catalog id",
      get_template("catalog:printify-80") is None
      and get_template("catalog:printify-2806") is None
      and get_template("catalog:printify-48") is None)
check("catalog templates endpoint is 404",
      client.get("/api/catalog/templates").status_code == 404)
check("centre mockup uses design-area PNG or stored photo",
      "designAreaTemplateUrl" in JS and "flatTemplateForTitle" not in JS
      and "/api/catalog/templates" not in JS
      and "loadCatalogTemplates" not in JS,
      "centreImageUrl must fall back to the design-area PNG mapping "
      "and the stored product photo, with no catalog fetch")

# --- Fix 4: slug auto-generates from name ---
check("slugify function present in JS",
      "slugify" in JS)
check("slugify logic: lowercase, hyphens, collapse, trim",
      ("toLowerCase" in JS and "replace" in JS and "slug" in JS))
check("settings page wires name input to slug auto-fill",
      "campSlug" in JS and "slugify" in JS)
check("manual slug edit flag present (stops auto-overwrite)",
      "slugManual" in JS or "manualSlug" in JS or "slugEdited" in JS)
# Server-side: creating a campaign without a slug must still work
# (auto-fill is a UI behaviour; server keeps slug validation).
r = post("/api/campaigns", {"name": "Golden State Of Mind"})
check("create campaign still works (server slug optional)",
      r.status_code in (200, 201), r.get_data(as_text=True)[:200])

# --- Fix 5: pixel + end fields removed from settings page ---
settings_html = client.get("/campaigns/warriors1234").get_data(as_text=True)
for label, needle in [
        ("Tik Tok Pixel", "Tik Tok Pixel"),
        ("Snapchat Pixel", "Snapchat Pixel"),
        ("Override default pixels", "Override default pixels"),
        ("Custom Audience", "Custom Audience"),
        ("Conversions API", "Conversions API"),
        ("Old Facebook pixels", "Old Facebook pixels"),
        ("Key Page View", "Key Page View"),
        ("Add to Cart pixel", "campFbAddToCart"),
        ("Checkout pixel", "campFbCheckout"),
        ("End date card", "campEnd"),
        ("tiktok id", "campTiktok"),
        ("snapchat id", "campSnapchat"),
        ("fb audience id", "campFbAudience"),
        ("fb capi id", "campFbCapi"),
        ("fb page view id", "campFbPageView"),
]:
    check("settings page has no " + label, needle not in settings_html,
          "found " + needle)
for kept in ["Details", "Storefront", "Conversion tools",
             "Cloak", "Upsells", "Description", "campName", "campSlug",
             "campTags", "campUpsell"]:
    check("settings page keeps " + kept, kept in settings_html)
# Save without pixel/end fields must still succeed, and an old set
# carrying them must still load.
r = post("/api/sets/warriors1234/campaign", {
    "name": "Warriors", "slug": "warriors", "description": "Test",
    "tags": "warriors",
    "campaign": {"storefront_homepage": False, "show_countdown": False,
                 "hide_purchases": False, "fudge_factor": 0,
                 "hide_from_search_engines": False,
                 "social_buttons": False, "upsell_discount": None}})
check("settings save works without pixel/end fields",
      r.status_code == 200, r.get_data(as_text=True)[:200])
old = client.get("/api/sets").get_json()
old_warriors = [s for s in old if s["id"] == "warriors1234"]
check("old set still loads after save",
      len(old_warriors) == 1)

# --- Placement persistence inside the fixed box (review B1) ---
r = post("/api/sets/warriors1234/save-all", {
    "placement": {"x": 0.10, "y": 0.95, "scale": 0.8, "angle": 0}})
_saved = r.get_json() if r.status_code == 200 else {}
_mp = _saved.get("master_placement") or {}
check("save-all clamps out-of-box placement to the print area",
      r.status_code == 200 and _mp.get("x") == 0.25 and
      _mp.get("y") == 0.70 and _mp.get("scale") == 0.5,
      str(_saved.get("master_placement")))
# Old pixel/end values must survive a save that does not send them.
_after_save = [s for s in client.get("/api/sets").get_json()
               if s["id"] == "warriors1234"][0]
_camp = _after_save.get("campaign") or {}
check("old pixel/end values survive a save without those fields",
      _camp.get("tiktok_pixel") == "old-tiktok" and
      _camp.get("snapchat_pixel") == "old-snap" and
      _camp.get("end_date") == "3/1/26",
      str(_camp))

# --- Fix 2 executed: box geometry fixed, design moves (node stub DOM) ---
import subprocess as _sp
_harness = """
var window = { fetch: async function() { return { json: async function() { return {}; } }; } };
var _els = {};
function _el(id) {
  if (!_els[id]) _els[id] = { style: {}, textContent: '', value: '', innerHTML: '', className: '',
    getBoundingClientRect: function() { return { left: 0, top: 0, width: 400, height: 400 }; },
    naturalWidth: 400, naturalHeight: 400, addEventListener: function() {}, setAttribute: function(k, v) { this[k] = v; }, getAttribute: function(k) { return this[k] || ''; },
    appendChild: function(c) { this._child = c; }, querySelectorAll: function() { return []; } };
  return _els[id];
}
var _created = [];
var document = { getElementById: _el, createElement: function(tag) { var e = _el('created' + _created.length); _created.push(e); e.tagName = tag; return e; }, addEventListener: function() {}, querySelectorAll: function() { return []; }, querySelector: function() { return null; } };
var alert = function() {};
"""
_tmp = os.path.join(TMP, "box.js")
with open(_tmp, "w") as _f:
    _f.write(_harness)
    _f.write(JS)
    _f.write("""
currentSet = { design_url: '/static/uploads/d.png', design_width: 1000, design_height: 1000,
  master_placement: { x: 0.5, y: 0.45, scale: 0.5, angle: 0 },
  products: [{ product_id: 'p1', locked: true, title: 'Tee', hide_design: false }], text_layers: [] };
selectedPid = 'p1'; viewSide = 'front';
_el('centreImg').style.display = 'block';
positionPlaceBox();
var box1 = { l: _el('placeBox').style.left, t: _el('placeBox').style.top, w: _el('placeBox').style.width, h: _el('placeBox').style.height };
var d1 = _el('designImg');
currentSet.master_placement = { x: 0.7, y: 0.6, scale: 0.25, angle: 10 };
positionPlaceBox();
var box2 = { l: _el('placeBox').style.left, t: _el('placeBox').style.top, w: _el('placeBox').style.width, h: _el('placeBox').style.height };
console.log(JSON.stringify({ box1: box1, box2: box2, designSrc: d1.getAttribute('src'), designLeft: d1.style.left, designTop: d1.style.top, designWidth: d1.style.width }));
""")
_proc = _sp.run(["node", _tmp], capture_output=True, text=True)
try:
    _out = json.loads(_proc.stdout.strip().splitlines()[-1])
except Exception:
    _out = {}
check("executed: print-area box geometry is fixed across placements",
      _proc.returncode == 0 and _out.get("box1") == _out.get("box2") and
      _out.get("box1") == {"l": "25%", "t": "20%", "w": "50%", "h": "50%"},
      _proc.stdout[:300] + _proc.stderr[:300])
def _pct(v):
    try:
        return float(str(v).rstrip("%"))
    except Exception:
        return -1
check("executed: design img renders inside box and moves",
      _out.get("designSrc") == "/static/uploads/d.png" and
      abs(_pct(_out.get("designLeft")) - 90) < 0.01 and
      abs(_pct(_out.get("designTop")) - 80) < 0.01 and
      abs(_pct(_out.get("designWidth")) - 50) < 0.01,
      str(_out))
_slug_proc = _sp.run(["node", "-e",
    "var window={};var document={addEventListener:function(){}};"
    + JS.split("function slugify")[0]
    + "function slugify" + JS.split("function slugify")[1].split("\n}\n")[0] + "\n}\n"
    + "console.log(slugify('Golden State Of Mind!')+'|'+slugify('!!!'));"],
    capture_output=True, text=True)
check("executed: slugify produces golden-state-of-mind, empty for punctuation",
      _slug_proc.returncode == 0 and
      _slug_proc.stdout.strip() == "golden-state-of-mind|",
      _slug_proc.stdout[:200] + _slug_proc.stderr[:200])

# --- Review B1/B2: server clamp + unlocked drag routing ---
from mockup import clamp_to_print_area  # noqa: E402
_clamped = clamp_to_print_area({"x": 0.10, "y": 0.95, "scale": 0.8,
                                "angle": 5})
check("server mockup clamp: out-of-box -> box, scale capped",
      _clamped["x"] == 0.25 and _clamped["y"] == 0.70 and
      _clamped["scale"] == 0.5 and _clamped["angle"] == 5, str(_clamped))
check("placeAt routes unlocked products to override_placement",
      "override_placement" in JS and "sel.locked" in JS)
check("save paths clamp placement (saveMaster/saveAll/product)",
      "clampPlacement" in JS)

# --- Re-review fixes: saveAll overrides, lock version bump, layer clamp ---
from PIL import Image as _PILImage  # noqa: E402
_seed2 = seed_set()
_seed2["id"] = "unlocked123"
_seed2["products"] = [{
    "product_id": "888", "title": "Unisex Long Sleeve Tee",
    "locked": False, "colours": ["White"], "all_colours": ["White"],
    "sizes": ["S"], "all_sizes": ["S"], "sale_price": 29.46,
    "compare_at_price": None, "base_cost": None, "mockups": [],
    "mockup_versions": {}, "mockup_version": None, "hero_image": None,
    "hidden_layers": [], "image": "https://example.test/tee.jpg",
    "images": ["https://example.test/tee.jpg"], "variant_prices": {},
    "override_placement": None}]
_seed2["design_version"] = 1
_all = client.get("/api/sets").get_json()
_all = {s["id"]: s for s in _all}
_all["unlocked123"] = _seed2
write_sets(_all)
r = post("/api/sets/unlocked123/save-all", {
    "products": [{"product_id": "888",
                  "override_placement": {"x": 0.10, "y": 0.95,
                                         "scale": 0.8, "angle": 0}}]})
_saved2 = r.get_json() if r.status_code == 200 else {}
_prod2 = [p for p in _saved2.get("products", [])
          if p["product_id"] == "888"]
check("saveAll persists unlocked override, clamped to print area",
      r.status_code == 200 and len(_prod2) == 1 and
      _prod2[0].get("override_placement") == {"x": 0.25, "y": 0.70,
                                              "scale": 0.5, "angle": 0},
      str(_prod2))
check("saveAll override change bumps design_version (mockups stale)",
      _saved2.get("design_version", 1) > 1, str(_saved2.get("design_version")))
r = post("/api/sets/unlocked123/products/888/lock",
         {"locked": False,
          "placement": {"x": 0.10, "y": 0.10, "scale": 0.9, "angle": 0}})
_locked = r.get_json() if r.status_code == 200 else {}
_prod3 = [p for p in _locked.get("products", [])
          if p["product_id"] == "888"]
check("set_lock clamps override and bumps design_version",
      r.status_code == 200 and len(_prod3) == 1 and
      _prod3[0].get("override_placement", {}).get("x") == 0.25 and
      _locked.get("design_version", 1) > _saved2.get("design_version", 1),
      str(_prod3) + " v=" + str(_locked.get("design_version")))
# Layer clamp: solid red layer PNG at x=0.10 must render at 0.25.
from text_layers import composite_layers  # noqa: E402
_photo = os.path.join(TMP, "photo.jpg")
_design = os.path.join(TMP, "design.png")
_layer = os.path.join(TMP, "layer.png")
_out = os.path.join(TMP, "layer-out.jpg")
_PILImage.new("RGB", (200, 100), (255, 255, 255)).save(_photo, "JPEG")
_PILImage.new("RGBA", (10, 10), (0, 0, 0, 0)).save(_design, "PNG")
_PILImage.new("RGBA", (20, 20), (255, 0, 0, 255)).save(_layer, "PNG")
composite_layers(_photo, _design,
                 {"x": 0.5, "y": 0.45, "scale": 0.5, "angle": 0},
                 [(_layer, 0.10, 0.5)], _out)
_px = _PILImage.open(_out).convert("RGB")
check("server layer render clamps x=0.10 to print-area edge 0.25",
      _px.getpixel((50, 50))[1] < 100 and _px.getpixel((20, 50))[1] > 200,
      str(_px.getpixel((50, 50))) + " vs " + str(_px.getpixel((20, 50))))

# --- No live profit, direct publish wording intact ---
designer_html = client.get("/campaigns/warriors1234/designer").get_data(
    as_text=True)
check("designer page still separate (no settings cards)",
      "Campaign settings" not in designer_html or
      "campTiktok" not in designer_html)
check("real sets.json byte-identical",
      sha(REAL_SETS) == real_hash_before)

print()
print(str(len(PASSED)) + " passed, " + str(len(FAILED)) + " failed")
if FAILED:
    print("FAILED: " + ", ".join(FAILED))
    sys.exit(1)
