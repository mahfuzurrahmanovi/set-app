"""Tests for the 3 new local product types (2026-11-07).

Long Sleeve Tee (Gildan 80), Classic Long Sleeve (Gildan Softstyle
64400), V-Neck Tee (Bella+Canvas 48), defined locally in the app.

Run from the repo root or the server folder:
    python server/new_types_test.py

No network, no real Shopify, no Printify, no supplier: Shopify is a
mock client and the dry-run publish never contacts it. Everything is
written to a temporary data directory, never to data/sets.json. A real
publish is never run: the mock's create_live_product fails the suite if
anything ever calls it.

Sections:
  1  the 3 types exist with the exact sizes / colours / prices
  2  template mapping per type, stored type beats title, rename-proof,
     legacy keyword fallback for the existing 3 products
  3  the real frontend function (app.js, run in node) agrees with the
     server for every case in section 2
  4  no Printify (or other supplier) references in the new code; the
     catalog stub is unchanged; clogs are not added
  5  API: add local types, set type, rename, refusals
  6  placement: locked follows the master, unlock override, re-lock
  7  designer mockup render for each new type + freshness rules
  8  linking a local product to its real Shopify listing (listing wins)
  9  grouped variant guard for the 6-product set (V-neck 5 and 6 sizes)
  10 designer page ships the type table and the add-type controls
  11 the garment PNGs carry no ghost dashes (placebox is the only box)
"""

import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_TMP = tempfile.mkdtemp(prefix="new_types_")
os.environ["SETAPP_DATA_ROOT"] = _TMP
os.environ.pop("SET_APP_PASSWORD", None)
os.environ.pop("SETAPP_VNECK_SIZES", None)

import numpy as np
from PIL import Image

import app as app_module
import catalog
import mockup as mockup_module
import product_types as pt

app_module.DATA_FILE = os.path.join(_TMP, "sets.json")
app_module.UPLOAD_DIR = os.path.join(_TMP, "uploads")
app_module.MOCKUP_DIR = os.path.join(_TMP, "mockups")

passed = 0
failed = []
skipped = []

import hashlib
_REAL = os.path.join(os.path.dirname(HERE), "data", "sets.json")


def _real_hash():
    if not os.path.exists(_REAL):
        return None
    return hashlib.sha256(open(_REAL, "rb").read()).hexdigest()


_REAL_BEFORE = _real_hash()


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(name + (" :: " + str(detail) if detail else ""))


def skip(name, why):
    skipped.append(name + " :: " + why)


# ---------------------------------------------------------------- mock
class _Shopify:
    """Stands in for shopify.py. Real publish must never be reached."""

    def __init__(self, real):
        self._real = real
        self.listings = {}
        self.created_live = []

    def authenticated(self):
        return True

    def shop_domain(self):
        return "b2uus8-mt.myshopify.com"

    def public_url(self):
        return ""

    def get_product_details(self, pid):
        d = self.listings.get(str(pid))
        if d is None:
            return None
        out = dict(d)
        out["variant_prices"] = dict(d["variant_prices"])
        out["colours"] = list(d["colours"])
        out["sizes"] = list(d["sizes"])
        out["images"] = list(d["images"])
        return out

    def search_products(self, query, limit=20):
        return []

    def get_product_image(self, pid):
        return None

    def create_live_product(self, **kw):
        self.created_live.append(kw)
        raise AssertionError("a real publish must never run in tests")

    def __getattr__(self, name):
        return getattr(self._real, name)


mock = _Shopify(app_module.shopify_api)
app_module.shopify_api = mock


def listing(pid, title, colours, sizes, price, handle=None, holes=0,
            image=None):
    """A Shopify listing as get_product_details returns it."""
    prices = {}
    pairs = [(c, s) for c in colours for s in sizes]
    for c, s in pairs[: len(pairs) - holes]:
        prices[(c, s)] = price
    return {
        "product_id": pid, "title": title,
        "handle": handle or title.lower().replace(" ", "-"),
        "image": image, "images": [image] if image else [],
        "colours": list(colours), "sizes": list(sizes),
        "variant_prices": prices,
        "variants": len(pairs) - holes,
    }


client = app_module.app.test_client()
tok = client.get("/api/csrf-token").get_json()["csrf_token"]
H = {"X-CSRF-Token": tok, "Content-Type": "application/json"}


def post(path, body=None):
    return client.post(path, data=json.dumps(body or {}), headers=H)


def get(path):
    return client.get(path)


def sets_now():
    return app_module.load_sets()


def prod(sid, pid):
    for p in sets_now()[sid]["products"]:
        if p["product_id"] == pid:
            return p
    return None


# ================================================================ 1
LS, CLS, VN = "long-sleeve", "classic-long-sleeve", "v-neck"
EXPECT = {
    LS: {"colours": {"Ash", "Black", "Dark Heather", "Gold", "Irish Green",
                     "Navy", "Purple", "Red", "Royal", "Sport Grey",
                     "White"},
         "sizes": ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
         "price": "27.00", "variants": 88,
         "title": "Oregon Ducks Long Sleeve Tee"},
    CLS: {"colours": {"Black", "Navy", "Royal", "Sport Grey", "White"},
          "sizes": ["S", "M", "L", "XL", "2XL", "3XL"],
          "price": "29.00", "variants": 30,
          "title": "Oregon Ducks Classic Long Sleeve Tee"},
    VN: {"colours": {"Black", "Navy", "Red", "White"},
         "sizes": ["S", "M", "L", "XL", "2XL"], "price": "29.00",
         "variants": 20,
         "title": "Oregon Ducks V-Neck Tee"},
}
UNION14 = {"Ash", "Black", "Cardinal Red", "Dark Heather", "Gold",
           "Irish Green", "Kelly Green", "Navy", "Orange", "Purple", "Red",
           "Royal", "Sport Grey", "White"}
check("colour union has 14", set(pt.COLOUR_UNION) == UNION14
      and len(pt.COLOUR_UNION) == 14)
for key, exp in EXPECT.items():
    s = pt.starter_for(key)
    check(key + " starter exists", s is not None)
    check(key + " colours exact", set(s["colours"]) == exp["colours"]
          and len(s["colours"]) == len(exp["colours"]), s["colours"])
    check(key + " colours inside the 14-colour union",
          set(s["colours"]) <= UNION14)
    check(key + " colour pool equals selection (nothing extra to add)",
          set(s["all_colours"]) == set(s["colours"]))
    check(key + " sizes exact", s["sizes"] == exp["sizes"], s["sizes"])
    check(key + " price exact", s["price"] == exp["price"], s["price"])
    check(key + " working title is a placeholder",
          s["title"] == exp["title"], s["title"])
    check(key + " default colour is Black",
          s["colours"][0] == "Black", s["colours"])
for bad in ("Cardinal Red", "Kelly Green", "Orange"):
    check("long sleeve excludes " + bad,
          bad not in pt.starter_for(LS)["colours"])
check("long sleeve is 11 colours x 8 sizes = 88",
      len(pt.starter_for(LS)["colours"])
      * len(pt.starter_for(LS)["sizes"]) == 88)
check("classic is 5 colours x 6 sizes = 30",
      len(pt.starter_for(CLS)["colours"])
      * len(pt.starter_for(CLS)["sizes"]) == 30)
check("v-neck sizes default to S-2XL (decided 2026-11-08)",
      pt.starter_for(VN)["sizes"] == ["S", "M", "L", "XL", "2XL"])
check("v-neck size pool is only the two options named in the brief",
      pt.starter_for(VN)["all_sizes"] == ["S", "M", "L", "XL", "2XL", "3XL"])
check("garment labels", pt.PRODUCT_TYPES[LS]["garment"] == "Gildan 80"
      and pt.PRODUCT_TYPES[CLS]["garment"].startswith(
          "Gildan Softstyle 64400")
      and pt.PRODUCT_TYPES[VN]["garment"] == "Bella+Canvas 48")
check("new types list", pt.NEW_TYPE_KEYS == [LS, CLS, VN])
check("template-only types have no starter",
      all(pt.starter_for(k) is None for k in ("tee", "hoodie", "crewneck")))
for k in ("tee", "hoodie", "crewneck"):
    try:
        pt.local_entry(k)
        check("local_entry(%s) refuses" % k, False)
    except ValueError:
        check("local_entry(%s) refuses" % k, True)

# v-neck size setting (configurable, validated, never silent)
os.environ["SETAPP_VNECK_SIZES"] = "S,M,L,XL,2XL"
s5 = pt.starter_for(VN)
check("env sets v-neck to 5 sizes", s5["sizes"] == ["S", "M", "L", "XL", "2XL"],
      s5["sizes"])
os.environ["SETAPP_VNECK_SIZES"] = "s, m, l, xl, 2xl, 3xl"
s6 = pt.starter_for(VN)
check("env sets v-neck to 6 sizes (case/space tolerant)",
      s6["sizes"] == ["S", "M", "L", "XL", "2XL", "3XL"], s6["sizes"])
os.environ["SETAPP_VNECK_SIZES"] = "S,M,HUGE"
try:
    pt.starter_for(VN)
    check("invalid v-neck size setting refused", False)
except ValueError as exc:
    check("invalid v-neck size setting refused", "HUGE" in str(exc), exc)
os.environ.pop("SETAPP_VNECK_SIZES", None)
check("env unset again: default S-2XL",
      pt.starter_for(VN)["sizes"] == ["S", "M", "L", "XL", "2XL"])

# ================================================================ 2
FRONT = "/static/design-area-templates/"
CASES = [  # (product dict, side, expected URL)
    ({"product_type": LS, "title": "Oregon Ducks Long Sleeve Tee"},
     "front", FRONT + "longsleeve-front.png"),
    ({"product_type": CLS, "title": "Oregon Ducks Classic Long Sleeve Tee"},
     "front", FRONT + "longsleeve-front.png"),
    ({"product_type": VN, "title": "Oregon Ducks V-Neck Tee"},
     "front", FRONT + "vneck-front.png"),
    # rename-proof: stored type wins over a title that says something else
    ({"product_type": LS, "title": "Ducks Fan Gear 2026"},
     "front", FRONT + "longsleeve-front.png"),
    ({"product_type": CLS, "title": "Totally Renamed"},
     "front", FRONT + "longsleeve-front.png"),
    ({"product_type": VN, "title": "Something Else Entirely"},
     "front", FRONT + "vneck-front.png"),
    ({"product_type": VN, "title": "Oregon Ducks Hoodie"},
     "front", FRONT + "vneck-front.png"),
    ({"product_type": LS, "title": "Oregon Ducks V-Neck Tee"},
     "front", FRONT + "longsleeve-front.png"),
    # legacy fallback (no stored type): the existing 3 products
    ({"title": "Oregon Ducks Unisex Tee"}, "front",
     FRONT + "shortsleeve-front.png"),
    ({"title": "Oregon Ducks Hoodie"}, "front", FRONT + "hoodie-front.png"),
    ({"title": "Oregon Ducks Crewneck Sweatshirt"}, "front",
     FRONT + "crewneck-front.png"),
    ({"title": "Oregon Ducks Long Sleeve Tee"}, "front",
     FRONT + "longsleeve-front.png"),
    ({"title": "Oregon Ducks Classic Long Sleeve Tee"}, "front",
     FRONT + "longsleeve-front.png"),
    ({"title": "Oregon Ducks V-Neck Tee"}, "front", FRONT + "vneck-front.png"),
    ({"title": "Oregon Ducks V Neck Tee"}, "front", FRONT + "vneck-front.png"),
    # stored types for the existing three
    ({"product_type": "tee", "title": "x"}, "front",
     FRONT + "shortsleeve-front.png"),
    ({"product_type": "hoodie", "title": "x"}, "front",
     FRONT + "hoodie-front.png"),
    ({"product_type": "crewneck", "title": "x"}, "front",
     FRONT + "crewneck-front.png"),
    # back view: short-sleeve tee only (legacy rule)
    ({"title": "Oregon Ducks Unisex Tee"}, "back",
     FRONT + "shortsleeve-back.png"),
    ({"product_type": "tee", "title": "x"}, "back",
     FRONT + "shortsleeve-back.png"),
    ({"title": "Oregon Ducks Hoodie"}, "back", ""),
    ({"product_type": LS, "title": "x"}, "back", ""),
    ({"product_type": CLS, "title": "x"}, "back", ""),
    ({"product_type": VN, "title": "x"}, "back", ""),
    # no title, no type: no template (legacy)
    ({}, "front", ""),
    ({"title": ""}, "front", ""),
    # an unknown stored type falls back to the title keywords
    ({"product_type": "nope", "title": "Oregon Ducks Hoodie"}, "front",
     FRONT + "hoodie-front.png"),
]
for prod_d, side, want in CASES:
    got = pt.template_url(prod_d, side)
    check("python template %s/%s -> %s" % (prod_d.get("product_type")
          or prod_d.get("title") or "empty", side,
          want.split("/")[-1] or "''"), got == want, got)
TPL_DIR = os.path.join(HERE, "static", "design-area-templates")
for name in sorted(pt.template_filenames()):
    check("template file exists: " + name,
          os.path.exists(os.path.join(TPL_DIR, name)))
check("new types reuse the existing outline files only",
      {pt.PRODUCT_TYPES[k]["template_front"] for k in (LS, CLS, VN)}
      == {"longsleeve-front.png", "vneck-front.png"})
check("classic uses longsleeve-front.png (open decision #5)",
      pt.PRODUCT_TYPES[CLS]["template_front"] == "longsleeve-front.png")
check("classic keyword is tried before long sleeve",
      pt.infer_type_key("Classic Long Sleeve Tee") == CLS
      and pt.infer_type_key("Gildan Long Sleeve Tee") == LS)
check("resolve_type_key stored beats title",
      pt.resolve_type_key({"product_type": VN, "title": "Hoodie"}) == VN)

# ================================================================ 3
JS_PATH = os.path.join(HERE, "static", "app.js")
js_src = open(JS_PATH).read()
_node_ok = False
try:
    _node_ok = subprocess.run(["node", "--version"], capture_output=True,
                              timeout=20).returncode == 0
except Exception:
    _node_ok = False
if not _node_ok:
    skip("section 3 (frontend function in node)", "node is not installed")
else:
    runner = r"""
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const code = fs.readFileSync(input.js, 'utf8');
const sandbox = {
  window: { fetch: function() {}, PRODUCT_TYPES: input.types },
  document: { addEventListener: function() {}, getElementById: function() { return null; } },
  console: console, alert: function() {}, confirm: function() { return true; }
};
sandbox.window.PRODUCT_TYPES = input.types;
vm.createContext(sandbox);
vm.runInContext(code + "\n;globalThis.__fn = designAreaTemplateUrl;", sandbox);
const out = input.cases.map(function(c) { return sandbox.__fn(c[0], c[1]); });
process.stdout.write(JSON.stringify(out));
"""
    rp = os.path.join(_TMP, "run_js.js")
    open(rp, "w").write(runner)

    def run_js(types, cases):
        ip = os.path.join(_TMP, "js_in.json")
        json.dump({"js": JS_PATH, "types": types, "cases": cases},
                  open(ip, "w"))
        r = subprocess.run(["node", rp, ip], capture_output=True, text=True,
                           timeout=60)
        if r.returncode != 0:
            return None, r.stderr
        return json.loads(r.stdout), ""

    table = pt.public_types()["types"]
    js_cases = [[c[0], c[1]] for c in CASES]
    out, err = run_js(table, js_cases)
    check("node ran app.js designAreaTemplateUrl", out is not None, err[:300])
    if out is not None:
        for (prod_d, side, want), got in zip(CASES, out):
            check("js template %s/%s -> %s" % (prod_d.get("product_type")
                  or prod_d.get("title") or "empty", side,
                  want.split("/")[-1] or "''"), got == want, got)
        # a bare title string still works (old call style)
        o2, _ = run_js(table, [["Oregon Ducks Hoodie", "front"],
                               ["Oregon Ducks V-Neck Tee", "front"],
                               ["", "front"]])
        check("js accepts a bare title (legacy call style)",
              o2 == [FRONT + "hoodie-front.png", FRONT + "vneck-front.png",
                     ""], o2)
        # if the type table never loaded, stored types fall back to the
        # title keywords instead of throwing
        o3, _ = run_js(None, [[{"title": "Oregon Ducks Hoodie"}, "front"],
                              [{"product_type": VN,
                                "title": "Oregon Ducks V-Neck Tee"},
                               "front"]])
        check("js without a type table falls back to keywords",
              o3 == [FRONT + "hoodie-front.png", FRONT + "vneck-front.png"],
              o3)
        # the frontend effectivePlacementOf agrees with the server:
        # locked long sleeve / classic follow the master, a locked
        # V-neck follows its type placement, an unlocked product's
        # override wins.
        prunner = r"""
const fs = require('fs'), vm = require('vm');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const code = fs.readFileSync(input.js, 'utf8');
const sandbox = {
  window: { fetch: function() {}, PRODUCT_TYPES: input.types },
  document: { addEventListener: function() {}, getElementById: function() { return null; } },
  console: console, alert: function() {}, confirm: function() { return true; }
};
sandbox.window.PRODUCT_TYPES = input.types;
vm.createContext(sandbox);
vm.runInContext(code + "\n;currentSet = {master_placement: " + JSON.stringify(input.master) + "};\n;globalThis.__pl = effectivePlacementOf;", sandbox);
const out = input.cases.map(function(c) { return sandbox.__pl(c); });
process.stdout.write(JSON.stringify(out));
"""
        pp = os.path.join(_TMP, "run_js_pl.js")
        open(pp, "w").write(prunner)
        ip = os.path.join(_TMP, "js_pl_in.json")
        json.dump({"js": JS_PATH, "types": table,
                   "master": {"x": 0.5, "y": 0.47, "scale": 0.32,
                              "angle": 0},
                   "cases": [
                       {"product_type": LS, "locked": True},
                       {"product_type": CLS, "locked": True},
                       {"product_type": VN, "locked": True},
                       {"product_type": VN, "locked": False,
                        "override_placement": {"x": 0.5, "y": 0.5,
                                               "scale": 0.3, "angle": 0}},
                   ]}, open(ip, "w"))
        r = subprocess.run(["node", pp, ip], capture_output=True, text=True,
                           timeout=60)
        check("node ran app.js effectivePlacementOf",
              r.returncode == 0, r.stderr[:300])
        if r.returncode == 0:
            pl = json.loads(r.stdout)
            check("js: locked long sleeve follows the master",
                  pl[0] == {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0},
                  pl[0])
            check("js: locked classic follows the master",
                  pl[1] == {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0},
                  pl[1])
            check("js: locked v-neck follows its type placement",
                  pl[2] == {"x": 0.5, "y": 0.60, "scale": 0.32, "angle": 0},
                  pl[2])
            check("js: unlocked v-neck override wins",
                  pl[3] == {"x": 0.5, "y": 0.5, "scale": 0.3, "angle": 0},
                  pl[3])

# ================================================================ 4
def src(*parts):
    return open(os.path.join(HERE, *parts)).read()


NEW_CODE = {
    "product_types.py": src("product_types.py"),
    "app.py": src("app.py"),
    "new_types_test.py": None,  # this file talks about the rule itself
    "templates/designer.html": src("templates", "designer.html"),
    "templates/campaigns.html": src("templates", "campaigns.html"),
    "templates/campaign_settings.html": src("templates",
                                            "campaign_settings.html"),
}
for name, text in NEW_CODE.items():
    if text is None:
        continue
    low = text.lower()
    allowed_label = (name == "templates/designer.html")
    n = low.count("printify")
    if allowed_label:
        # the one pre-existing "Printify flat product photo" label
        n -= low.count("printify flat product photo")
    check("%s has no Printify reference" % name, n == 0, n)
    for needle in ("blueprint", "provider id", "print_provider",
                   "images.printify.com", "api.printify", "catkissfish",
                   "cat kiss fish api"):
        check("%s has no %r" % (name, needle), needle not in low)
check("product_types.py has no clogs", "clog" not in
      NEW_CODE["product_types.py"].lower())
check("no clog type", not any("clog" in k for k in pt.PRODUCT_TYPES))
check("clogs not mentioned in app.py", "clog" not in
      NEW_CODE["app.py"].lower())
# app.js: only the pre-existing, deliberate printifyImageOf lines remain
ALLOWED_JS_PRINTIFY = {
    "function printifyImageOf(p) {",
    "// Exact Printify photo already on file for this store product, if",
    "// images.printify.com counts.",
    "if (urls[i] && urls[i].indexOf('images.printify.com') !== -1) return urls[i];",
    "p._printifyExact = true;",
    "// Exact Printify photo on file for this store product beats both a",
    "// template match and a model Shopify photo: it is the photo Printify",
    "const exact = printifyImageOf(p);",
    "p._flatTemplate = { title: p.title, brand: 'Printify' };",
    "p._printifyExact = false;",
    "if (p._printifyExact) return 'Printify photo (exact product photo)';",
    "if (p._flatTemplate) return 'Printify flat product photo' + (p._flatTemplate.brand ? ' (' + esc(p._flatTemplate.brand) + ')' : '');",
    "return 'Not a Printify flat photo: bare store photo';",
}
extra = [ln.strip() for ln in js_src.splitlines()
         if "printify" in ln.lower() and ln.strip() not in ALLOWED_JS_PRINTIFY]
check("app.js adds no new Printify lines", extra == [], extra)
check("app.js keeps printifyImageOf (deliberate, not a connection)",
      "function printifyImageOf(p)" in js_src)
check("app.js has no catalog fetch", "/api/catalog/templates" not in js_src)
check("catalog TEMPLATES still empty stub", catalog.TEMPLATES == [])
check("catalog get_template still None",
      catalog.get_template("catalog:printify-80") is None
      and catalog.get_template("local:long-sleeve") is None)
cat_src = src("catalog.py").lower()
for needle in ("printify", "blueprint", "provider", "gildan", "bella"):
    check("catalog.py has no %r" % needle, needle not in cat_src)
r = get("/api/catalog/templates")
check("catalog endpoint still 404", r.status_code == 404)
check("local ids are not Shopify ids", pt.is_local_id("local:v-neck")
      and not pt.is_local_id("15469998538906"))

# ================================================================ 5
r = get("/api/product-types")
check("GET /api/product-types 200", r.status_code == 200, r.status_code)
j = r.get_json()
check("types table has all six types", set(j["types"]) == {
    "tee", "hoodie", "crewneck", "v-neck", "classic-long-sleeve",
    "long-sleeve"}, list(j["types"]))
check("types table: v-neck sizes decided (S-2XL default)",
      j["types"][VN]["starter"]["sizes_decided"] is True
      and j["types"][VN]["starter"]["sizes"] == ["S", "M", "L", "XL", "2XL"])
check("types table: template urls",
      j["types"][LS]["template_front_url"] == FRONT + "longsleeve-front.png"
      and j["types"]["tee"]["template_back_url"]
      == FRONT + "shortsleeve-back.png")

r = post("/api/campaigns", {"name": "Types test", "slug": "types-test"})
check("campaign created", r.status_code == 201, r.status_code)
SID = r.get_json()["id"]
check("new set is grouped by default", r.get_json()["grouping"] == "grouped")

r = post("/api/sets/%s/local-products" % SID, {"type": LS})
check("add long sleeve 201", r.status_code == 201, (r.status_code,
                                                    r.get_json()))
r = post("/api/sets/%s/local-products" % SID, {"type": CLS})
check("add classic 201", r.status_code == 201, r.status_code)
r = post("/api/sets/%s/local-products" % SID, {"type": VN})
check("add v-neck 201", r.status_code == 201, r.status_code)
S = sets_now()[SID]
check("set holds 3 products", len(S["products"]) == 3)
for key, exp in EXPECT.items():
    p = prod(SID, "local:" + key)
    check(key + " entry exists", p is not None)
    if p is None:
        continue
    check(key + " kind local", p["kind"] == "local")
    check(key + " stored type", p["product_type"] == key)
    check(key + " title placeholder", p["title"] == exp["title"])
    check(key + " colours", set(p["colours"]) == exp["colours"])
    check(key + " sizes", p["sizes"] == exp["sizes"], p["sizes"])
    check(key + " sale price", p["sale_price"] == exp["price"])
    check(key + " locked, no override", p["locked"] is True
          and p["override_placement"] is None)
    check(key + " default colour Black", p["default_color"] == "Black"
          and p["colours"][0] == "Black")
    check(key + " position front", p["position"] == "front")
    check(key + " has no photo / mockups", not p["images"] and not
          p["mockups"] and p["image"] is None)
    check(key + " colour pool == colours", set(p["all_colours"])
          == set(p["colours"]))
check("long sleeve 88 variants", app_module.product_variant_count(
    prod(SID, "local:" + LS)) == 88)
check("classic 30 variants", app_module.product_variant_count(
    prod(SID, "local:" + CLS)) == 30)
check("v-neck 4 x 5 = 20 variants by default (S-2XL)",
      app_module.product_variant_count(prod(SID, "local:" + VN)) == 20)

# product_variant_count matches the CREATED count, not the grid
def _pvc(colours, sizes, sale_price=None, variant_prices=None,
         variants=None):
    p = {"colours": list(colours), "sizes": list(sizes)}
    if sale_price is not None:
        p["sale_price"] = sale_price
    if variant_prices is not None:
        p["variant_prices"] = dict(variant_prices)
    if variants is not None:
        p["variants"] = variants
    return app_module.product_variant_count(p)

_c12 = ["c%d" % i for i in range(12)]
_s8 = ["s%d" % i for i in range(8)]
_pairs = [(c, s) for c in _c12 for s in _s8]
_holes = {("%s||%s" % (c, s)): "10.00" for c, s in _pairs[8:]}
check("variant count: priced pairs only (8 unpriced pairs skipped)",
      _pvc(_c12, _s8, variant_prices=_holes, variants=88) == 88)
check("variant count: stored listing count when no prices recorded",
      _pvc(_c12, _s8, variants=88) == 88)
check("variant count: grid when no prices and no stored count",
      _pvc(_c12, _s8) == 96)
check("variant count: flat sale price prices every pair",
      _pvc(_c12, _s8, sale_price="27.00") == 96)
check("variant count: None when colours or sizes missing",
      _pvc([], _s8) is None and _pvc(_c12, []) is None)

r = post("/api/sets/%s/local-products" % SID, {"type": LS})
check("same local type twice refused", r.status_code == 400, r.status_code)
check("refusal says already in set",
      "already" in (r.get_json() or {}).get("error", "").lower())
for bad in ("hoodie", "tee", "crewneck", "clogs", "nope", "", None):
    r = post("/api/sets/%s/local-products" % SID, {"type": bad})
    check("local type %r refused" % (bad,), r.status_code == 400,
          r.status_code)
r = post("/api/sets/no-such/local-products", {"type": LS})
check("local add on missing set 404", r.status_code == 404)
check("set unchanged after refusals", len(sets_now()[SID]["products"]) == 3)

# bare add refuses local ids; refresh refuses local products
r = post("/api/sets/%s/products" % SID, {"product_id": "local:long-sleeve"})
check("bare add of a local: id refused", r.status_code == 400
      and "local" in r.get_json()["error"].lower(), r.get_json())
r = post("/api/sets/%s/products/local:%s/refresh" % (SID, LS))
check("refresh of a local product refused (no listing)",
      r.status_code == 400, r.status_code)
check("refusal says link first",
      "link" in r.get_json()["error"].lower(), r.get_json())

# v-neck sizes: set once decided, via the existing size endpoint
r = post("/api/sets/%s/products/local:%s/variants" % (SID, VN),
         {"sizes": ["S", "M", "L", "XL", "2XL"]})
check("v-neck sizes can be set later", r.status_code == 200)
check("v-neck now 4 x 5 = 20 variants", app_module.product_variant_count(
    prod(SID, "local:" + VN)) == 20)

# type endpoint
r = post("/api/sets/%s/products/local:%s/type" % (SID, CLS), {"type": LS})
check("set type 200", r.status_code == 200)
check("type stored", prod(SID, "local:" + CLS)["product_type"] == LS)
check("template follows the stored type", pt.template_url(
    prod(SID, "local:" + CLS)) == FRONT + "longsleeve-front.png")
r = post("/api/sets/%s/products/local:%s/type" % (SID, CLS), {"type": VN})
check("type can change to v-neck", prod(SID, "local:" + CLS)[
    "product_type"] == VN and pt.template_url(
        prod(SID, "local:" + CLS)) == FRONT + "vneck-front.png")
r = post("/api/sets/%s/products/local:%s/type" % (SID, CLS), {"type": CLS})
check("type set back", prod(SID, "local:" + CLS)["product_type"] == CLS)
r = post("/api/sets/%s/products/local:%s/type" % (SID, CLS), {"type": "nope"})
check("unknown type refused", r.status_code == 400)
r = post("/api/sets/%s/products/nope/type" % SID, {"type": LS})
check("type on missing product 404", r.status_code == 404)
r = post("/api/sets/%s/products/local:%s/type" % (SID, CLS), {"type": None})
check("type can be cleared (keyword fallback)", r.status_code == 200
      and "product_type" not in prod(SID, "local:" + CLS))
check("cleared type falls back to the title keywords",
      pt.template_url(prod(SID, "local:" + CLS))
      == FRONT + "longsleeve-front.png")
post("/api/sets/%s/products/local:%s/type" % (SID, CLS), {"type": CLS})

# rename (local products only) and the template after the rename
r = post("/api/sets/%s/products/local:%s/title" % (SID, LS),
         {"title": "Ducks Fan Gear 2026"})
check("rename local 200", r.status_code == 200, r.get_json())
check("title stored", prod(SID, "local:" + LS)["title"]
      == "Ducks Fan Gear 2026")
check("template unchanged after rename (long sleeve)", pt.template_url(
    prod(SID, "local:" + LS)) == FRONT + "longsleeve-front.png")
r = post("/api/sets/%s/products/local:%s/title" % (SID, VN),
         {"title": "Mystery Garment"})
check("template unchanged after rename (v-neck)", pt.template_url(
    prod(SID, "local:" + VN)) == FRONT + "vneck-front.png")
r = post("/api/sets/%s/products/local:%s/title" % (SID, CLS),
         {"title": "Mystery Garment"})
check("two products cannot share a title (Style option clash)",
      r.status_code == 400, r.status_code)
check("duplicate check is case-insensitive", post(
    "/api/sets/%s/products/local:%s/title" % (SID, CLS),
    {"title": "  mystery GARMENT "}).status_code == 400)
check("blank title refused", post(
    "/api/sets/%s/products/local:%s/title" % (SID, CLS),
    {"title": "   "}).status_code == 400)
check("title over 255 chars refused", post(
    "/api/sets/%s/products/local:%s/title" % (SID, CLS),
    {"title": "x" * 256}).status_code == 400)
check("renaming to its own title is fine", post(
    "/api/sets/%s/products/local:%s/title" % (SID, VN),
    {"title": "Mystery Garment"}).status_code == 200)
# restore working titles
post("/api/sets/%s/products/local:%s/title" % (SID, LS),
     {"title": EXPECT[LS]["title"]})
post("/api/sets/%s/products/local:%s/title" % (SID, VN),
     {"title": EXPECT[VN]["title"]})

# ================================================================ 6
MASTER = {"x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0}
VNECK_PLACEMENT = {"x": 0.5, "y": 0.60, "scale": 0.32, "angle": 0}
r = post("/api/sets/%s/master" % SID, {"placement": MASTER})
check("master set to the live values", r.status_code == 200)
S = sets_now()[SID]
check("master stored", S["master_placement"] == MASTER, S["master_placement"])
for key in (LS, CLS):
    check(key + " locked follows the master",
          app_module.effective_placement(S, "local:" + key) == MASTER,
          app_module.effective_placement(S, "local:" + key))
check("v-neck locked follows its own type placement (not the master,"
      " which would put a square badge over the V opening)",
      app_module.effective_placement(S, "local:" + VN) == VNECK_PLACEMENT,
      app_module.effective_placement(S, "local:" + VN))
check("v-neck type placement clears the V (badge top 0.360 > V 0.341)",
      VNECK_PLACEMENT["y"] - VNECK_PLACEMENT["scale"] * 1000 / 2 / 666
      > 0.341)
v0 = S["design_version"]
r = post("/api/sets/%s/products/local:%s/lock" % (SID, VN),
         {"locked": False, "placement": {"x": 0.5, "y": 0.5, "scale": 0.3,
                                         "angle": 0}})
check("unlock with override 200", r.status_code == 200)
S = sets_now()[SID]
check("override applies to that product only",
      app_module.effective_placement(S, "local:" + VN)["y"] == 0.5
      and app_module.effective_placement(S, "local:" + LS) == MASTER
      and app_module.effective_placement(S, "local:" + CLS) == MASTER)
check("override bumps the design version", S["design_version"] > v0)
check("master untouched by an override", S["master_placement"] == MASTER)
r = post("/api/sets/%s/products/local:%s/lock" % (SID, VN), {"locked": True})
S = sets_now()[SID]
check("re-lock returns to the v-neck type placement",
      app_module.effective_placement(S, "local:" + VN) == VNECK_PLACEMENT
      and prod(SID, "local:" + VN)["override_placement"] is None)
r = post("/api/sets/%s/products/local:%s/lock" % (SID, VN),
         {"locked": False, "placement": {"x": 0.9, "y": 0.9, "scale": 0.9,
                                         "angle": 0}})
ov = prod(SID, "local:" + VN)["override_placement"]
check("override is clamped to the fixed print area",
      ov["x"] == 0.75 and ov["y"] == 0.70 and ov["scale"] == 0.5, ov)
post("/api/sets/%s/products/local:%s/lock" % (SID, VN), {"locked": True})
# printed area geometry is still the fixed 25/20/50/50 box
check("app.js PRINT_AREA still 25/20/50/50",
      "const PRINT_AREA = { left: 0.25, top: 0.20, width: 0.50, "
      "height: 0.50 };" in js_src)

# V-neck mockup render: a square badge at the locked V-neck
# placement must sit clear of the V opening on the real template.
# The V opening reaches 0.341 of the image height at the centre, so
# the centre column above 0.341 must show no badge at all, while the
# badge is present below the V. The master placement is the control:
# it DOES put the badge into the V.
def _is_red(px):
    return int(px[0]) > 180 and int(px[1]) < 120 and int(px[2]) < 120

_badge = os.path.join(_TMP, "square-badge.png")
Image.new("RGBA", (400, 400), (255, 0, 0, 255)).save(_badge)
_vneck_png = os.path.join(HERE, "static", "design-area-templates",
                          "vneck-front.png")
S = sets_now()[SID]
_vn_pl = app_module.effective_placement(S, "local:" + VN)
_vn_out = os.path.join(_TMP, "vneck-badge.png")
mockup_module.composite(_badge, _vneck_png, _vn_pl, _vn_out)
_vn_im = np.array(Image.open(_vn_out).convert("RGB"))
_cx = _vn_im.shape[1] // 2
check("v-neck render: no badge in the V opening (centre, y 0.28)",
      not _is_red(_vn_im[int(0.28 * _vn_im.shape[0]), _cx]),
      _vn_im[int(0.28 * _vn_im.shape[0]), _cx].tolist())
check("v-neck render: badge present below the V (centre, y 0.50)",
      _is_red(_vn_im[int(0.50 * _vn_im.shape[0]), _cx]))
_m_out = os.path.join(_TMP, "vneck-badge-master.png")
mockup_module.composite(_badge, _vneck_png, MASTER, _m_out)
_m_im = np.array(Image.open(_m_out).convert("RGB"))
check("control: master placement DOES put the badge in the V (y 0.28)",
      _is_red(_m_im[int(0.28 * _m_im.shape[0]), _cx]))

# ================================================================ 7
def make_badge(path, size=600):
    """A stand-in for the Oregon badge: a transparent PNG with a solid
    green disc and a yellow ring (the real badge file is not in the
    package). Transparent corners, > 3 percent transparent pixels."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    yy, xx = np.ogrid[:size, :size]
    c = size / 2
    d = np.sqrt((xx - c) ** 2 + (yy - c) ** 2)
    a = np.array(im)
    a[d <= size / 2 - 2] = (255, 213, 0, 255)
    a[d <= size * 0.40] = (0, 110, 50, 255)
    Image.fromarray(a, "RGBA").save(path)


badge = os.path.join(_TMP, "badge.png")
make_badge(badge)
r = client.post("/api/sets/%s/upload" % SID,
                data={"design": (open(badge, "rb"), "badge.png")},
                headers={"X-CSRF-Token": tok},
                content_type="multipart/form-data")
check("stand-in badge uploads", r.status_code == 200, r.get_json())
S = sets_now()[SID]
check("design stored", bool(S["design_url"]))

for key in EXPECT:
    pid = "local:" + key
    r = get("/api/sets/%s/products/%s/photo?bare=1" % (SID, pid))
    pj = r.get_json()
    exp_tpl = pt.template_url(prod(SID, pid))
    check(key + " bare photo is its design-area template",
          pj.get("photo") == exp_tpl and pj.get("source") == "template", pj)
    body = {"design": S["design_url"], "photos": {pid: pj["photo"]}}
    r = post("/api/sets/%s/mockups" % SID, body)
    j = r.get_json()
    check(key + " mockup render 200 with no errors",
          r.status_code == 200 and not j.get("errors"), j)
    url = (j.get("mockups") or {}).get(pid)
    check(key + " mockup url issued", bool(url) and url.startswith(
        "/static/mockups/"), url)
    if not url:
        continue
    out = os.path.join(app_module.MOCKUP_DIR, os.path.basename(url))
    check(key + " mockup file exists", os.path.exists(out))
    im = np.array(Image.open(out).convert("RGB")).astype(int)
    tpl = np.array(Image.open(os.path.join(TPL_DIR, os.path.basename(
        exp_tpl))).convert("RGB")).astype(int)
    check(key + " mockup is template-sized (1000x666)",
          im.shape == tpl.shape == (666, 1000, 3), (im.shape, tpl.shape))
    # badge centred on the chest at x 0.5, width 0.32 of the image;
    # y 0.47 (the master) for the long sleeves, 0.60 for the V-neck
    # (its type placement, so the badge clears the V opening)
    exp_y = 0.60 if key == VN else 0.47
    cx, cy = 500, int(exp_y * 666)
    check(key + " badge centre pixel is badge green",
          abs(im[cy, cx][0] - 0) < 12 and abs(im[cy, cx][1] - 110) < 12,
          im[cy, cx].tolist())
    diff = (np.abs(im - tpl).sum(axis=2) > 40)
    ys, xs = np.where(diff)
    check(key + " badge changed pixels", len(xs) > 1000, len(xs))
    if len(xs):
        w = xs.max() - xs.min() + 1
        check(key + " badge width is ~32% of the image",
              abs(w - 320) <= 8, w)
        check(key + " badge centred left/right",
              abs((xs.min() + xs.max()) / 2 - 500) <= 3,
              (xs.min() + xs.max()) / 2)
        check(key + " badge centred at %d%% height" % int(exp_y * 100),
              abs((ys.min() + ys.max()) / 2 - cy) <= 3,
              (ys.min() + ys.max()) / 2)
        check(key + " badge not clipped (inside the image)",
              xs.min() > 0 and xs.max() < 999 and ys.min() > 0
              and ys.max() < 665)
        # inside the fixed print area horizontally (left 25%, width 50%)
        # and not above its top edge. The bottom is not asserted: the
        # app clamps the design CENTRE and WIDTH only, so a tall design
        # may extend below the box.
        check(key + " badge sits inside the print area (left/right, top)",
              xs.min() >= 250 and xs.max() <= 750
              and ys.min() >= int(0.20 * 666),
              (xs.min(), xs.max(), ys.min(), ys.max()))
    check(key + " corner pixel untouched", im[5, 5].tolist()
          == tpl[5, 5].tolist())

# freshness: every render stamps the design version
S = sets_now()[SID]
for key in EXPECT:
    p = prod(SID, "local:" + key)
    check(key + " mockup current after render",
          app_module.mockup_is_current(S, p) is True)
    check(key + " mockup version stamped",
          p["mockup_versions"].get(p["mockups"][0]) == S["design_version"])
post("/api/sets/%s/master" % SID, {"placement": {
    "x": 0.5, "y": 0.5, "scale": 0.32, "angle": 0}})
S = sets_now()[SID]
check("master edit flags every new type's mockup outdated",
      all(app_module.mockup_is_current(S, prod(SID, "local:" + k)) is False
          for k in EXPECT))
r = post("/api/sets/%s/publish" % SID, {"dry_run": True})
check("dry run warns about outdated mockups", any(
    "fresh Preview" in w for w in r.get_json().get("warnings", [])),
      r.get_json())
post("/api/sets/%s/master" % SID, {"placement": MASTER})
# re-render all three (v-neck still has 5 sizes selected)
S = sets_now()[SID]
photos = {}
for key in EXPECT:
    photos["local:" + key] = get("/api/sets/%s/products/local:%s/photo?bare=1"
                                 % (SID, key)).get_json()["photo"]
r = post("/api/sets/%s/mockups" % SID, {"design": S["design_url"],
                                        "photos": photos})
check("re-render all three 200", r.status_code == 200
      and not r.get_json().get("errors"), r.get_json())
S = sets_now()[SID]
check("re-render makes them current again", all(
    app_module.mockup_is_current(S, prod(SID, "local:" + k)) is True
    for k in EXPECT))
# a design re-upload clears the new types' mockups
before = {k: list(prod(SID, "local:" + k)["mockups"]) for k in EXPECT}
check("each new type holds a mockup before re-upload",
      all(before[k] for k in EXPECT))
r = client.post("/api/sets/%s/upload" % SID,
                data={"design": (open(badge, "rb"), "badge2.png")},
                headers={"X-CSRF-Token": tok},
                content_type="multipart/form-data")
S = sets_now()[SID]
check("design re-upload clears new types' mockups", all(
    prod(SID, "local:" + k)["mockups"] == [] for k in EXPECT))
# photos allow-list: only the known template files, never arbitrary paths
r = post("/api/sets/%s/mockups" % SID, {
    "design": S["design_url"],
    "photos": {"local:" + LS:
               "/static/design-area-templates/../../app.py"}})
check("template photo path traversal is refused", bool(
    r.get_json().get("errors")) or r.status_code == 400, r.get_json())
r = post("/api/sets/%s/mockups" % SID, {
    "design": S["design_url"],
    "photos": {"local:" + LS:
               "/static/design-area-templates/not-a-template.png"}})
check("unknown template file name refused",
      bool(r.get_json().get("errors")), r.get_json())
r = post("/api/sets/%s/mockups" % SID, {
    "design": S["design_url"],
    "photos": {"local:" + LS: "/etc/passwd"}})
check("filesystem path still refused", bool(r.get_json().get("errors")))
# re-render so later sections have current mockups
photos = {}
for key in EXPECT:
    photos["local:" + key] = get("/api/sets/%s/products/local:%s/photo?bare=1"
                                 % (SID, key)).get_json()["photo"]
post("/api/sets/%s/mockups" % SID, {"design": S["design_url"],
                                    "photos": photos})

# changing a local product's type clears its (now wrong) mockup only
S = sets_now()[SID]
other = list(prod(SID, "local:" + LS)["mockups"])
post("/api/sets/%s/products/local:%s/type" % (SID, CLS), {"type": VN})
check("type change clears that local product's mockups",
      prod(SID, "local:" + CLS)["mockups"] == [])
check("other products keep their mockups",
      prod(SID, "local:" + LS)["mockups"] == other and other)
post("/api/sets/%s/products/local:%s/type" % (SID, CLS), {"type": CLS})

# ================================================================ 8
# Linking a local product to its real Shopify listing. The listing
# wins; the type, lock and override carry over.
mock.listings["900000000001"] = listing(
    "900000000001", "Oregon Ducks Gildan Long Sleeve", ["Black", "Navy",
                                                        "Red"],
    ["S", "M", "L"], "26.50", image="https://example.test/ls.jpg")
mock.listings["900000000002"] = listing(
    "900000000002", "Ducks Soft Long Sleeve", EXPECT[CLS]["colours"] and
    sorted(EXPECT[CLS]["colours"]), EXPECT[CLS]["sizes"], "28.00")
mock.listings["900000000003"] = listing(
    "900000000003", "Oregon Ducks Vee", sorted(EXPECT[VN]["colours"]),
    ["S", "M", "L", "XL", "2XL"], "28.50")

# unlock the long sleeve with an override first, to prove it carries over
post("/api/sets/%s/products/local:%s/lock" % (SID, LS),
     {"locked": False, "placement": {"x": 0.52, "y": 0.5, "scale": 0.3,
                                     "angle": 0}})
before_ids = [p["product_id"] for p in sets_now()[SID]["products"]]
r = post("/api/sets/%s/products" % SID, {
    "product_id": "900000000001", "link_local": "local:" + LS})
check("link long sleeve 200", r.status_code == 200, r.get_json())
ids = [p["product_id"] for p in sets_now()[SID]["products"]]
check("local entry replaced in place (same position, same count)",
      ids == ["900000000001"] + before_ids[1:], ids)
p = prod(SID, "900000000001")
check("linked entry is a store product", p["kind"] == "store")
check("linked entry keeps the stored type", p["product_type"] == LS)
check("template of the linked product is long sleeve", pt.template_url(
    p) == FRONT + "longsleeve-front.png")
check("listing wins: title", p["title"] == "Oregon Ducks Gildan Long Sleeve")
check("listing wins: colours (3, not the local 11)",
      sorted(p["colours"]) == ["Black", "Navy", "Red"], p["colours"])
check("listing wins: sizes (3, not the local 8)",
      p["sizes"] == ["S", "M", "L"], p["sizes"])
check("listing wins: per-variant prices",
      p["variant_prices"].get("Black||S") == "26.50", p["variant_prices"])
check("working price dropped so the listing's prices apply",
      p["sale_price"] is None)
check("listing photo stored", p["image"] == "https://example.test/ls.jpg")
check("lock state carried over (still unlocked, same override)",
      p["locked"] is False and p["override_placement"]["x"] == 0.52)
check("old local mockups cleared on link", p["mockups"] == []
      and p["hero_image"] is None)
check("local placeholder is gone", prod(SID, "local:" + LS) is None)
check("variant price comes from the listing", app_module
      .variant_price_for_pair(p, "Black", "S") is not None and str(
          app_module.variant_price_for_pair(p, "Black", "S")) == "26.50")
# refresh keeps seller choices but takes new listing data, and the type
mock.listings["900000000001"]["title"] = "Totally Renamed In Shopify"
post("/api/sets/%s/products/900000000001/refresh" % SID)
p = prod(SID, "900000000001")
check("refresh syncs the Shopify title", p["title"]
      == "Totally Renamed In Shopify")
check("template survives a Shopify rename (stored type)", pt.template_url(
    p) == FRONT + "longsleeve-front.png")
# re-lock to master
post("/api/sets/%s/products/900000000001/lock" % SID, {"locked": True})
check("re-lock after linking returns to master",
      app_module.effective_placement(sets_now()[SID], "900000000001")
      == sets_now()[SID]["master_placement"])

# link errors
r = post("/api/sets/%s/products" % SID, {
    "product_id": "900000000002", "link_local": "local:nope"})
check("link to a missing local product refused", r.status_code == 400)
check("nothing added on that refusal", prod(SID, "900000000002") is None)
r = post("/api/sets/%s/products" % SID, {
    "product_id": "900000000002", "link_local": "900000000001"})
check("link to a non-local product refused", r.status_code == 400)
r = post("/api/sets/%s/products" % SID, {"product_id": "999999999999",
                                         "link_local": "local:" + CLS})
check("link to an unknown Shopify id refused, local kept",
      r.status_code == 400 and prod(SID, "local:" + CLS) is not None)

# link the other two (a renamed title with no keywords at all)
r = post("/api/sets/%s/products" % SID, {
    "product_id": "900000000002", "link_local": "local:" + CLS})
check("link classic 200", r.status_code == 200, r.get_json())
p = prod(SID, "900000000002")
check("classic keeps type though the new title says nothing about it",
      p["product_type"] == CLS and pt.template_url(p)
      == FRONT + "longsleeve-front.png")
check("classic synced 5 colours x 6 sizes", len(p["colours"]) == 5
      and len(p["sizes"]) == 6)
r = post("/api/sets/%s/products" % SID, {
    "product_id": "900000000003", "link_local": "local:" + VN})
check("link v-neck 200", r.status_code == 200, r.get_json())
p = prod(SID, "900000000003")
check("v-neck keeps type though the title is 'Vee'",
      p["product_type"] == VN and pt.template_url(p)
      == FRONT + "vneck-front.png")
check("v-neck sizes come from the listing", p["sizes"] == [
    "S", "M", "L", "XL", "2XL"])
check("no local products left", all(
    q["kind"] != "local" for q in sets_now()[SID]["products"]))

# adding a store product without linking infers the type from the title
mock.listings["900000000004"] = listing(
    "900000000004", "Oregon Ducks Hoodie", ["Black"], ["S", "M"], "44.00")
mock.listings["900000000005"] = listing(
    "900000000005", "Mystery Garment", ["Black"], ["S", "M"], "20.00")
post("/api/sets/%s/products" % SID, {"product_id": "900000000004"})
post("/api/sets/%s/products" % SID, {"product_id": "900000000005"})
check("plain add infers hoodie from the title",
      prod(SID, "900000000004")["product_type"] == "hoodie")
check("plain add of an unrecognised title defaults to tee",
      prod(SID, "900000000005")["product_type"] == "tee")
r = post("/api/sets/%s/products" % SID, {
    "product_id": "900000000005", "product_type": "x"})
check("adding the same id again is a no-op", r.status_code == 200)
mock.listings["900000000006"] = listing(
    "900000000006", "Mystery Garment 2", ["Black"], ["S"], "20.00")
r = post("/api/sets/%s/products" % SID, {
    "product_id": "900000000006", "product_type": VN})
check("add with an explicit type stores it", r.status_code == 200
      and prod(SID, "900000000006")["product_type"] == VN)
mock.listings["900000000007"] = listing(
    "900000000007", "Mystery Garment 3", ["Black"], ["S"], "20.00")
r = post("/api/sets/%s/products" % SID, {
    "product_id": "900000000007", "product_type": "nope"})
check("add with an unknown type refused", r.status_code == 400
      and prod(SID, "900000000007") is None)
for pid in ("900000000004", "900000000005", "900000000006"):
    post("/api/sets/%s/products/%s/remove" % (SID, pid))
check("test products removed", all(prod(SID, p) is None for p in (
    "900000000004", "900000000005", "900000000006")))

# legacy product with no stored type: refresh stores the type from the
# OLD title, so a later Shopify rename cannot silently move the template
mock.listings["900000000008"] = listing(
    "900000000008", "Oregon Ducks Crewneck Sweatshirt", ["Black"], ["S"],
    "34.00")
post("/api/sets/%s/products" % SID, {"product_id": "900000000008"})
sets = sets_now()
for q in sets[SID]["products"]:
    if q["product_id"] == "900000000008":
        q.pop("product_type", None)
app_module.save_sets(sets)
check("legacy entry has no stored type",
      "product_type" not in prod(SID, "900000000008"))
mock.listings["900000000008"]["title"] = "Ducks Cozy Pullover"
post("/api/sets/%s/products/900000000008/refresh" % SID)
p = prod(SID, "900000000008")
check("refresh stored the type from the old title",
      p["product_type"] == "crewneck", p.get("product_type"))
check("renamed legacy product keeps its crewneck template",
      p["title"] == "Ducks Cozy Pullover" and pt.template_url(p)
      == FRONT + "crewneck-front.png")
post("/api/sets/%s/products/900000000008/remove" % SID)

# rename is local-only: a store product's title comes from Shopify
r = post("/api/sets/%s/products/900000000001/title" % SID,
         {"title": "Something"})
check("rename of a store product refused (Shopify owns the title)",
      r.status_code == 400 and "shopify" in r.get_json()["error"].lower(),
      r.get_json())

# duplicate keeps local products and types
r = post("/api/sets/%s/local-products" % SID, {"type": LS})
check("a fresh local long sleeve can be added again after linking",
      r.status_code == 201)
r = post("/api/sets/%s/duplicate" % SID)
dup = r.get_json()
check("duplicate keeps local product + stored types",
      any(q["product_id"] == "local:" + LS and q["product_type"] == LS
          for q in dup["products"]), [q["product_id"] for q in dup[
              "products"]])
post("/api/sets/%s/delete" % dup["id"])
post("/api/sets/%s/products/local:%s/remove" % (SID, LS))

# ================================================================ 9
# The 6-product set: legacy three (non-rectangular tee, as live) + the
# new three. Grouped chunks each hold 95 or fewer variants.
def build_six(vneck_sizes, link=False):
    r = post("/api/campaigns", {"name": "Six products %d" % len(vneck_sizes)
                                + ("L" if link else ""),
                                "slug": "six-%d%s" % (len(vneck_sizes),
                                                      "l" if link else "")})
    sid = r.get_json()["id"]
    tee_colours = ["Ash", "Black", "Dark Heather", "Gold", "Irish Green",
                   "Navy", "Orange", "Purple", "Red", "Royal", "Sport Grey",
                   "White"]
    eight = ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]
    six = ["S", "M", "L", "XL", "2XL", "3XL"]
    legacy = [
        ("15469998538906", "Oregon Ducks Unisex Tee", tee_colours, eight,
         "18.88", 8),   # 12 x 8 = 96 pairs, 88 real variants
        ("15470002929818", "Oregon Ducks Hoodie", [
            "Black", "Navy", "Red", "Royal", "Gold", "Purple", "White",
            "Sport Grey"], six, "44.00", 0),
        ("15470004568218", "Oregon Ducks Crewneck Sweatshirt", [
            "Black", "Navy", "Red", "Royal", "Gold", "Purple", "White",
            "Sport Grey"], six, "34.00", 0),
    ]
    for pid, title, cols, sizes, price, holes in legacy:
        mock.listings[pid] = listing(pid, title, cols, sizes, price,
                                     holes=holes)
        post("/api/sets/%s/products" % sid, {"product_id": pid})
    if link:
        news = [("910000000001", "Oregon Ducks Long Sleeve Tee", LS),
                ("910000000002", "Oregon Ducks Classic Long Sleeve Tee", CLS),
                ("910000000003", "Oregon Ducks V-Neck Tee", VN)]
        for pid, title, key in news:
            st = pt.starter_for(key)
            # The V-neck listing is built with the size list under test;
            # the starter default (S-2XL) no longer stands in for it.
            sizes = vneck_sizes if key == VN else st["sizes"]
            mock.listings[pid] = listing(pid, title, st["colours"], sizes,
                                         st["price"])
            post("/api/sets/%s/local-products" % sid, {"type": key})
            post("/api/sets/%s/products/local:%s/variants" % (sid, key),
                 {"sizes": sizes})
            r = post("/api/sets/%s/products" % sid, {
                "product_id": pid, "link_local": "local:" + key})
            assert r.status_code == 200, r.get_json()
    else:
        for key in (LS, CLS, VN):
            post("/api/sets/%s/local-products" % sid, {"type": key})
        post("/api/sets/%s/products/local:%s/variants" % (sid, VN),
             {"sizes": vneck_sizes})
    sets = sets_now()
    sets[sid]["master_placement"] = dict(MASTER)
    sets[sid]["design_url"] = "/static/uploads/fake.png"
    sets[sid]["grouping"] = "grouped"
    app_module.save_sets(sets)
    return sid


for n_sizes, vsizes in ((5, ["S", "M", "L", "XL", "2XL"]),
                        (6, ["S", "M", "L", "XL", "2XL", "3XL"])):
    for linked in (False, True):
        tag = "%d-size v-neck, %s" % (n_sizes, "linked" if linked
                                      else "local")
        sid = build_six(vsizes, link=linked)
        # Variants actually created: the tee has 12 x 8 = 96 selected
        # pairs but 88 real variants (8 unpriced pairs are skipped), so
        # 184 + 88 + 30 + 4n. The variant-count endpoint reports the
        # CREATED count (the same number publish creates), not the
        # selected grid: 184 + 88 + 30 + 4n.
        total = 184 + 88 + 30 + 4 * n_sizes
        check(tag + ": six products in the set",
              len(sets_now()[sid]["products"]) == 6)
        vs = get("/api/sets/%s/variant-count" % sid).get_json()
        check(tag + ": variant-count reports created pairs = %d"
              % total, vs["total_combine"] == total,
              vs["total_combine"])
        check(tag + ": grouped guard ok", vs["guard_ok"] is True)
        msg = vs["message"].lower()
        check(tag + ": no limit text in grouped mode",
              not any(w in msg for w in ("limit", "100", "95", "listings",
                                         "shopify")), vs["message"])
        r = post("/api/sets/%s/publish" % sid, {"dry_run": True})
        j = r.get_json()
        check(tag + ": grouped dry run 200", r.status_code == 200,
              (r.status_code, j))
        if r.status_code != 200:
            continue
        sizes = [len(x["variants"]) for x in j["products"]]
        check(tag + ": chunks sum to %d" % total, sum(sizes) == total, sizes)
        check(tag + ": every chunk <= 95", all(x <= 95 for x in sizes),
              sizes)
        check(tag + ": %d listings" % math.ceil(total / 95),
              len(sizes) == math.ceil(total / 95), sizes)
        keys = [(v["option1"], v["option2"], v["option3"])
                for x in j["products"] for v in x["variants"]]
        check(tag + ": every variant lands in exactly one chunk "
              "(no duplicate Style/Color/Size)", len(keys) == len(set(keys)))
        styles = {k[0] for k in keys}
        check(tag + ": six Style values", len(styles) == 6, styles)
        by_style = {}
        for k in keys:
            by_style[k[0]] = by_style.get(k[0], 0) + 1
        check(tag + ": per-product counts 88/48/48/88/30/%d" % (4 * n_sizes),
              sorted(by_style.values()) == sorted(
                  [88, 48, 48, 88, 30, 4 * n_sizes]), by_style)
        blob = json.dumps(j.get("warnings", [])).lower() + \
            j["variant_summary"]["message"].lower()
        check(tag + ": preview shows no limit text",
              "limit" not in blob and "100-variant" not in blob, blob)
        skipped_warn = [w for w in j["warnings"] if "no store price" in w]
        check(tag + ": only the tee has unpriced pairs (8 skipped)",
              len(skipped_warn) == 1 and "(8)" in skipped_warn[0]
              and "Unisex Tee" in skipped_warn[0], j["warnings"])
        unlinked = [w for w in j["warnings"] if "not linked" in w.lower()]
        if linked:
            check(tag + ": no unlinked warning", unlinked == [], unlinked)
            check(tag + ": checklist ready for all six", all(
                row["ready"] for row in j["checklist"]), j["checklist"])
        else:
            check(tag + ": unlinked warning names the 3 local products",
                  len(unlinked) == 1 and all(t in unlinked[0] for t in (
                      "Long Sleeve Tee", "Classic Long Sleeve",
                      "V-Neck Tee")), unlinked)
            ready = {row["title"]: row["ready"] for row in j["checklist"]}
            check(tag + ": local rows are not 'ready'; store rows are",
                  sum(1 for v in ready.values() if v) == 3
                  and sum(1 for v in ready.values() if not v) == 3, ready)
        # combine refuses the full set (over the 100 cap)
        sets = sets_now()
        sets[sid]["grouping"] = "combine"
        app_module.save_sets(sets)
        r = post("/api/sets/%s/publish" % sid, {"dry_run": True})
        check(tag + ": combine refuses the full set (created count %d)"
              % total, r.status_code == 400
              and "Combine mode" in r.get_json()["error"]
              and str(total) in r.get_json()["error"], r.get_json())
        vs = get("/api/sets/%s/variant-count" % sid).get_json()
        check(tag + ": combine guard reports over the limit",
              vs["guard_ok"] is False and "Over the limit" in vs["message"])
        # split: every product fits on its own
        sets = sets_now()
        sets[sid]["grouping"] = "split"
        app_module.save_sets(sets)
        r = post("/api/sets/%s/publish" % sid, {"dry_run": True})
        check(tag + ": split allows the 6 products (each <= 100)",
              r.status_code == 200 and sorted(
                  len(x["variants"]) for x in r.get_json()["products"])
              == sorted([88, 48, 48, 88, 30, 4 * n_sizes]), r.get_json()
              if r.status_code != 200 else "")
        # back to grouped
        sets = sets_now()
        sets[sid]["grouping"] = "grouped"
        app_module.save_sets(sets)
        # a REAL publish is blocked for unlinked local products, and
        # never reaches Shopify (the mock fails the suite if it does)
        if not linked:
            r = post("/api/sets/%s/publish" % sid, {})
            check(tag + ": real publish blocked while products are "
                  "unlinked", r.status_code == 400 and "link" in r.get_json(
                  )["error"].lower(), r.get_json())
            check(tag + ": blocked publish lists the 3 local products",
                  len(r.get_json().get("products", [])) == 3,
                  r.get_json())
            check(tag + ": publish state untouched",
                  sets_now()[sid].get("publish_state") == "draft")
check("no real publish was attempted", mock.created_live == [])

# v-neck without sizes keeps the dry run honest (blocks, names sizes)
sid = build_six(["S", "M", "L", "XL", "2XL"])
post("/api/sets/%s/products/local:%s/variants" % (sid, VN), {"sizes": []})
r = post("/api/sets/%s/publish" % sid, {"dry_run": True})
check("v-neck with no sizes blocks the dry run and says why",
      r.status_code == 400 and any(
          "sizes" in x["missing"] for x in r.get_json()["products"]),
      r.get_json())

# ================================================================ 10
r = get("/campaigns/%s/designer" % SID)
page = r.get_data(as_text=True)
check("designer page 200", r.status_code == 200)
check("designer ships the type table", "PRODUCT_TYPES" in page
      and "longsleeve-front.png" in page and "vneck-front.png" in page)
check("designer page has the add-type controls",
      'id="localTypeButtons"' in page and 'id="linkLocalSelect"' in page
      and "addLocalProduct" in js_src)
check("designer page has no catalog card", "Catalog products" not in page)
m = page.split("window.PRODUCT_TYPES = ", 1)
ok_json = False
if len(m) == 2:
    blob = m[1].split(";\n", 1)[0]
    try:
        embedded = json.loads(blob)
        ok_json = set(embedded) == set(pt.PRODUCT_TYPES)
    except ValueError:
        ok_json = False
check("embedded type table is valid JSON with all six types", ok_json)
check("app.js has the add / link / rename / type controls",
      all(w in js_src for w in ("addLocalProduct", "saveProductType",
                                "renameLocalProduct", "linkLocalSelect")))

# ================================================================ 11
BOXES = {
    "crewneck-front.png": (240, 761, 166, 533),
    "longsleeve-front.png": (240, 761, 153, 540),
    "vneck-front.png": (240, 761, 166, 533),
    "hoodie-front.png": (240, 761, 159, 479),
}
for fname, (x0, x1, y0, y1) in BOXES.items():
    L = np.array(Image.open(os.path.join(TPL_DIR, fname)).convert(
        "RGBA"))[..., 0].astype(int)
    ghost = 0
    for y in range(y0 - 4, y1 + 5):
        for x in range(x0 - 4, x1 + 5):
            on_h = abs(y - y0) <= 4 or abs(y - y1) <= 4
            on_v = abs(x - x0) <= 4 or abs(x - x1) <= 4
            v = L[y, x]
            if v in (140, 180):
                continue
            for dx, dy, on in ((0, 5, on_h), (5, 0, on_v)):
                if on and L[y - dy, x - dx] == L[y + dy, x + dx] \
                        and L[y - dy, x - dx] not in (140, 180) \
                        and L[y - dy, x - dx] != v:
                    ghost += 1
                    break
    check(fname + " has no ghost dashes (placebox is the only box)",
          ghost <= 12, ghost)

# ---------------------------------------------------------------- end
check("temp data dir used", app_module.DATA_FILE.startswith(_TMP))
check("real data/sets.json untouched (byte-identical)",
      _real_hash() == _REAL_BEFORE)

print("%d passed, %d failed, %d skipped" % (passed, len(failed),
                                            len(skipped)))
for f in failed:
    print("FAIL:", f)
for s in skipped:
    print("SKIP:", s)
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if failed else 0)
