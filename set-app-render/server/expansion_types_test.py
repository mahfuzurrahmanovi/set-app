"""Tests for the 7-type expansion round (2026-11-06), updated to Ovi's
decided spec the same day.

Run from the repo root or the server folder:
    python server/expansion_types_test.py

Checks, with no network and no real Shopify (mock-free: only dry-run
publish is called, which never contacts Shopify):
  1. The 3 new product types in catalog.py match the decided spec
     (blueprints 80/2806/48, provider 99, Ovi's Oregon colours,
     Long Sleeve S-5XL, Classic S-3XL, V-neck S-2XL, print areas
     from the provider-99 variants endpoint) and carry the per-type
     prices Ovi confirmed on 2026-11-06 (Long Sleeve $27, Classic
     $29, V-neck $29, all USD).
  2. Titles used for the new Oregon products pick the right flat
     design-area template and catalog template.
  3. The four design-area template images (crewneck, long sleeve,
     v-neck, hoodie) contain no baked-in dashed print-area box: no red
     pixels, a small fixed grey palette, and no ghost dashes along the
     old box edges. The app's own placebox is the only dashed area.
  4. Grouped mode: new campaigns default to grouped, and a grouped
     set with the 3 templates (138 grid variants) previews and chunks
     cleanly with NO limit text. A synthetic 144-variant product is
     then added to prove the Grouped guard fix: Grouped still allows
     it, while Combine and Split keep their guards (regression).
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
T = {t["blueprint_id"]: t for t in catalog.TEMPLATES}
check("three templates", sorted(T) == [48, 80, 2806], sorted(T))
spec = {
    80: ("Gildan", "Unisex Ultra Cotton Long Sleeve Tee", 11, 8,
         (3033, 3442), "27.00", True),
    2806: ("Gildan", "Long Sleeve T-Shirt", 5, 6,
           (4500, 5100), "29.00", True),
    48: ("Bella+Canvas", "Unisex Jersey Short Sleeve V-Neck Tee", 4, 5,
         (3461, 3922), "29.00", True),
}
for bp, (brand, title, nc, ns, area, price, confirmed) in spec.items():
    t = T[bp]
    check("bp%d brand" % bp, t["brand"] == brand)
    check("bp%d title" % bp, t["title"] == title)
    check("bp%d provider 99" % bp, t["provider_id"] == 99)
    check("bp%d colours" % bp, len(t["colours"]) == nc, len(t["colours"]))
    check("bp%d sizes" % bp, len(t["sizes"]) == ns, len(t["sizes"]))
    check("bp%d print area" % bp,
          (t["print_area"]["width"], t["print_area"]["height"]) == area)
    check("bp%d suggested price" % bp, t.get("suggested_price") == price)
    check("bp%d price_confirmed" % bp, t.get("price_confirmed") is confirmed)
    e = catalog.template_entry(t)
    check("bp%d entry sale_price" % bp, e["sale_price"] == price)
    check("bp%d entry stays catalog" % bp,
          e["kind"] == "catalog" and e["template"] is True)
    check("bp%d entry all selected" % bp,
          e["colours"] == t["colours"] and e["sizes"] == t["sizes"])
    check("bp%d entry base_cost empty" % bp, e["base_cost"] is None)

# ---------------------------------------------------------------- 2
m = catalog.match_template_for_title
check("title long sleeve -> 80",
      m("Oregon Ducks Long Sleeve Tee")["blueprint_id"] == 80)
check("title classic -> 2806",
      m("Oregon Ducks Classic Long Sleeve Tee")["blueprint_id"] == 2806)
check("title v-neck -> 48", m("Oregon Ducks V-Neck Tee")["blueprint_id"] == 48)
check("title tee -> none", m("Oregon Ducks Unisex Tee") is None)

js = open(os.path.join(HERE, "static", "app.js")).read() \
    if os.path.exists(os.path.join(HERE, "static", "app.js")) else ""
if js:
    check("js maps long sleeve template", "longsleeve-front.png" in js)
    check("js maps v-neck template", "vneck-front.png" in js)

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


r = post("/api/campaigns", {"name": "Expansion test", "slug": "expansion-test"})
check("campaign created", r.status_code == 201, r.status_code)
sid = r.get_json()["id"]
check("new campaign defaults grouped", r.get_json()["grouping"] == "grouped")
r = post("/api/sets", {"name": "Plain set"})
check("new set defaults grouped", r.get_json()["grouping"] == "grouped")

r = post("/api/sets/%s/catalog-templates" % sid, {"all": True})
check("catalog add all", r.status_code == 200 and len(r.get_json()["added"]) == 3)
sets = app_module.load_sets()
sets[sid]["design_url"] = "/static/uploads/fake.png"
app_module.save_sets(sets)

r = client.get("/api/sets/%s/variant-count" % sid)
vs = r.get_json()
check("grouped total 138", vs["total_combine"] == 138, vs.get("total_combine"))
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
    check("grouped chunks sum to 138", sum(sizes) == 138, sizes)
    check("grouped chunks each <= 95", all(n <= 95 for n in sizes), sizes)
    check("grouped has 2 listings", len(sizes) == 2, sizes)
    blob = json.dumps(j.get("warnings", [])).lower() + \
        j["variant_summary"]["message"].lower()
    check("grouped preview shows no limit text",
          "limit" not in blob and "100-variant" not in blob, blob)

# Grouped guard-fix regression: a synthetic 144-variant product
# (full Gildan 2400 grid, 18 colours x 8 sizes) must NOT be blocked
# in Grouped mode, even though it is over 100 on its own.
sets = app_module.load_sets()
big = catalog.template_entry(T[80])
big["product_id"] = "synthetic-144"
big["title"] = "Synthetic 144-variant Long Sleeve"
big["colours"] = ["Ash", "Black", "Carolina Blue", "Dark Chocolate",
                  "Dark Heather", "Forest Green", "Gold", "Irish Green",
                  "Light Blue", "Light Pink", "Maroon", "Navy", "Purple",
                  "Red", "Royal", "Safety Green", "Sport Grey", "White"]
big["sizes"] = ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
big["all_colours"] = list(big["colours"])
big["all_sizes"] = list(big["sizes"])
sets[sid]["products"].append(big)
app_module.save_sets(sets)
r = client.get("/api/sets/%s/variant-count" % sid)
vs = r.get_json()
check("grouped total 282 with big product",
      vs["total_combine"] == 282, vs.get("total_combine"))
check("grouped guard ok with big product", vs["guard_ok"] is True)
r = post("/api/sets/%s/publish" % sid, {"dry_run": True})
j = r.get_json()
check("grouped dry-run publish allowed (product over 100)",
      r.status_code == 200, (r.status_code, j))
if r.status_code == 200:
    sizes = [len(p["variants"]) for p in j["products"]]
    check("grouped chunks sum to 282", sum(sizes) == 282, sizes)
    check("grouped chunks each <= 95", all(n <= 95 for n in sizes), sizes)
    check("grouped has 3 listings", len(sizes) == 3, sizes)

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
