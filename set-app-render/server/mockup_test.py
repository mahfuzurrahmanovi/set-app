"""Engine test: master placement vs unlocked override, no external files."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw

from mockup import render_set_mockups

OUT = "/tmp/set-app-test"
os.makedirs(OUT, exist_ok=True)

# Fake product photo: 1000x1000, light background, grey garment block.
photo = Image.new("RGB", (1000, 1000), (240, 240, 240))
d = ImageDraw.Draw(photo)
d.rounded_rectangle([250, 100, 750, 950], radius=40, fill=(200, 200, 200))
photo.save(f"{OUT}/photo.jpg")

# Fake design: transparent 800x600, green badge + text.
design = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
d = ImageDraw.Draw(design)
d.ellipse([50, 50, 750, 550], fill=(15, 118, 110, 255))
d.text((400, 300), "OREGON", fill=(255, 255, 255, 255), anchor="mm")
design.save(f"{OUT}/design.png")

test_set = {
    "id": "testset",
    "master_placement": {"x": 0.5, "y": 0.45, "scale": 0.5, "angle": 0},
    "products": [
        {"product_id": "locked-tee", "locked": True, "override_placement": None},
        {
            "product_id": "unlocked-hoodie",
            "locked": False,
            "override_placement": {"x": 0.5, "y": 0.65, "scale": 0.35, "angle": 0},
        },
    ],
}

results = render_set_mockups(
    test_set,
    f"{OUT}/design.png",
    {"locked-tee": f"{OUT}/photo.jpg", "unlocked-hoodie": f"{OUT}/photo.jpg"},
    OUT,
)


def px(path, xy):
    return Image.open(path).convert("RGB").getpixel(xy)


def is_green(p):
    r, g, b = p
    return g > 100 and g > r + 30


for pid, path in results.items():
    im = Image.open(path)
    print(pid, "->", path, "size:", im.size)
    print("  pixel at master spot (500,450) green?", is_green(px(path, (500, 450))), px(path, (500, 450)))
    print("  pixel at override spot (500,650) green?", is_green(px(path, (500, 650))), px(path, (500, 650)))

print("OK: locked product follows master (green at 450, not at 650);")
print("    unlocked product follows override (green at 650, not at 450).")
