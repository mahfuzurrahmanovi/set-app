"""Fix tests 2.1: bare-photo centre mockup + visible mockup reorder.

Runs against a COPY of the data dir, never the real sets.json.
Shopify is never called: get_product_image is monkeypatched.
Run: .venv/bin/python server/fix_test.py
"""

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from PIL import Image, ImageDraw  # noqa: E402

import app as app_module  # noqa: E402
import shopify as shopify_api  # noqa: E402

REAL_SETS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "sets.json",
)

PASSED = []
FAILED = []


def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"  PASS {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name} {detail}")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def make_photo(path, size=(600, 700), color=(180, 200, 230)):
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 500, 600], outline=(90, 90, 90), width=4)
    img.save(path, "JPEG", quality=92)


def make_design(path):
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([100, 100, 300, 300], fill=(255, 0, 0, 255))
    img.save(path, "PNG")


def main():
    real_hash_before = sha(REAL_SETS)
    tmp = tempfile.mkdtemp(prefix="setapp-fix-test-")
    try:
        data_dir = os.path.join(tmp, "data")
        os.makedirs(data_dir)
        shutil.copy(REAL_SETS, os.path.join(data_dir, "sets.json"))
        app_module.DATA_FILE = os.path.join(data_dir, "sets.json")
        app_module.UPLOAD_DIR = os.path.join(tmp, "uploads")
        app_module.MOCKUP_DIR = os.path.join(tmp, "mockups")
        os.makedirs(app_module.UPLOAD_DIR, exist_ok=True)
        client = app_module.app.test_client()

        # Fix round 3: POSTs now need a CSRF token. Wrap post() so every
        # call in this file fetches the session token first.
        _raw_post = client.post

        def _post(*args, **kwargs):
            token = client.get("/api/csrf-token").get_json()["csrf_token"]
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["X-CSRF-Token"] = token
            return _raw_post(*args, headers=headers, **kwargs)

        client.post = _post

        photo = os.path.join(tmp, "photo.jpg")
        make_photo(photo)
        design = os.path.join(tmp, "design.png")
        make_design(design)
        # Fix round 3: renders only accept server-issued /static/ URLs.
        shutil.copy(photo, os.path.join(app_module.UPLOAD_DIR, "photo.jpg"))
        photo = "/static/uploads/photo.jpg"
        shutil.copy(design, os.path.join(app_module.UPLOAD_DIR, "design.png"))
        design = "/static/uploads/design.png"
        sid = "oregon-ducks-set"
        tee = "15469998538906"

        print("== 1. Baseline: Oregon set, no design ==")
        r = client.get("/api/sets")
        oregon = [s for s in r.get_json() if s["id"] == sid][0]
        check("oregon 3 products, no design",
              len(oregon["products"]) == 3
              and not oregon.get("design_url"))
        check("oregon products have no stored images",
              all(not p.get("mockups") and not p.get("hero_image")
                  and not p.get("images") and not p.get("image")
                  for p in oregon["products"]))

        print("== 2. Preview mockup with NO design renders bare photo ==")
        r = client.post(f"/api/sets/{sid}/mockups",
                        json={"photos": {tee: photo}})
        check("no-design mockup 200", r.status_code == 200,
              str(r.status_code) + " " + r.get_data(as_text=True)[:200])
        j = r.get_json() or {}
        url = (j.get("mockups") or {}).get(tee)
        check("no-design mockup url returned", bool(url), str(j)[:200])
        if url:
            local = os.path.join(app_module.MOCKUP_DIR,
                                 os.path.basename(url))
            check("bare mockup file exists", os.path.exists(local))
            if os.path.exists(local):
                im = Image.open(local)
                check("bare mockup is the photo size",
                      im.size == (600, 700), str(im.size))
        r = client.get("/api/sets")
        oregon = [s for s in r.get_json() if s["id"] == sid][0]
        tee_p = [p for p in oregon["products"]
                 if p["product_id"] == tee][0]
        check("bare mockup stored on product",
              bool(tee_p.get("mockups")), str(tee_p.get("mockups")))

        print("== 3. Preview mockup with empty-string design also works ==")
        r = client.post(f"/api/sets/{sid}/mockups",
                        json={"design": "", "photos": {tee: photo}})
        check("empty-design mockup 200", r.status_code == 200,
              str(r.status_code))

        print("== 4. Preview mockup WITH design still works ==")
        r = client.post(f"/api/sets/{sid}/mockups",
                        json={"design": design, "photos": {tee: photo}})
        check("with-design mockup 200", r.status_code == 200,
              str(r.status_code))
        j = r.get_json() or {}
        url2 = (j.get("mockups") or {}).get(tee)
        check("with-design mockup url returned", bool(url2))

        print("== 5. Photo endpoint ==")
        r = client.get(f"/api/sets/{sid}/products/{tee}/photo")
        j = r.get_json() or {}
        check("photo endpoint returns stored mockup",
              r.status_code == 200 and j.get("photo")
              and j.get("source") == "mockup", str(j)[:200])

        hoodie = "15470002929818"
        orig = shopify_api.get_product_image
        shopify_api.get_product_image = lambda pid: "https://cdn.example/x.jpg"  # noqa: E731
        try:
            r = client.get(f"/api/sets/{sid}/products/{hoodie}/photo")
            j = r.get_json() or {}
            check("photo endpoint falls back to Shopify image",
                  r.status_code == 200
                  and j.get("photo") == "https://cdn.example/x.jpg"
                  and j.get("source") == "shopify", str(j)[:200])
        finally:
            shopify_api.get_product_image = orig

        def _boom(pid):
            raise RuntimeError("no token")
        shopify_api.get_product_image = _boom
        try:
            r = client.get(f"/api/sets/{sid}/products/{hoodie}/photo")
            j = r.get_json() or {}
            check("photo endpoint honest on Shopify failure",
                  r.status_code == 200 and j.get("photo") is None
                  and bool(j.get("error")), str(j)[:200])
        finally:
            shopify_api.get_product_image = orig

        print("== 6. Mockup order: visible block + reorder works ==")
        html = client.get("/").get_data(as_text=True)
        check("served template contains visible Mockup order block",
              "Mockup order" in html)
        check("served template gates reorder on 2+ mockups",
              "(p.mockups || []).length >= 2" in html)
        check("reorder block is a visible div, not collapsed details",
              "<div><h3>Mockup order</h3>" in html)
        # Give the tee 2 mockups via the test copy, then reorder.
        copy_path = os.path.join(data_dir, "sets.json")
        data = json.load(open(copy_path))
        data[sid]["products"][0]["mockups"] = ["/static/mockups/a.jpg",
                                               "/static/mockups/b.jpg"]
        json.dump(data, open(copy_path, "w"), indent=2)
        r = client.get("/api/sets")
        oregon = [s for s in r.get_json() if s["id"] == sid][0]
        check("product with 2 mockups returns both",
              [p for p in oregon["products"]
               if p["product_id"] == tee][0]["mockups"]
              == ["/static/mockups/a.jpg", "/static/mockups/b.jpg"])
        r = client.post(
            f"/api/sets/{sid}/products/{tee}/mockups/reorder",
            json={"order": ["/static/mockups/b.jpg",
                            "/static/mockups/a.jpg"]})
        check("reorder endpoint 200", r.status_code == 200,
              str(r.status_code) + " " + r.get_data(as_text=True)[:200])
        r = client.get("/api/sets")
        oregon = [s for s in r.get_json() if s["id"] == sid][0]
        check("reorder swapped the mockups",
              [p for p in oregon["products"]
               if p["product_id"] == tee][0]["mockups"]
              == ["/static/mockups/b.jpg", "/static/mockups/a.jpg"])

        print("== 7. Catalog template photo (no Shopify call) ==")
        r2 = client.get("/api/catalog/templates")
        templates = r2.get_json() or []
        check("catalog templates list non-empty", bool(templates))
        if templates:
            tid = templates[0]["product_id"]
            r = client.post(f"/api/sets/{sid}/catalog-templates",
                            json={"product_ids": [tid]})
            check("catalog template added", r.status_code == 200,
                  str(r.status_code) + " "
                  + r.get_data(as_text=True)[:200])
            r = client.get(f"/api/sets/{sid}/products/{tid}/photo")
            j = r.get_json() or {}
            check("catalog photo returned without Shopify",
                  r.status_code == 200 and bool(j.get("photo"))
                  and j.get("source") in ("catalog", "hero")
                  and "printify.com" in j.get("photo", ""),
                  str(j)[:200])

        print("== 8. Regressions ==")
        check("real sets.json byte-identical",
              sha(REAL_SETS) == real_hash_before)
        r = client.get("/api/sets")
        oregon = [s for s in r.get_json() if s["id"] == sid][0]
        check("oregon set still loads, master kept",
              oregon["master_placement"]["x"] == 0.5
              and oregon["master_placement"]["scale"] == 0.32)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", FAILED)
        sys.exit(1)


if __name__ == "__main__":
    main()
