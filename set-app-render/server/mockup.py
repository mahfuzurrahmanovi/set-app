"""Mockup engine: draw a design onto a product photo at a placement.

Placement semantics (shared with the UI and the set data model):
  x, y  = centre of the design as a fraction of the photo (0-1).
  scale = design width as a fraction of the photo width.
  angle = rotation in degrees, 0 = upright.

A set has one master_placement. A product follows the master unless it is
unlocked, in which case its override_placement wins. Re-locking returns it
to the master. This is the "fix the first, fix the rest" rule, with a
per-product escape hatch.
"""

from PIL import Image


def composite(design_path, photo_path, placement, output_path):
    photo = Image.open(photo_path).convert("RGBA")
    design = Image.open(design_path).convert("RGBA")
    W, H = photo.size
    x = float(placement["x"])
    y = float(placement["y"])
    scale = float(placement.get("scale", 0.5))
    angle = float(placement.get("angle", 0))

    target_w = max(1, int(W * scale))
    ratio = design.height / design.width if design.width else 1
    design = design.resize((target_w, max(1, int(target_w * ratio))), Image.LANCZOS)
    if angle:
        design = design.rotate(-angle, resample=Image.BICUBIC, expand=True)

    pos = (int(W * x - design.width / 2), int(H * y - design.height / 2))
    photo.alpha_composite(design, pos)
    photo.convert("RGB").save(output_path, "JPEG", quality=92)
    return output_path


def effective_placement(set_obj, product_id):
    """Placement a product actually renders with: override if unlocked."""
    for p in set_obj.get("products", []):
        if p.get("product_id") == product_id:
            if not p.get("locked", True) and p.get("override_placement"):
                return p["override_placement"]
            return set_obj["master_placement"]
    return set_obj["master_placement"]


def render_set_mockups(set_obj, design_path, photo_by_product, out_dir):
    """Render one mockup per product in the set. Returns {product_id: path}."""
    import os

    os.makedirs(out_dir, exist_ok=True)
    results = {}
    for p in set_obj.get("products", []):
        pid = p["product_id"]
        photo = photo_by_product.get(pid)
        if not photo:
            continue
        out = os.path.join(out_dir, f"{set_obj['id']}_{pid}.jpg")
        composite(design_path, photo, effective_placement(set_obj, pid), out)
        results[pid] = out
    return results
