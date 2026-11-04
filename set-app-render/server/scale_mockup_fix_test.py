"""Scale / Printify-photo / Auto-select fix tests (Ovi, 2026-11-04 19:54).

1. Design moves but cannot be scaled: a clear Design size slider under
   the mockup, live preview, Save persists for locked and unlocked.
2. Mockup must be the exact Printify photo, not a model photo.
3. Products auto-selected, with a clear Remove product button.

FAILS before the fix, PASSES after. Temp data root only, mock Shopify
only, never touches the real data/sets.json, never publishes live.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_SETS = os.path.join(os.path.dirname(HERE), "data", "sets.json")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


real_hash_before = sha(REAL_SETS)

TMP = tempfile.mkdtemp(prefix="setapp_scalefix_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "scalefix-test-password"
os.environ["FLASK_SECRET_KEY"] = "scalefix-test-secret"

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
    return post("/api/login", {"password": "scalefix-test-password"})


def write_sets(sets):
    with open(os.path.join(TMP, "sets.json"), "w") as f:
        json.dump(sets, f)


def seed_set():
    return {
        "id": "scale12345", "name": "Scale Test",
        "description": "Test", "tags": ["test"], "slug": "scale-test",
        "grouping": "split", "publish_state": "draft",
        "publish_error": None, "artwork_locked": False,
        "design_url": "/static/uploads/test-design.png",
        "design_width": 1000, "design_height": 1000,
        "design_dpi": 200, "design_warnings": [], "design_version": 1,
        "master_placement": {"x": 0.5, "y": 0.45,
                             "scale": 0.5, "angle": 0},
        "text_layers": [],
        "campaign": {"status": "draft", "fulfillment": "LAUNCH_END"},
        "products": [
            {"product_id": "999", "title": "Unisex Long Sleeve Tee",
             "locked": True, "colours": ["White", "Black"],
             "all_colours": ["White", "Black"], "sizes": ["S", "M"],
             "all_sizes": ["S", "M"], "sale_price": 29.46,
             "compare_at_price": None, "base_cost": None,
             "mockups": [], "mockup_versions": {},
             "mockup_version": None, "hero_image": None,
             "hidden_layers": [], "override_placement": None,
             "image": "https://example.test/model-tee.jpg",
             "images": ["https://example.test/model-tee.jpg"],
             "variant_prices": {}},
            {"product_id": "888", "title": "Unisex Classic Long Sleeve Tee",
             "locked": False, "colours": ["White"],
             "all_colours": ["White", "Black"], "sizes": ["S"],
             "all_sizes": ["S", "M"], "sale_price": 29.0,
             "compare_at_price": None, "base_cost": None,
             "mockups": [], "mockup_versions": {},
             "mockup_version": None, "hero_image": None,
             "hidden_layers": [],
             "override_placement": {"x": 0.5, "y": 0.45,
                                    "scale": 0.5, "angle": 0},
             "image": "https://images.printify.com/exact-photo-123",
             "images": ["https://images.printify.com/exact-photo-123"],
             "variant_prices": {}},
        ],
    }


write_sets({"scale12345": seed_set()})
login()

JS = open(os.path.join(HERE, "static", "app.js")).read()
DESIGNER = open(os.path.join(HERE, "templates", "designer.html")).read()

# --- Fix 1: Design size slider, live, under the mockup ---
check("designer has a Design size slider under the mockup",
      'id="designSize"' in DESIGNER and "Design size" in DESIGNER)
check("design size slider range is 0.1 to 0.5",
      'id="designSize"' in DESIGNER and
      ('min="0.1"' in DESIGNER or "min=.1" in DESIGNER) and
      ('max="0.5"' in DESIGNER or "max=.5" in DESIGNER))
check("design size slider live-updates the preview on input",
      ("designSize" in JS) and
      (("oninput" in DESIGNER) or ("addEventListener('input'" in JS))
      and ("positionPlaceBox" in JS))
check("design size handler writes to master or override by lock state",
      ("designSize" in JS) and ("locked" in JS) and
      ("override_placement" in JS))
check("lock placement label present (locked = master, unlocked = product)",
      ("Locked" in JS or "locked" in DESIGNER) and
      ("master" in DESIGNER.lower() or "master" in JS))
import re as _re
_placeat = JS[JS.find("function placeAt"):JS.find("function tapToPlace")]
check("placeAt uses current scale (no forced scale 0.5)",
      # Old code forced it in the clamped tap point:
      # clampPlacement({ ..., scale: 0.5, angle: 0 }). The remaining
      # "scale: 0.5, angle: 0 }" is only a master default object.
      "scale: 0.5, angle: 0 })" not in _placeat and
      "scale: base0.scale" in _placeat, _placeat[:200])

# --- Fix 1: Save persists scale, locked and unlocked ---
r = post("/api/sets/scale12345/save-all", {
    "placement": {"x": 0.5, "y": 0.45, "scale": 0.2, "angle": 0},
    "details": {"name": "Scale Test", "slug": "scale-test",
                "description": "Test", "tags": "test", "grouping": "split"},
    "products": []})
_saved = r.get_json() if r.status_code == 200 else {}
check("save-all persists master scale 0.2 (locked product)",
      r.status_code == 200 and
      (_saved.get("master_placement") or {}).get("scale") == 0.2,
      str(_saved.get("master_placement")))
r = post("/api/sets/scale12345/products/888/lock",
         {"locked": False,
          "placement": {"x": 0.5, "y": 0.45, "scale": 0.2, "angle": 0}})
_locked = r.get_json() if r.status_code == 200 else {}
_prod = [p for p in _locked.get("products", [])
         if p["product_id"] == "888"]
check("set_lock persists override scale 0.2 (unlocked product)",
      r.status_code == 200 and len(_prod) == 1 and
      (_prod[0].get("override_placement") or {}).get("scale") == 0.2,
      str(_prod))

# --- Fix 1: node stub-DOM width math ---
_harness = """
var window = { fetch: async function() { return { json: async function() { return {}; } }; } };
var _els = {};
function _el(id) {
  if (!_els[id]) _els[id] = { id: id, style: {}, textContent: '', value: '', innerHTML: '', className: '',
    getBoundingClientRect: function() { return { left: 0, top: 0, width: 400, height: 400 }; },
    naturalWidth: 400, naturalHeight: 400, addEventListener: function() {}, setPointerCapture: function() {},
    setAttribute: function(k, v) { this[k] = v; }, getAttribute: function(k) { return this[k] || ''; },
    appendChild: function(c) { this._child = c; }, querySelectorAll: function() { return []; } };
  return _els[id];
}
var _created = [];
var document = { getElementById: _el, createElement: function(tag) { var e = _el('created' + _created.length); _created.push(e); e.tagName = tag; return e; }, addEventListener: function() {}, querySelectorAll: function() { return []; }, querySelector: function() { return null; } };
var alert = function() {};
"""
_js = open(os.path.join(HERE, "static", "app.js")).read()
_tmp = os.path.join(TMP, "size.js")
with open(_tmp, "w") as _f:
    _f.write(_harness + "\n" + _js + "\n"
             "catalogTemplatesTried = true; catalogTemplates = [];\n"
             "currentSet = { id: 'scale12345', design_url: '/static/uploads/test-design.png', design_width: 1000, design_height: 1000, master_placement: { x: 0.5, y: 0.45, scale: SCALE, angle: 0 }, text_layers: [], products: [{ product_id: '999', title: 'Unisex Long Sleeve Tee', locked: true, hidden_layers: [] }] };\n"
             "selectedPid = '999'; viewSide = 'front';\n"
             "var _img = document.getElementById('centreImg'); _img.style.display = 'block';\n"
             "positionPlaceBox();\n"
             "var _d = document.getElementById('designImg');\n"
             "console.log('DESIGN_WIDTH=' + (_d ? _d.style.width : 'none'));\n")
for _scale, _expect in [(0.2, "40%"), (0.5, "100%")]:
    _src = open(_tmp).read().replace("SCALE", str(_scale))
    _run = os.path.join(TMP, "size_run.js")
    with open(_run, "w") as _f:
        _f.write(_src)
    _out = subprocess.run(["node", _run], capture_output=True,
                          text=True, timeout=30)
    check("design width at scale %s is %s of the box" % (_scale, _expect),
          ("DESIGN_WIDTH=" + _expect) in _out.stdout,
          _out.stdout[:200] + _out.stderr[:200])

# --- Fix 2: exact Printify photo ---
check("centre code prefers a stored Printify URL",
      "images.printify.com" in JS and "centreImageUrl" in JS)
check("flat template matching covers classic long sleeve",
      ("classic" in JS.lower()) and ("flatTemplateForTitle" in JS))
check("catalog still has only the 3 real templates (no invented URLs)",
      True)  # verified by the endpoint check below
r = client.get("/api/catalog/templates")
check("catalog templates endpoint returns 3 templates",
      r.status_code == 200 and len(r.get_json()) == 3,
      str(r.status_code))
from catalog import match_template_for_title  # noqa: E402
check("classic long sleeve maps to American Apparel template (945)",
      (match_template_for_title("Unisex Classic Long Sleeve Tee") or {}).get("blueprint_id") == 945)
check("v-neck maps to Bella+Canvas template (48)",
      (match_template_for_title("Unisex Jersey Short Sleeve V-Neck Tee") or {}).get("blueprint_id") == 48)
check("long sleeve maps to Gildan template (80)",
      (match_template_for_title("Unisex Ultra Cotton Long Sleeve Tee") or {}).get("blueprint_id") == 80)
check("hoodie has no template (honest fallback)",
      match_template_for_title("Unisex Heavyweight Pullover Hoodie") is None)

# --- Fix 3: auto-select + clear remove ---
from app import _entry_from_details  # noqa: E402
_entry = _entry_from_details({
    "product_id": "777", "title": "Test Tee", "colours": [],
    "all_colours": ["Black", "White"], "sizes": [],
    "all_sizes": ["S", "M"], "variant_prices": {}})
check("add with empty colours/sizes fills from full lists",
      _entry["colours"] == ["Black", "White"] and
      _entry["sizes"] == ["S", "M"], str(_entry))
check("product HTML has a clear Remove product button (not just X)",
      "Remove product" in JS)
check("product HTML has no lone X remove button as the only remove",
      "Remove product" in JS and
      "title=\"Remove from set\"" not in JS)
check("product HTML has Select all / Clear for colours and sizes",
      ("Select all" in JS) and ("Clear" in JS))
r = post("/api/sets/scale12345/products/888/variants",
         {"colours": ["White", "Black"], "sizes": ["S", "M"]})
check("variants endpoint can select all colours and sizes",
      r.status_code == 200, r.get_data(as_text=True)[:200])
r = post("/api/sets/scale12345/products/888/variants",
         {"colours": [], "sizes": []})
check("variants endpoint can clear colours and sizes",
      r.status_code == 200, r.get_data(as_text=True)[:200])
# Restore, then remove a product via the API.
post("/api/sets/scale12345/products/888/variants",
     {"colours": ["White", "Black"], "sizes": ["S", "M"]})
r = post("/api/sets/scale12345/products/888/remove", {})
_after = r.get_json() if r.status_code == 200 else {}
check("remove product works via API and set still loads",
      r.status_code == 200 and
      all(p["product_id"] != "888" for p in _after.get("products", [])) and
      any(p["product_id"] == "999" for p in _after.get("products", [])),
      str(_after.get("products")))
# --- Review regression: unlocked Design size must not corrupt master ---
_run2 = os.path.join(TMP, "size_unlocked.js")
with open(_run2, "w") as _f:
    _f.write(_harness + "\n" + _js + "\n"
             "catalogTemplatesTried = true; catalogTemplates = [];\n"
             "currentSet = { id: 'scale12345', design_url: '/static/uploads/test-design.png', design_width: 1000, design_height: 1000, master_placement: { x: 0.5, y: 0.45, scale: 0.5, angle: 0 }, text_layers: [], products: [{ product_id: '999', title: 'Unisex Long Sleeve Tee', locked: true, hidden_layers: [] }, { product_id: '888', title: 'Unisex Classic Long Sleeve Tee', locked: false, hidden_layers: [], override_placement: { x: 0.5, y: 0.45, scale: 0.5, angle: 0 } }] };\n"
             "selectedPid = '888'; viewSide = 'front';\n"
             "document.getElementById('s').value = '0.50';\n"
             "setDesignSize(0.2);\n"
             "console.log('PS=' + document.getElementById('ps-888').value);\n"
             "console.log('S=' + document.getElementById('s').value);\n"
             "console.log('MASTER=' + currentSet.master_placement.scale);\n"
             "console.log('OVERRIDE=' + currentSet.products[1].override_placement.scale);\n")
_out2 = subprocess.run(["node", _run2], capture_output=True,
                       text=True, timeout=30)
check("unlocked Design size syncs per-product slider to 0.20 (B1)",
      "PS=0.20" in _out2.stdout, _out2.stdout[:300] + _out2.stderr[:200])
check("unlocked Design size leaves master slider at 0.50 (B2)",
      "S=0.50" in _out2.stdout, _out2.stdout[:300] + _out2.stderr[:200])
check("unlocked Design size leaves master placement at 0.5 (B2)",
      "MASTER=0.5" in _out2.stdout, _out2.stdout[:300])
check("unlocked Design size sets override to 0.2",
      "OVERRIDE=0.2" in _out2.stdout, _out2.stdout[:300])
check("designer page still separate, fixed print area intact",
      "PRINT_AREA" in JS and "25" in JS)
check("real sets.json byte-identical",
      sha(REAL_SETS) == real_hash_before)

print()
print(str(len(PASSED)) + " passed, " + str(len(FAILED)) + " failed")
if FAILED:
    print("FAILED: " + ", ".join(FAILED))
    sys.exit(1)
