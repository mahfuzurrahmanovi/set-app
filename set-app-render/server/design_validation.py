"""Design upload validation, with plain-language errors.

Standing rule (Ovi): designs must be true transparent files, no
background and no product mockup baked in. So this module REJECTS
anything that is not a transparent PNG:
  - JPEG, WebP, GIF, PSD and anything else: rejected (JPEG has no
    transparency at all; PSD is not a finished print file here).
  - PNG with no alpha channel, or with solid corners all round:
    rejected as "not transparent".
Size and quality checks are plain warnings, not rejections, except
for an absolute size cap and a minimum pixel size.

DPI is an ESTIMATE: print width is assumed to be 12 inches (a
standard chest print). It is labelled an estimate everywhere it is
shown, never presented as a measured value.
"""

from PIL import Image

MAX_BYTES = 25 * 1024 * 1024  # 25 MB cap for phone uploads
MIN_SIDE_PX = 200
PRINT_WIDTH_INCHES = 12.0
DPI_WARN_BELOW = 150

ALLOWED_FORMAT = "PNG"


def _corner_opaque(alpha, w, h):
    """True when all four corner patches are essentially opaque."""
    patch_w = max(1, w // 20)
    patch_h = max(1, h // 20)
    corners = [
        (0, 0),
        (w - patch_w, 0),
        (0, h - patch_h),
        (w - patch_w, h - patch_h),
    ]
    for x0, y0 in corners:
        total = 0
        count = 0
        for yy in range(y0, y0 + patch_h):
            for xx in range(x0, x0 + patch_w):
                total += alpha.getpixel((xx, yy))
                count += 1
        if count and (total / count) < 250:
            return False
    return True


def validate_design(stream, filename="", max_bytes=MAX_BYTES):
    """Validate an uploaded design file object.

    stream: a file-like object positioned at the start (Flask
    FileStorage works). Returns a dict:
      {"ok": True, "width": w, "height": h, "dpi_estimate": d,
       "transparent": True, "warnings": [...]}
    or {"ok": False, "error": "<plain message>"}.
    A failed validation means the file must NOT be saved.
    """
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size > max_bytes:
        return {
            "ok": False,
            "error": (
                f"This file is {size / 1024 / 1024:.1f} MB, over the "
                f"{max_bytes / 1024 / 1024:.0f} MB limit. Please upload a "
                "smaller file."
            ),
        }
    try:
        img = Image.open(stream)
        img.load()
    except Exception:
        return {
            "ok": False,
            "error": "That file could not be read as an image. Please upload a PNG file.",
        }
    fmt = (img.format or "").upper()
    if fmt != ALLOWED_FORMAT:
        return {
            "ok": False,
            "error": (
                f"This is a {fmt or 'unknown'} file. Please upload a PNG "
                "with a transparent background. JPEG files cannot be "
                "transparent, so they are not accepted."
            ),
        }
    w, h = img.size
    if w < MIN_SIDE_PX or h < MIN_SIDE_PX:
        return {
            "ok": False,
            "error": (
                f"This image is only {w} x {h} pixels, too small to print "
                "clearly. Please upload a larger design."
            ),
        }
    if img.mode not in ("RGBA", "LA", "PA"):
        # Modes without an alpha channel cannot be transparent.
        # ("P" without a transparency chunk also lands here.)
        if img.mode == "P" and "transparency" in img.info:
            pass
        else:
            return {
                "ok": False,
                "error": (
                    "This PNG has no transparent background. Please upload "
                    "a design saved with transparency (no white or coloured "
                    "background behind the artwork)."
                ),
            }
    alpha = img.convert("RGBA").split()[3]
    extrema = alpha.getextrema()
    if extrema[0] > 250:
        return {
            "ok": False,
            "error": (
                "This PNG has no transparent background. Every pixel is "
                "solid. Please upload a design saved with transparency."
            ),
        }
    if _corner_opaque(alpha, w, h):
        return {
            "ok": False,
            "error": (
                "This design looks like it has a solid background: all "
                "four corners are solid. Please upload a design with a "
                "truly transparent background."
            ),
        }
    # Transparent fraction: a solid photo with transparent corners
    # (rounded corners) passes the corner check, so also require a
    # real share of transparent pixels.
    hist = alpha.histogram()
    transparent_px = sum(hist[:250])
    total_px = w * h
    if total_px and transparent_px / total_px < 0.03:
        return {
            "ok": False,
            "error": (
                "This PNG has almost no transparent area, so it looks "
                "like a solid photo rather than a design. Please upload "
                "a design saved with a truly transparent background."
            ),
        }
    dpi = round(w / PRINT_WIDTH_INCHES)
    warnings = []
    if dpi < DPI_WARN_BELOW:
        warnings.append(
            f"Estimated print quality is about {dpi} DPI at a 12 inch "
            "print width, under the usual 150 DPI. A larger file will "
            "print sharper."
        )
    return {
        "ok": True,
        "width": w,
        "height": h,
        "dpi_estimate": dpi,
        "transparent": True,
        "warnings": warnings,
    }
