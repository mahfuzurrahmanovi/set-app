"""Text layers for the set-app editor (ShopBase-style, basic only).

A text layer is a small record on the set:
  {id, content, font, size, colour, lettercase, rotation, opacity,
   hidden}
Fonts map to fonts installed on this machine (DejaVu / Liberation).
Layers render to transparent PNGs, then composite onto mockups at the
set's placement centre. This is a design tool only: it never creates
buyer-facing personalization options, and it never touches orders.

Colour is a #rrggbb hex string. Opacity is 0-100 percent. Rotation is
degrees (-180..180). Lettercase: none / upper / lower.
"""

import os
import re
import uuid

from PIL import Image, ImageDraw, ImageFont

FONTS = {
    "sans": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "serif": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_layer(body):
    """Validate a text-layer body. Returns (layer, error)."""
    content = (body.get("content") or "").strip()
    if not content:
        return None, "Type some text for the layer first."
    font = body.get("font") or "sans"
    if font not in FONTS:
        return None, "Font must be Sans, Serif or Mono."
    try:
        size = int(body.get("size", 120))
    except (TypeError, ValueError):
        return None, "Size must be a whole number of pixels."
    if size < 10 or size > 500:
        return None, "Size must be between 10 and 500 pixels."
    colour = body.get("colour") or "#000000"
    if not HEX_RE.match(colour):
        return None, "Colour must be a hex value like #1a1a1a."
    lettercase = body.get("lettercase") or "none"
    if lettercase not in ("none", "upper", "lower"):
        return None, "Lettercase must be none, upper or lower."
    try:
        rotation = float(body.get("rotation", 0))
    except (TypeError, ValueError):
        return None, "Rotation must be a number of degrees."
    if rotation < -180 or rotation > 180:
        return None, "Rotation must be between -180 and 180 degrees."
    try:
        opacity = int(body.get("opacity", 100))
    except (TypeError, ValueError):
        return None, "Opacity must be a whole percent."
    if opacity < 0 or opacity > 100:
        return None, "Opacity must be between 0 and 100 percent."
    if lettercase == "upper":
        content = content.upper()
    elif lettercase == "lower":
        content = content.lower()
    return {
        "id": uuid.uuid4().hex[:8],
        "content": content,
        "font": font,
        "size": size,
        "colour": colour.lower(),
        "lettercase": lettercase,
        "rotation": rotation,
        "opacity": opacity,
        "hidden": False,
    }, None


def render_text_png(layer, out_path):
    """Render one text layer to a transparent PNG. Returns the path."""
    font = ImageFont.truetype(FONTS[layer["font"]], layer["size"])
    probe = Image.new("RGBA", (10, 10))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), layer["content"], font=font)
    w = bbox[2] - bbox[0] + 20
    h = bbox[3] - bbox[1] + 20
    img = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rgb = tuple(int(layer["colour"][i:i + 2], 16) for i in (1, 3, 5))
    draw.text((10 - bbox[0], 10 - bbox[1]), layer["content"],
              font=font, fill=rgb + (255,))
    if layer["opacity"] < 100:
        alpha = img.split()[3].point(
            lambda v: int(v * layer["opacity"] / 100))
        img.putalpha(alpha)
    if layer["rotation"]:
        img = img.rotate(-layer["rotation"], resample=Image.BICUBIC,
                         expand=True)
    img.save(out_path, "PNG")
    return out_path


def composite_layers(photo_path, design_path, placement, layer_pngs,
                     output_path):
    """Composite design + visible text layers onto a photo.

    design_path may be None (product hides the design: photo only).
    layer_pngs: list of transparent PNG paths, each centred on the
    placement centre. Output is a JPEG mockup.
    """
    from mockup import composite  # local import: same server dir

    if design_path is None:
        # Product hides the design: start from the bare photo.
        Image.open(photo_path).convert("RGB").save(
            output_path, "JPEG", quality=92)
    else:
        composite(design_path, photo_path, placement, output_path)
    if not layer_pngs:
        return output_path
    img = Image.open(output_path).convert("RGBA")
    W, H = img.size
    cx = float(placement["x"]) * W
    cy = float(placement["y"]) * H
    for path in layer_pngs:
        layer = Image.open(path).convert("RGBA")
        img.alpha_composite(
            layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))
    img.convert("RGB").save(output_path, "JPEG", quality=92)
    return output_path
