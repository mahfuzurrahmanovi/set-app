"""Phone-viewport check of the designer for the 3 new types (2026-11-07).

OPTIONAL, local only: needs `playwright` with a Chromium build, which
is NOT in requirements.txt (Render never runs this). If playwright or
Chromium is missing the script says so and exits 0 without checking.

    python server/new_types_phone_check.py [screenshot_dir]

Starts the app on a random local port against a temporary data
directory (never data/sets.json), seeds a set with the live master
placement (x 0.5, y 0.47, scale 0.32, angle 0) and a stand-in badge
(the real Oregon badge file is not in the package), adds the three
local types, then at 390x844 (phone) checks for each type: the right
outline is shown, the placebox is the single dashed box, the badge is
placed and inside the image, the page does not scroll sideways, the
buttons are touch-sized, and Preview mockup works. Saves screenshots.
No Shopify, no publish.
"""

import json
import os
import socket
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="phone_check_")
os.environ["SETAPP_DATA_ROOT"] = TMP
os.environ.pop("SET_APP_PASSWORD", None)
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(TMP, "shots")
os.makedirs(OUT, exist_ok=True)

try:
    from playwright.sync_api import sync_playwright
except Exception:
    print("playwright is not installed: phone check skipped")
    sys.exit(0)

import numpy as np
from PIL import Image

import app as app_module

app_module.DATA_FILE = os.path.join(TMP, "sets.json")
app_module.UPLOAD_DIR = os.path.join(TMP, "uploads")
app_module.MOCKUP_DIR = os.path.join(TMP, "mockups")

passed, failed = 0, []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(name + (" :: " + str(detail) if detail else ""))


# stand-in badge: transparent PNG, green disc with a yellow ring
badge = os.path.join(TMP, "badge.png")
size = 600
yy, xx = np.ogrid[:size, :size]
d = np.sqrt((xx - size / 2) ** 2 + (yy - size / 2) ** 2)
a = np.zeros((size, size, 4), dtype=np.uint8)
a[d <= size / 2 - 2] = (255, 213, 0, 255)
a[d <= size * 0.40] = (0, 110, 50, 255)
Image.fromarray(a, "RGBA").save(badge)

c = app_module.app.test_client()
tok = c.get("/api/csrf-token").get_json()["csrf_token"]
H = {"X-CSRF-Token": tok, "Content-Type": "application/json"}
sid = c.post("/api/campaigns", data=json.dumps(
    {"name": "Phone check", "slug": "phone-check"}), headers=H
).get_json()["id"]
c.post("/api/sets/%s/master" % sid, data=json.dumps({"placement": {
    "x": 0.5, "y": 0.47, "scale": 0.32, "angle": 0}}), headers=H)
c.post("/api/sets/%s/upload" % sid, data={"design": (open(badge, "rb"),
                                                     "badge.png")},
       headers={"X-CSRF-Token": tok}, content_type="multipart/form-data")
for key in ("long-sleeve", "classic-long-sleeve", "v-neck"):
    c.post("/api/sets/%s/local-products" % sid,
           data=json.dumps({"type": key}), headers=H)

s = socket.socket()
s.bind(("127.0.0.1", 0))
port = s.getsockname()[1]
s.close()
threading.Thread(target=lambda: app_module.app.run(
    host="127.0.0.1", port=port, threaded=True, use_reloader=False),
    daemon=True).start()
import time
time.sleep(1.5)

TYPES = [("local:long-sleeve", "longsleeve-front.png"),
         ("local:classic-long-sleeve", "longsleeve-front.png"),
         ("local:v-neck", "vneck-front.png")]
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  device_scale_factor=2, has_touch=True,
                                  is_mobile=True)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:%d/campaigns/%s/designer" % (port, sid))
        page.wait_for_selector(".prodcard", timeout=15000)
        check("three product cards shown", page.locator(
            ".prodcard").count() == 3, page.locator(".prodcard").count())
        check("page does not scroll sideways", page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"))
        check("add-type buttons rendered (3, all 'In set')",
              page.locator("#localTypeButtons button").count() == 3
              and page.locator("#localTypeButtons button[disabled]"
                               ).count() == 3)
        for pid, tpl in TYPES:
            page.evaluate("selectProduct('%s')" % pid)
            page.wait_for_function(
                "document.getElementById('centreImg').src.indexOf('%s') > -1"
                % tpl, timeout=10000)
            page.wait_for_function(
                "document.getElementById('designImg') && "
                "document.getElementById('designImg').naturalWidth > 0",
                timeout=10000)
            tag = pid.split(":")[1]
            check(tag + ": shows " + tpl, tpl in page.evaluate(
                "document.getElementById('centreImg').src"))
            check(tag + ": exactly one dashed placebox",
                  page.locator(".placebox").count() == 1)
            box = page.evaluate("""(function(){
              var w=document.getElementById('centreWrap').getBoundingClientRect();
              var b=document.getElementById('placeBox').getBoundingClientRect();
              var d=document.getElementById('designImg').getBoundingClientRect();
              return {w:w.width,h:w.height,
                bl:(b.left-w.left)/w.width, bt:(b.top-w.top)/w.height,
                bw:b.width/w.width, bh:b.height/w.height,
                dx:((d.left+d.right)/2-w.left)/w.width,
                dy:((d.top+d.bottom)/2-w.top)/w.height,
                dw:d.width/w.width};})()""")
            check(tag + ": placebox is 25/20/50/50 of the mockup",
                  abs(box["bl"] - .25) < .01 and abs(box["bt"] - .20) < .01
                  and abs(box["bw"] - .50) < .01
                  and abs(box["bh"] - .50) < .01, box)
            check(tag + ": badge centred at x 0.50, y 0.47, width 0.32",
                  abs(box["dx"] - .5) < .01 and abs(box["dy"] - .47) < .01
                  and abs(box["dw"] - .32) < .01, box)
            check(tag + ": badge inside the image (not clipped)",
                  box["dx"] - box["dw"] / 2 > 0
                  and box["dx"] + box["dw"] / 2 < 1)
            page.locator("#centreWrap").screenshot(path=os.path.join(
                OUT, "phone-%s-mockup.png" % tag))
            page.locator(".prodcard.selected").scroll_into_view_if_needed()
            page.screenshot(path=os.path.join(OUT, "phone-%s-card.png"
                                              % tag))
            # Preview mockup works for the local type (renders on outline)
            # (the card re-renders after a preview, so the "Preview
            # ready" note is replaced at once: check the stored render)
            page.evaluate("previewMockup('%s')" % pid)
            page.wait_for_function(
                "currentSet.products.filter(function(x){return x."
                "product_id==='%s'})[0].mockups.length > 0" % pid,
                timeout=20000)
            murl = page.evaluate(
                "currentSet.products.filter(function(x){return x."
                "product_id==='%s'})[0].mockups[0]" % pid)
            resp = page.request.get("http://127.0.0.1:%d%s" % (port, murl))
            check(tag + ": Preview mockup renders and the file is served",
                  resp.status == 200 and resp.headers.get(
                      "content-type", "").startswith("image/"), murl)
            tall = page.evaluate("""(function(){
              var bs=[].slice.call(document.querySelectorAll(
                '.prodcard button, #localTypeButtons button'));
              return bs.filter(function(b){var r=b.getBoundingClientRect();
                return r.width>0 && r.height>0 && r.height<36;}).length;})()""")
            check(tag + ": product buttons are touch-sized (>= 36px)",
                  tall == 0, tall)
        check("no JavaScript errors on the page", errors == [], errors)
        check("page still does not scroll sideways", page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"))
        browser.close()
except Exception as exc:
    msg = str(exc)
    if "Executable doesn't exist" in msg or "playwright install" in msg:
        print("Chromium is not available: phone check skipped")
        sys.exit(0)
    raise

print("%d passed, %d failed" % (passed, len(failed)))
for f in failed:
    print("FAIL:", f)
print("screenshots:", OUT)
sys.exit(1 if failed else 0)
