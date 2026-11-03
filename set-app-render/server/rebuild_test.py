"""Rebuild tests for the set app (2026-11-03).

Runs against a COPY of the data dir, never the real sets.json.
Shopify is never called: create_draft_product is monkeypatched, and
dry-run mode is asserted to skip the client entirely.
Run: .venv/bin/python server/rebuild_test.py
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


def make_png(path, size=(800, 800), transparent=True, fmt="PNG"):
    img = Image.new("RGBA" if transparent else "RGB", size,
                    (0, 0, 0, 0) if transparent else (255, 255, 255))
    if transparent:
        draw = ImageDraw.Draw(img)
        draw.ellipse([300, 300, 500, 500], fill=(255, 255, 255, 255))
    img.save(path, fmt)


def main():
    real_hash_before = sha(REAL_SETS)
    tmp = tempfile.mkdtemp(prefix="setapp-test-")
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

        print("== 1. Seeded Oregon set intact ==")
        r = client.get("/api/sets")
        sets = r.get_json()
        oregon = [s for s in sets if s["id"] == "oregon-ducks-set"][0]
        ids = [p["product_id"] for p in oregon["products"]]
        check("oregon 3 products", ids == [
            "15469998538906", "15470002929818", "15470004568218"], str(ids))
        check("oregon all locked",
              all(p["locked"] for p in oregon["products"]))
        check("oregon master kept",
              oregon["master_placement"]["x"] == 0.5
              and oregon["master_placement"]["scale"] == 0.32)
        check("oregon titles kept",
              oregon["products"][0]["title"] == "Oregon Ducks Unisex Tee")

        print("== 2. Set details ==")
        r = client.post("/api/sets", json={"name": "Test Set"})
        sid = r.get_json()["id"]
        check("new set defaults",
              r.get_json()["grouping"] == "combine"
              and r.get_json()["publish_state"] == "draft")
        r = client.post(f"/api/sets/{sid}/details",
                        json={"name": "x" * 256})
        check("title 256 chars rejected", r.status_code == 400, str(r.status_code))
        r = client.post(f"/api/sets/{sid}/details", json={
            "name": "Test Set 2", "description": "A test set",
            "tags": "ducks, fan gift", "grouping": "split"})
        j = r.get_json()
        check("details saved",
              j["name"] == "Test Set 2" and j["description"] == "A test set"
              and j["tags"] == ["ducks", "fan gift"]
              and j["grouping"] == "split", str(j))
        r = client.post(f"/api/sets/{sid}/details", json={"grouping": "bogus"})
        check("bad grouping rejected", r.status_code == 400)

        print("== 3. Catalog templates ==")
        r = client.get("/api/catalog/templates")
        templates = r.get_json()
        check("3 templates listed", len(templates) == 3, str(len(templates)))
        check("template image URLs real Printify",
              all(u.startswith("https://images.printify.com/")
                  for t in templates for u in t["images"]))
        r = client.post(f"/api/sets/{sid}/catalog-templates", json={"all": True})
        j = r.get_json()
        check("all 3 added", len(j["added"]) == 3, str(j["added"]))
        check("templates marked catalog",
              all(p.get("kind") == "catalog" and p.get("template") is True
                  for p in j["set"]["products"]))
        r = client.post(f"/api/sets/{sid}/catalog-templates", json={"all": True})
        check("re-add dedupes", r.get_json()["added"] == [])

        print("== 4. Variant math + 100 guard ==")
        r = client.get(f"/api/sets/{sid}/variant-count")
        j = r.get_json()
        # Full selections: 18x8=144, 5x5=25, 11x5=55 -> 224 combine.
        check("combine total 224", j["total_combine"] == 224, str(j))
        check("split grouping reported", j["grouping"] == "split", str(j))
        # Split mode with full selections: 144-product still over.
        check("split guard fails on 144-product",
              j["guard_ok"] is False, str(j))
        # Trim template 80 to 12 colours -> 96, split guard passes.
        pid80 = "catalog:printify-80"
        r = client.post(f"/api/sets/{sid}/products/{pid80}/variants",
                        json={"colours": ["Black", "Navy", "Red", "Royal",
                                          "White", "Ash", "Gold", "Maroon",
                                          "Purple", "Forest Green",
                                          "Dark Heather", "Sport Grey"]})
        check("variants saved", r.status_code == 200, str(r.status_code))
        r = client.get(f"/api/sets/{sid}/variant-count")
        j = r.get_json()
        check("split guard passes after trim",
              j["guard_ok"] is True and j["total_combine"] == 96 + 25 + 55,
              str(j))

        print("== 5. Pricing + profit guard ==")
        calls = []
        orig_create = shopify_api.create_draft_product
        shopify_api.create_draft_product = lambda **kw: calls.append(kw) or {"id": 1, "status": "draft", "handle": "test-set-2"}
        try:
            for pid in ("catalog:printify-80", "catalog:printify-945",
                        "catalog:printify-48"):
                client.post(f"/api/sets/{sid}/products/{pid}/pricing",
                            json={"sale_price": 10, "base_cost": 12})
            # No design yet -> design guard fires first; upload one.
            tpng = os.path.join(tmp, "design.png")
            make_png(tpng, transparent=True)
            with open(tpng, "rb") as fh:
                r = client.post(f"/api/sets/{sid}/upload",
                                data={"design": (fh, "design.png")},
                                content_type="multipart/form-data")
            check("transparent upload passes", r.status_code == 200,
                  str(r.status_code) + str(r.get_json()))
            check("upload validation info",
                  r.get_json()["validation"]["transparent"] is True)
            r = client.post(f"/api/sets/{sid}/publish-draft",
                            json={"dry_run": True})
            # Gearlaunch flow (2026-11-03): profit removed, Shopify
            # owns profit, so a price below base cost no longer blocks.
            check("price below base cost does NOT block dry-run",
                  r.status_code == 200
                  and len(r.get_json().get("products", [])) == 3,
                  str(r.status_code))
            check("shopify client not called on dry-run",
                  calls == [])
            for pid in ("catalog:printify-80", "catalog:printify-945",
                        "catalog:printify-48"):
                client.post(f"/api/sets/{sid}/products/{pid}/pricing",
                            json={"sale_price": 27.99, "base_cost": 12.50})
            r = client.post(f"/api/sets/{sid}/publish-draft",
                            json={"dry_run": True})
            j = r.get_json()
            check("dry-run ok in split mode",
                  r.status_code == 200 and j["dry_run"] is True
                  and len(j["products"]) == 3, str(r.status_code))
            check("dry-run still never calls shopify", calls == [])
            # Combine dry-run: small selections -> 1 payload.
            client.post(f"/api/sets/{sid}/details", json={"grouping": "combine"})
            for pid in ("catalog:printify-80", "catalog:printify-945",
                        "catalog:printify-48"):
                client.post(f"/api/sets/{sid}/products/{pid}/variants",
                            json={"colours": ["Black", "White"],
                                  "sizes": ["S", "M"]})
            r = client.post(f"/api/sets/{sid}/publish-draft",
                            json={"dry_run": True})
            j = r.get_json()
            check("combine dry-run 1 payload, 12 variants",
                  len(j["products"]) == 1
                  and len(j["products"][0]["variants"]) == 12, str(j))

            print("== 6. Mock publish + artwork lock ==")
            orig_auth = shopify_api.authenticated
            shopify_api.authenticated = lambda: True
            try:
                r = client.post(f"/api/sets/{sid}/publish-draft", json={})
                j = r.get_json()
                check("mock publish ok",
                      r.status_code == 200 and j.get("published") is True,
                      str(r.status_code) + str(j))
                check("mock client called once", len(calls) == 1, str(len(calls)))
                check("mock payload is draft status",
                      calls[0].get("title") == "Test Set 2")
                r = client.post(f"/api/sets/{sid}/publish-draft", json={})
                check("second real publish blocked 409",
                      r.status_code == 409, str(r.status_code))
                with open(tpng, "rb") as fh:
                    r = client.post(f"/api/sets/{sid}/upload",
                                    data={"design": (fh, "design.png")},
                                    content_type="multipart/form-data")
                check("upload blocked after publish lock",
                      r.status_code == 409, str(r.status_code))
            finally:
                shopify_api.authenticated = orig_auth

            print("== 7. Publish failure path ==")
            r = client.post("/api/sets", json={"name": "Fail Set"})
            sid2 = r.get_json()["id"]
            client.post(f"/api/sets/{sid2}/catalog-templates",
                        json={"product_ids": ["catalog:printify-945"]})
            client.post(f"/api/sets/{sid2}/products/catalog:printify-945/pricing",
                        json={"sale_price": 30, "base_cost": 12})
            with open(tpng, "rb") as fh:
                client.post(f"/api/sets/{sid2}/upload",
                            data={"design": (fh, "design.png")},
                            content_type="multipart/form-data")

            def boom(**kw):
                raise RuntimeError("Shopify draft create failed (HTTP 500)")
            shopify_api.create_draft_product = boom
            shopify_api.authenticated = lambda: True
            try:
                r = client.post(f"/api/sets/{sid2}/publish-draft", json={})
                check("publish failure -> 502", r.status_code == 502,
                      str(r.status_code))
                r = client.get("/api/sets")
                failset = [s for s in r.get_json() if s["id"] == sid2][0]
                check("failed state recorded",
                      failset["publish_state"] == "failed"
                      and failset["publish_error"] is not None)
            finally:
                shopify_api.authenticated = orig_auth
        finally:
            shopify_api.create_draft_product = orig_create

        print("== 8. Upload validation rejections ==")
        r = client.post("/api/sets", json={"name": "Empty Set"})
        sid_empty = r.get_json()["id"]
        with open(tpng, "rb") as fh:
            client.post(f"/api/sets/{sid_empty}/upload",
                        data={"design": (fh, "design.png")},
                        content_type="multipart/form-data")
        r = client.post(f"/api/sets/{sid_empty}/publish-draft",
                        json={"dry_run": True})
        check("empty set publish blocked",
              r.status_code == 400, str(r.status_code))
        r = client.post("/api/sets", json={"name": "Upload Set"})
        sid3 = r.get_json()["id"]
        opaque = os.path.join(tmp, "opaque.png")
        make_png(opaque, transparent=False)
        with open(opaque, "rb") as fh:
            r = client.post(f"/api/sets/{sid3}/upload",
                            data={"design": (fh, "opaque.png")},
                            content_type="multipart/form-data")
        check("opaque PNG rejected", r.status_code == 400, str(r.status_code))
        jpg = os.path.join(tmp, "photo.jpg")
        make_png(jpg, transparent=False, fmt="JPEG")
        with open(jpg, "rb") as fh:
            r = client.post(f"/api/sets/{sid3}/upload",
                            data={"design": (fh, "photo.jpg")},
                            content_type="multipart/form-data")
        check("JPEG rejected", r.status_code == 400, str(r.status_code))
        r = client.post(f"/api/sets/{sid3}/upload",
                        data={}, content_type="multipart/form-data")
        check("no file rejected", r.status_code == 400)

        print("== 9. Hero picker ==")
        r = client.post(f"/api/sets/{sid3}/catalog-templates",
                        json={"product_ids": ["catalog:printify-48"]})
        pid48 = "catalog:printify-48"
        imgs = r.get_json()["set"]["products"][0]["images"]
        r = client.post(f"/api/sets/{sid3}/products/{pid48}/hero",
                        json={"image": imgs[1]})
        check("hero changed",
              r.get_json()["products"][0]["hero_image"] == imgs[1])
        r = client.post(f"/api/sets/{sid3}/products/{pid48}/hero",
                        json={"image": "https://example.com/nope.jpg"})
        check("unknown hero rejected", r.status_code == 400)

        print("== 10. Mockup render + regressions ==")
        photo = os.path.join(tmp, "photo.png")
        make_png(photo, size=(400, 400), transparent=False)
        # Fix round 3: renders only accept server-issued /static/ URLs,
        # so stage the files under UPLOAD_DIR first.
        shutil.copy(tpng, os.path.join(app_module.UPLOAD_DIR, "design.png"))
        shutil.copy(photo, os.path.join(app_module.UPLOAD_DIR, "photo.png"))
        r = client.post(f"/api/sets/{sid3}/mockups",
                        json={"design": "/static/uploads/design.png",
                              "photos": {pid48: "/static/uploads/photo.png"}})
        j = r.get_json()
        check("mockup rendered", r.status_code == 200
              and pid48 in j.get("mockups", {}), str(j))
        mock_path = os.path.join(
            app_module.MOCKUP_DIR, os.path.basename(j["mockups"][pid48]))
        check("mockup file exists", os.path.exists(mock_path))
        r = client.get("/api/products/search?q=oregon")
        check("picker search unauthenticated -> 503",
              r.status_code == 503, str(r.status_code))
        # Lock/unlock + master regression on a store-style product.
        # Fix round 3: adding a store product enriches it from Shopify,
        # so mock the details lookup (and auth) for this regression.
        shopify_api.authenticated = lambda: True
        shopify_api.get_product_details = lambda pid: {
            "product_id": pid, "title": "Oregon Ducks Unisex Tee",
            "handle": "oregon-ducks-unisex-tee", "image": None,
            "images": [], "colours": ["Black", "White"],
            "sizes": ["S", "M"], "variant_prices": {}, "variants": 4}
        r = client.post(f"/api/sets/{sid3}/products",
                        json={"product_id": "15469998538906"})
        _added = [p for p in r.get_json()["products"]
                  if p["product_id"] == "15469998538906"][0]
        check("add by id ok, enriched",
              r.status_code == 200
              and _added["title"] == "Oregon Ducks Unisex Tee"
              and _added["colours"] == ["Black", "White"], str(r.status_code))
        r = client.post(f"/api/sets/{sid3}/products/15469998538906/lock",
                        json={"locked": False,
                              "placement": {"x": 0.4, "y": 0.4,
                                            "scale": 0.3, "angle": 10}})
        check("unlock with override ok",
              r.get_json()["products"][-1]["locked"] is False)
        r = client.post(f"/api/sets/{sid3}/master",
                        json={"placement": {"x": 0.5, "y": 0.5,
                                            "scale": 0.5, "angle": 0}})
        check("master save ok", r.status_code == 200)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    real_hash_after = sha(REAL_SETS)
    check("real sets.json byte-identical",
          real_hash_before == real_hash_after,
          f"{real_hash_before} vs {real_hash_after}")

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("FAILED:", FAILED)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
