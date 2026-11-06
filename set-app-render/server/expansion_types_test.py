"""Tests for the catalog removal (2026-11-06, Ovi: the app must have
no Printify connection). The 3 Printify catalog templates are gone.

Run from the repo root or the server folder:
    python server/expansion_types_test.py

Checks, with no network and no real Shopify (mock-free: only dry-run
publish is called, which never contacts Shopify):
  1. The catalog is empty: TEMPLATES == [], get_template returns None
     for the old catalog ids, and catalog.py source contains no
     Printify data (no "printify", blueprint, provider or
     images.printify.com references). match_template_for_title and
     template_entry no longer exist.
  2. The frontend no longer fetches or renders catalog templates:
     no /api/catalog/templates fetch, no loadCatalogTemplates, no
     flatTemplateForTitle, no "Catalog products" card in the designer.
     The design-area PNG mapping (long sleeve / v-neck) is still there.
  3. The four design-area template images (crewneck, long sleeve,
     v-neck, hoodie) contain no baked-in dashed print-area box: no red
     pixels, a small fixed grey palette, and no ghost dashes along the
     old box edges. The app's own placebox is the only dashed area.
  4. The catalog endpoints are gone (404) and the Grouped guard fix
     still holds, proved with a plain synthetic 144-variant product
     (no catalog): Grouped allows it, while Combine and Split keep
     their guards (regression).
Writes only to a temporary data directory, never to data/sets.json.
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_TMP = tempfile.mkdtemp(prefix="expansion_types_")
os.environ["SETAPP_DATA_ROOT"] = _TMP
os.environ.pop("SET_APP_PASSWORD", None)

import numpy as np
from PIL import Image

import app as app_module
import catalog

app_module.DATA_FILE = os.path.join(_TMP, "sets.json")
app_module.UPLOAD_DIR = os.path.join(_TMP, "uploads")
app_module.MOCKUP_DIR = os.path.join(_TMP, "mockups")

passed = 0
failed = []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(name + (" :: " + str(detail) if detail else ""))


# ---------------------------------------------------------------- 1
check("catalog TEMPLATES empty", catalog.TEMPLATES == [],
      catalog.TEMPLATES)
for pid in ("catalog:printify-80", "catalog:printify-2806",
            "catalog:printify-48", "catalog:anything"):
    check("get_template(%s) is None" % pid,
          catalog.get_template(pid) is None)
check("match_template_for_title removed",
      not hasattr(catalog, "match_template_for_title"))
check("template_entry removed", not hasattr(catalog, "template_entry"))
_src = open(os.path.join(HERE, "catalog.py")).read()
for needle in ("printify", "blueprint", "provider",
               "images.printify.com", "Gildan", "Bella"):
    check("catalog.py has no %r" % needle,
          needle.lower() not in _src.lower(), needle)

# ---------------------------------------------------------------- 2
js = open(os.path.join(HERE, "static", "app.js")).read() \
    if os.path.exists(os.path.join(HERE, "static", "app.js")) else ""
html = open(os.path.join(HERE, "templates", "designer.html")).read() \
    if os.path.exists(os.path.join(HERE, "templates",
                                   "designer.html")) else ""
if js:
    check("js maps long sleeve template", "longsleeve-front.png" in js)
    check("js maps v-neck template", "vneck-front.png" in js)
    check("js has no catalog fetch", "/api/catalog/templates" not in js)
    check("js has no loadCatalogTemplates", "loadCatalogTemplates" not in js)
    check("js has no flatTemplateForTitle", "flatTemplateForTitle" not in js)
    check("js has no catalogTemplates var", "catalogTemplates" not in js)
    check("js still uses design-area PNGs", "designAreaTemplateUrl" in js)
if html:
    check("designer has no Catalog products card",
          "Catalog products" not in html and "catalogList" not in html)

# ---------------------------------------------------------------- 3
TPL = os.path.join(HERE, "static", "design-area-templates")
BOXES = {  # old baked-in box: x0, x1, y0, y1
    "crewneck-front.png": (240, 761, 166, 533),
    "longsleeve-front.png": (240, 761, 153, 540),
    "vneck-front.png": (240, 761, 166, 533),
    "hoodie-front.png": (240, 761, 159, 479),
}
PALETTE = {140, 180, 240, 242, 250, 255}
for fname, (x0, x1, y0, y1) in BOXES.items():
    path = os.path.join(TPL, fname)
    check(fname + " exists", os.path.exists(path))
    if not os.path.exists(path):
        continue
    a = np.array(Image.open(path).convert("RGBA")).astype(int)
    r, g, b, al = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    check(fname + " no red pixels",
          int(((r > 150) & (g < 120) & (b < 120)).sum()) == 0)
    check(fname + " grey only", bool((r == g).all() and (g == b).all()))
    check(fname + " opaque", bool((al == 255).all()))
    L = r
    check(fname + " palette", set(np.unique(L).tolist()) <= PALETTE,
          sorted(set(np.unique(L).tolist()) - PALETTE))
    check(fname + " size", Image.open(path).size == (1000, 666))
    # ghost dashes: band pixel differs from equal neighbours 5px away
    ghost = 0
    H, W = L.shape
    for y in range(y0 - 4, y1 + 5):
        for x in range(x0 - 4, x1 + 5):
            on_h = abs(y - y0) <= 4 or abs(y - y1) <= 4
            on_v = abs(x - x0) <= 4 or abs(x - x1) <= 4
            v = L[y, x]
            if v in (140, 180):
                continue
            for dx, dy, on in ((0, 5, on_h), (5, 0, on_v)):
                if not on:
                    continue
                na, nb = L[y - dy, x - dx], L[y + dy, x + dx]
                if na == nb and na not in (140, 180) and na != v:
                    ghost += 1
                    break
    check(fname + " no ghost dashes", ghost <= 12, ghost)

# ---------------------------------------------------------------- 4
client = app_module.app.test_client()
tok = client.get("/api/csrf-token").get_json()["csrf_token"]
H = {"X-CSRF-Token": tok, "Content-Type": "application/json"}


def post(path, body=None):
    return client.post(path, data=json.dumps(body or {}), headers=H)


check("GET /api/catalog/templates is 404",
      client.get("/api/catalog/templates").status_code == 404)
r = post("/api/sets/no-such-set/catalog-templates", {"all": True})
check("POST catalog-templates is 404 (no such route)",
      r.status_code == 404, r.status_code)

r = post("/api/campaigns", {"name": "Expansion test", "slug": "expansion-test"})
check("campaign created", r.status_code == 201, r.status_code)
sid = r.get_json()["id"]
check("new campaign defaults grouped", r.get_json()["grouping"] == "grouped")
r = post("/api/sets", {"name": "Plain set"})
check("new set defaults grouped", r.get_json()["grouping"] == "grouped")
r = post("/api/sets/%s/catalog-templates" % sid, {"all": True})
check("POST catalog-templates on a real set is 404",
      r.status_code == 404, r.status_code)

# Grouped guard-fix regression, with a plain synthetic product (no
# catalog): 18 colours x 8 sizes = 144 variants, over 100 on its own.
big = {
    "product_id": "synthetic-144",
    "kind": "store",
    "title": "Synthetic 144-variant Long Sleeve",
    "colours": ["Ash", "Black", "Carolina Blue", "Dark Chocolate",
                "Dark Heather", "Forest Green", "Gold", "Irish Green",
                "Light Blue", "Light Pink", "Maroon", "Navy", "Purple",
                "Red", "Royal", "Safety Green", "Sport Grey", "White"],
    "sizes": ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
    "all_colours": ["Ash", "Black", "Carolina Blue", "Dark Chocolate",
                    "Dark Heather", "Forest Green", "Gold", "Irish Green",
                    "Light Blue", "Light Pink", "Maroon", "Navy", "Purple",
                    "Red", "Royal", "Safety Green", "Sport Grey", "White"],
    "all_sizes": ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
    "images": [], "image": None, "position": "front", "mockups": [],
    "hero_image": None, "locked": True, "override_placement": None,
    "sale_price": "27.00", "compare_at_price": None, "base_cost": None,
}
sets = app_module.load_sets()
sets[sid]["products"].append(big)
sets[sid]["design_url"] = "/static/uploads/fake.png"
app_module.save_sets(sets)

r = client.get("/api/sets/%s/variant-count" % sid)
vs = r.get_json()
check("grouped total 144", vs["total_combine"] == 144,
      vs.get("total_combine"))
check("grouped guard ok", vs["guard_ok"] is True)
msg = vs["message"].lower()
check("grouped message has no limit text",
      not any(w in msg for w in ("limit", "100", "95", "listings", "shopify")),
      vs["message"])
check("grouped message says one campaign link", "one campaign link" in msg)

r = post("/api/sets/%s/publish" % sid, {"dry_run": True})
j = r.get_json()
check("grouped dry-run publish allowed",
      r.status_code == 200, (r.status_code, j))
if r.status_code == 200:
    sizes = [len(p["variants"]) for p in j["products"]]
    check("grouped chunks sum to 144", sum(sizes) == 144, sizes)
    check("grouped chunks each <= 95", all(n <= 95 for n in sizes), sizes)
    check("grouped has 2 listings", len(sizes) == 2, sizes)
    blob = json.dumps(j.get("warnings", [])).lower() + \
        j["variant_summary"]["message"].lower()
    check("grouped preview shows no limit text",
          "limit" not in blob and "100-variant" not in blob, blob)

# regressions: combine and split keep their guards
sets = app_module.load_sets()
sets[sid]["grouping"] = "combine"
app_module.save_sets(sets)
r = post("/api/sets/%s/publish" % sid, {"dry_run": True})
check("combine over 100 still blocked", r.status_code == 400
      and "Combine mode" in r.get_json()["error"], r.get_json())
sets = app_module.load_sets()
sets[sid]["grouping"] = "split"
app_module.save_sets(sets)
r = post("/api/sets/%s/publish" % sid, {"dry_run": True})
check("split with a 144-variant product still blocked", r.status_code == 400
      and "Split mode" in r.get_json()["error"], r.get_json())

# real sets.json untouched
real = os.path.join(os.path.dirname(HERE), "data", "sets.json")
check("temp data dir used", app_module.DATA_FILE.startswith(_TMP))

print("%d passed, %d failed" % (passed, len(failed)))
for f in failed:
    print("FAIL:", f)
sys.exit(1 if failed else 0)
