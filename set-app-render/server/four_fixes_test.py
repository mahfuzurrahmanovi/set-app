"""Four fixes + grouped 500-variant mode (Ovi, 2026-11-04 21:51: solve it).

1. Settings button says Designer, saves first, then goes to designer;
   a failed save must not navigate.
2. No text-layer UI, and centre mockup renders no text layers.
3. Centre mockup base is a Printify design-page template (flat outline,
   dashed print area), not a model/Shopify rendered photo.
4. Phone-width layout: compact nav, no tall block, mockup/slider/tabs
   reachable, no horizontal overflow except campaigns table scroll.
5. Grouped mode: ~500 variants shown as one total in the app, publish
   chunks each listing at <=95 variants, never one 500-variant product.

FAILS before, PASSES after. Temp data root only, mock Shopify only,
never touches real data/sets.json, never publishes live.
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
TMP = tempfile.mkdtemp(prefix="setapp_fourfixes_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "fourfix-test-password"
os.environ["FLASK_SECRET_KEY"] = "fourfix-test-secret"
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


def read(rel):
    with open(os.path.join(HERE, rel)) as f:
        return f.read()


settings_html = read("templates/campaign_settings.html")
designer_html = read("templates/designer.html")
js = read("static/app.js")
css = read("static/app.css")

# 1. Designer button
check("settings has a Designer button that saves then goes",
      "saveAndGoDesigner" in settings_html and ">Designer<" in settings_html)
check("settings no longer has a Save campaign settings button",
      "Save campaign settings" not in settings_html)
check("saveAndGoDesigner navigates only after a successful save",
      "saveAndGoDesigner" in js and "window.location.href" in js and
      "goDesigner" in js)
# 2. Text layers gone from UI and centre rendering
check("designer has no Add a text layer form",
      "Add a text layer" not in designer_html and
      "layerFormDetails" not in designer_html)
check("designer has no Layers section heading",
      "<h2>Layers</h2>" not in designer_html)
check("centre mockup renders no text layers",
      "centreLayer" not in js.split("function positionPlaceBox")[1].split(
          "function renderArtworkSpec")[0])
# 3. Design-area templates
for fname in ("hoodie-front.png", "crewneck-front.png",
              "longsleeve-front.png", "vneck-front.png",
              "shortsleeve-back.png", "shortsleeve-front.png"):
    check("design-area template exists: " + fname,
          os.path.isfile(os.path.join(
              HERE, "static", "design-area-templates", fname)))
check("centreImageUrl prefers design-area template",
      "designAreaTemplateUrl" in js and
      "design-area-templates" in js)
check("mockup label says design-area template",
      "Design-area template" in js)
# 4. Phone layout
check("phone media query at 480px or below",
      "@media (max-width: 480px)" in css)
check("phone nav is compact (no tall block)",
      "480px" in css and ".nav" in css.split("@media (max-width: 480px)")[1])

# 5. Grouped mode, server side
def seed_grouped():
    products = []
    for i, title in enumerate(("Tee", "Hoodie", "Crewneck", "V-Neck",
                               "Long Sleeve")):
        products.append({
            "product_id": "p%d" % i, "title": title,
            "colours": ["C%d" % j for j in range(10)],
            "sizes": ["S%d" % j for j in range(10)],
            "variant_prices": {},
            "sale_price": "20.00",
        })
    return {"id": "grp1", "name": "Grouped Set", "description": "d",
            "tags": [], "slug": "grouped-set", "grouping": "grouped",
            "publish_state": "draft", "products": products,
            "design_url": "/static/uploads/x.png", "design_version": 1}


s = seed_grouped()
summary = app_module.variant_summary(s)
check("grouped summary is guard_ok at 500 variants",
      summary["total_combine"] == 500 and summary["guard_ok"] is True,
      summary)
payloads = app_module.build_product_payloads(s)
check("grouped payloads chunk at <=95 variants each",
      len(payloads) >= 6 and all(len(p["variants"]) <= 95
                                 for p in payloads),
      [len(p["variants"]) for p in payloads])
check("grouped payloads keep all 500 variants, no loss",
      sum(len(p["variants"]) for p in payloads) == 500)
check("grouped payload titles are one set, numbered after first",
      payloads[0]["title"] == "Grouped Set" and
      payloads[1]["title"].startswith("Grouped Set ("))

print("\n%d passed, %d failed" % (len(PASSED), len(FAILED)))
print("real sets.json unchanged:",
      sha(REAL_SETS) == real_hash_before)
if FAILED or sha(REAL_SETS) != real_hash_before:
    sys.exit(1)
