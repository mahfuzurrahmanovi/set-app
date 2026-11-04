"""Part 7 fixes (Ovi, 2026-11-04 22:08 phone review of live 3f99848).

1. Phone product card: title must not wrap one letter per line; the
   Remove button must not squeeze it. Header is a real class with
   thumb shrink-proof, title flexing with normal word wrap, and a
   button that is width:auto, nowrap, shrink-proof.
2. Mockup: exactly ONE dashed print area. Chosen approach: strip the
   baked-in dashed box from the template images themselves, so the
   app's fixed placebox (25%/20%/50%/50%) is the only dashed area.
   Gemini templates: red dashed box pixels must be gone. Ovi's tee
   screenshot: its dashed box edges (x=220 and x=400, y=163 and
   y=369) must be gone.
3. Grouped is the default for NEW sets, tapping a grouping button
   saves to the server at once and refreshes the variant count, and
   Grouped mode shows NO text about the 100 limit, 95 chunking, or
   any limit at all: just total variants and one campaign link.
   Combine mode keeps its own warning.

FAILS before, PASSES after. Temp data root only, mock Shopify only,
never touches real data/sets.json, never publishes live.
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_SETS = os.path.join(os.path.dirname(HERE), "data", "sets.json")

import hashlib  # noqa: E402


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


real_hash_before = sha(REAL_SETS)
TMP = tempfile.mkdtemp(prefix="setapp_part7_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ["SET_APP_PASSWORD"] = "part7-test-password"
os.environ["FLASK_SECRET_KEY"] = "part7-test-secret"
sys.path.insert(0, HERE)
import app as app_module  # noqa: E402

PASSED, FAILED = [], []


def check(name, ok, extra=""):
    (PASSED if ok else FAILED).append(name)
    print(("  PASS " if ok else "  FAIL ") + name +
          ("" if ok else " :: " + str(extra)[:300]))


def read(rel):
    with open(os.path.join(HERE, rel)) as f:
        return f.read()


js = read("static/app.js")
css = read("static/app.css")
designer_html = read("templates/designer.html")
app_py = read("app.py")

# 1. Phone product card header
check("prodcard header uses a dedicated class, not bare flex div",
      "prodcard-header" in js)
check("prodcard header button is width:auto, nowrap, shrink-proof",
      "prodcard-header button" in css and "width: auto" in css and
      "white-space: nowrap" in css and "flex-shrink: 0" in css)
check("prodcard title wraps with break-word, not anywhere",
      "prodtitle" in css and "overflow-wrap: break-word" in css)
check("prodcard header title div is flex:1 with min-width:0",
      "prodcard-header .prodtitle" in css and "flex: 1" in css and
      "min-width: 0" in css)
check("phone media query wraps prodcard header",
      "@media (max-width: 480px)" in css and
      "prodcard-header" in css.split("@media (max-width: 480px)")[-1])

# 2. Template images: baked-in dashed box stripped
from PIL import Image  # noqa: E402

tmpl_dir = os.path.join(HERE, "static", "design-area-templates")
for name in ("hoodie-front.png", "crewneck-front.png",
             "longsleeve-front.png", "vneck-front.png",
             "shortsleeve-back.png"):
    im = Image.open(os.path.join(tmpl_dir, name)).convert("RGBA")
    red = sum(1 for r, g, b, a in im.getdata()
              if a > 50 and r > 180 and g < 100 and b < 100)
    check("no red dashed box left in " + name, red == 0, "red=%d" % red)

tee = Image.open(os.path.join(tmpl_dir,
                              "shortsleeve-front.png")).convert("RGBA")


def dark_on_line(xs, ys):
    n = 0
    for x, y in zip(xs, ys):
        r, g, b, a = tee.getpixel((x, y))
        if r < 180 and g < 180 and b < 180:
            n += 1
    return n


check("tee screenshot left dashed edge stripped",
      dark_on_line([220] * 207, range(163, 370)) < 10)
check("tee screenshot right dashed edge stripped",
      dark_on_line([400] * 207, range(163, 370)) < 10)
check("tee screenshot top/bottom dashed edges stripped",
      dark_on_line(range(220, 401), [163] * 181) < 10 and
      dark_on_line(range(220, 401), [369] * 181) < 10)
check("tee garment outline still present",
      dark_on_line([155] * 207, range(163, 370)) > 20)

# 3. Grouped default, instant save, no limit text in grouped
check("new sets are created with grouping grouped, not combine",
      app_py.count('"grouping": "grouped"') >= 2 and
      '"grouping": "combine"' not in app_py)
check("setGrouping saves grouping to the server at once",
      "async function setGrouping" in js and
      "postSet('/details'" in js and "grouping: g" in js)
check("setGrouping refreshes the variant count at once",
      "renderVariantCount" in js.split("function setGrouping")[1].split(
          "async function saveDetails")[0])
test_set = {"products": [
    {"product_id": "a", "colours": ["c%d" % i for i in range(14)],
     "sizes": ["s%d" % i for i in range(16)]},
]}
test_set["grouping"] = "grouped"
summary = app_module.variant_summary(test_set)
check("grouped summary shows total and one campaign link, no limit text",
      summary["total_combine"] == 224 and
      "one campaign link" in summary["message"] and
      "100" not in summary["message"] and
      "95" not in summary["message"] and
      "limit" not in summary["message"].lower() and
      "chunk" not in summary["message"].lower())
test_set["grouping"] = "combine"
summary_c = app_module.variant_summary(test_set)
check("combine mode keeps its own over-limit warning",
      "100" in summary_c["message"] and not summary_c["guard_ok"])
check("designer grouped paragraph has no limit text",
      "95" not in designer_html and "100 variants per product" not in
      designer_html)
check("grouped button label has no variant cap text",
      "up to ~500 variants" not in designer_html and
      "Grouped: one link" in designer_html)

print("PASSED %d FAILED %d" % (len(PASSED), len(FAILED)))
assert real_hash_before == sha(REAL_SETS), "real sets.json changed!"
assert not FAILED, FAILED
