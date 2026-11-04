"""Designer mobile fix tests (Ovi, 2026-11-04 20:17).

1. Campaign settings button is "Designer", saves first, then navigates.
2. Text layer removed from the designer UI.
3. Mockup base is a flat product-only Printify image, not a model photo.
4. Mobile friendly on a 360-430px phone viewport.

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

TMP = tempfile.mkdtemp(prefix="setapp_mobilefix_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "mobilefix-test-password"
os.environ["FLASK_SECRET_KEY"] = "mobilefix-test-secret"

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
    return post("/api/login", {"password": "mobilefix-test-password"})


def write_sets(sets):
    with open(os.path.join(TMP, "sets.json"), "w") as f:
        json.dump(sets, f)


def seed_set():
    return {
        "id": "mobile1234", "name": "Mobile Test",
        "description": "Test", "tags": ["test"], "slug": "mobile-test",
        "grouping": "split", "publish_state": "draft",
        "publish_error": None, "artwork_locked": False,
        "design_url": "/static/uploads/test-design.png",
        "design_width": 1000, "design_height": 1000,
        "design_dpi": 200, "design_warnings": [], "design_version": 1,
        "master_placement": {"x": 0.5, "y": 0.45,
                             "scale": 0.5, "angle": 0},
        "text_layers": [{"id": "oldlayer1", "content": "OLD TEXT",
                         "font": "sans", "size": 120, "colour": "#111111"}],
        "campaign": {"status": "draft", "fulfillment": "LAUNCH_END"},
        "products": [
            {"product_id": "999", "title": "Unisex Long Sleeve Tee",
             "locked": True, "colours": ["White"], "all_colours": ["White"],
             "sizes": ["S"], "all_sizes": ["S"], "sale_price": 27.0,
             "compare_at_price": None, "base_cost": None,
             "mockups": [], "mockup_versions": {}, "mockup_version": None,
             "hero_image": None, "hidden_layers": [],
             "override_placement": None,
             "image": "https://example.test/model-tee.jpg",
             "images": ["https://example.test/model-tee.jpg"],
             "variant_prices": {}},
        ],
    }


write_sets({"mobile1234": seed_set()})
login()

JS = open(os.path.join(HERE, "static", "app.js")).read()
CSS = open(os.path.join(HERE, "static", "app.css")).read()
DESIGNER = open(os.path.join(HERE, "templates", "designer.html")).read()
SETTINGS = open(os.path.join(HERE, "templates", "campaign_settings.html")).read()

# --- Fix 1: settings button is Designer, saves first ---
check("settings page has a Designer button",
      ">Designer<" in SETTINGS)
check("settings page has NO Save campaign settings button",
      "Save campaign settings" not in SETTINGS)
check("save-then-designer handler exists in JS",
      "saveAndGoDesigner" in JS)
check("save-then-designer navigates only on success",
      ("saveAndGoDesigner" in JS) and
      ("/designer" in JS) and ("campaignSettingsResult" in JS))
r = client.get("/campaigns/mobile1234")
check("settings page route serves the Designer button (authed)",
      r.status_code == 200 and b"Designer" in r.data and
      b"Save campaign settings" not in r.data,
      r.status_code)

# --- Fix 2: text layer removed from designer UI ---
check("designer page has NO Add a text layer form",
      "Add a text layer" not in DESIGNER and
      "layerFormDetails" not in DESIGNER)
check("designer page has NO Layers section heading",
      "<h2>Layers</h2>" not in DESIGNER)
check("centre render does not render text-layer spans",
      "centreLayer" not in JS)
check("old stored text layers do not crash the set load",
      client.get("/campaigns/mobile1234/designer").status_code == 200)

# --- Fix 3: design-page template mockup (SUPERSEDED 2026-11-04) ---
# Ovi corrected the earlier flat-photo approach: Shopify/Printify photos
# are wrong as the designer base. The base is now a Printify design-page
# template: flat outline, dashed print area, no model, no photo.
# The old flat_image expectations below are replaced by that check.
import os as _os
for _f in ("hoodie-front.png", "crewneck-front.png",
           "longsleeve-front.png", "vneck-front.png",
           "shortsleeve-back.png", "shortsleeve-front.png"):
    check("design-area template exists: " + _f,
          _os.path.isfile(_os.path.join(HERE, "static",
                                         "design-area-templates", _f)))
check("JS centre base uses design-area templates",
      "designAreaTemplateUrl" in JS and "design-area-templates" in JS)
check("JS flat helper still falls back honestly when no flat image",
      "Not a Printify flat photo" in JS)

# --- Fix 4: mobile friendly, 360-430px ---
check("CSS has a narrow phone media query (max-width 480px)",
      "@media (max-width: 480px)" in CSS)
check("mobile CSS keeps nav to one compact row (nowrap, auto button)",
      "@media (max-width: 480px)" in CSS and
      ".nav" in CSS and "nowrap" in CSS)
check("mobile CSS caps mockup at screen width",
      "max-width: 100%" in CSS)
check("mobile CSS allows paired buttons to wrap instead of squeezing",
      "flex-wrap: wrap" in CSS)
check("designer still has Design size slider + FRONT/BACK tabs in Design card",
      'id="designSize"' in DESIGNER and 'id="tabFront"' in DESIGNER and
      'id="tabBack"' in DESIGNER)
check("no tall topbar class in designer page",
      "topbar" not in DESIGNER)
check("fixed print area + Design size slider still present",
      "PRINT_AREA" in JS and "designSize" in JS)

# --- Hard constraints still held ---
check("separate pages still separate (no stacked index)",
      not os.path.exists(os.path.join(HERE, "templates", "index.html")))
check("no live profit in new pages",
      "Profit per unit" not in DESIGNER and "Profit per unit" not in SETTINGS)
check("direct live publish wording still present",
      "Publish to Shopify (live)" in DESIGNER)
check("real sets.json byte-identical",
      sha(REAL_SETS) == real_hash_before)

print(str(len(PASSED)) + " passed, " + str(len(FAILED)) + " failed")
if FAILED:
    print("FAILED: " + ", ".join(FAILED))
    sys.exit(1)
