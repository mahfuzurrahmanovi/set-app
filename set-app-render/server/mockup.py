"""Mockup engine: draw a design onto a product photo at a placement.

Placement semantics (shared with the UI and the set data model):
  x, y  = centre of the design as a fraction of the photo (0-1),
  clamped on render/save to the fixed print area (x 0.25-0.75,
  y 0.20-0.70).
  scale = design width as a fraction of the photo width, capped
  at 0.5 (the print-area box width).
  angle = rotation in degrees, 0 = upright.

A set has one master_placement. A product follows the master unless it is
unlocked, in which case its override_placement wins. Re-locking returns it
to the master. This is the "fix the first, fix the rest" rule, with a
per-product escape hatch.

One exception: a product whose type defines its own placement (the
V-neck, whose type placement sits lower so a square badge clears the
V opening the master would overlap) follows that type placement
while locked, not the master. An unlocked product's own override
always wins over the type placement too.
"""

from PIL import Image

MAX_PHOTO_WIDTH = 3000


def _capped_photo(photo_path):
    """Open a photo, downscaling to MAX_PHOTO_WIDTH if it is wider.

    Huge CDN photos (8000px+) would otherwise blow the render memory
    budget; mockups do not need full resolution.
    """
    photo = Image.open(photo_path).convert("RGBA")
    if photo.width > MAX_PHOTO_WIDTH:
        ratio = MAX_PHOTO_WIDTH / photo.width
        photo = photo.resize(
            (MAX_PHOTO_WIDTH, max(1, int(photo.height * ratio))),
            Image.LANCZOS)
    return photo


def composite(design_path, photo_path, placement, output_path):
    photo = _capped_photo(photo_path)
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


def clamp_to_print_area(placement):
    """Clamp a placement to the fixed print area (see app.js
    PRINT_AREA): centre x in [0.25, 0.75], y in [0.20, 0.70],
    width scale capped at 0.5 (the box width). Legacy out-of-box
    placements render clamped, so preview and published mockups
    agree instead of diverging."""
    if not placement:
        return placement
    out = dict(placement)
    try:
        out["x"] = min(0.75, max(0.25, float(out.get("x", 0.5))))
        out["y"] = min(0.70, max(0.20, float(out.get("y", 0.45))))
        out["scale"] = min(0.5, max(0.1, float(out.get("scale", 0.5))))
    except (TypeError, ValueError):
        pass
    return out


def effective_placement(set_obj, product_id):
    """Placement a product actually renders with: override if unlocked,
    the product type's own placement if it defines one (V-neck only),
    else the master. Always clamped to the fixed print area."""
    for p in set_obj.get("products", []):
        if p.get("product_id") == product_id:
            if not p.get("locked", True) and p.get("override_placement"):
                return clamp_to_print_area(p["override_placement"])
            tp = type_placement_for(p)
            if tp is not None:
                return clamp_to_print_area(tp)
            return clamp_to_print_area(set_obj["master_placement"])
    return clamp_to_print_area(set_obj["master_placement"])


def type_placement_for(product):
    """A product's type placement (V-neck only), or None.

    Resolves the product's type (stored type first, else title
    keywords) and returns a copy of that type's placement, if it
    defines one. Never raises; a missing or broken type table means
    the caller falls back to the master.
    """
    try:
        import product_types as ptypes
    except ImportError:
        return None
    try:
        return ptypes.type_placement(ptypes.resolve_type_key(product or {}))
    except Exception:
        return None


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
