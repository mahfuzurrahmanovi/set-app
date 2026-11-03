"""Catalog templates: the 3 missing Printify product types as designable
products in the app, so the seller can upload designs on them here.

Data verified live 2026-11-03 via the Printify CLI (blueprints
endpoint): titles, brands and image URLs below are real catalog data,
not invented. Colours, sizes and print areas are from
missing-products-spec.md (2026-11-02 audit).

Printify variants output carries no production cost, so base_cost
starts empty and the seller types it. Templates are clearly marked:
kind="catalog" and template=True, and the UI must label them
"Catalog template, not a store product yet". They are never sent to
Shopify as-is; they become real products only through the draft
publish flow, after a design is uploaded.
"""

TEMPLATES = [
    {
        "product_id": "catalog:printify-80",
        "kind": "catalog",
        "template": True,
        "blueprint_id": 80,
        "provider_id": 99,
        "brand": "Gildan",
        "title": "Unisex Ultra Cotton Long Sleeve Tee",
        "colours": [
            "Ash", "Black", "Carolina Blue", "Dark Chocolate",
            "Dark Heather", "Forest Green", "Gold", "Irish Green",
            "Light Blue", "Light Pink", "Maroon", "Navy", "Purple",
            "Red", "Royal", "Safety Green", "Sport Grey", "White",
        ],
        "sizes": ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
        "print_area": {"position": "front", "width": 3033, "height": 3442},
        "images": [
            "https://images.printify.com/66c436f540af02f3cd0aa5b4",
            "https://images.printify.com/66c436fc1496997ddf06eca3",
            "https://images.printify.com/5d073877d155b4001019f828",
        ],
    },
    {
        "product_id": "catalog:printify-945",
        "kind": "catalog",
        "template": True,
        "blueprint_id": 945,
        "provider_id": 99,
        "brand": "American Apparel",
        "title": "Unisex Classic Long Sleeve T-Shirt",
        "colours": ["Athletic Heather", "Black", "Navy", "Sand", "White"],
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "print_area": {"position": "front", "width": 2835, "height": 3239},
        "images": [
            "https://images.printify.com/67644043c5d8aa445a07eda2",
            "https://images.printify.com/6764403f4c5ff7ec4406fe57",
            "https://images.printify.com/6764403cf1b843b73b029f9e",
            "https://images.printify.com/62a30b88fdab4feee906445a",
            "https://images.printify.com/62a30b87fdab4feee9064457",
            "https://images.printify.com/629df914c9c6a38b9708ca5b",
        ],
    },
    {
        "product_id": "catalog:printify-48",
        "kind": "catalog",
        "template": True,
        "blueprint_id": 48,
        "provider_id": 99,
        "brand": "Bella+Canvas",
        "title": "Unisex Jersey Short Sleeve V-Neck Tee",
        "colours": [
            "Asphalt", "Athletic Heather", "Black", "Dark Grey Heather",
            "Deep Heather", "Heather True Royal", "Navy", "Red",
            "Team Purple", "True Royal", "White",
        ],
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "print_area": {"position": "front", "width": 3461, "height": 3922},
        "images": [
            "https://images.printify.com/68de6ccea86faddead05c862",
            "https://images.printify.com/68de9252b497c11fbf0a9d99",
            "https://images.printify.com/68dfa84972bfaa8bf6086bb2",
            "https://images.printify.com/68daf7617a307ad8350c73e2",
            "https://images.printify.com/68de6bd1147c38727a024a52",
            "https://images.printify.com/68de6bd4536a5099c102fcc2",
        ],
    },
]


def template_entry(template):
    """A set-product entry built from a catalog template.

    All colours and sizes start selected (ShopBase-style default-all).
    The first catalog image is the hero image.
    """
    entry = {
        "product_id": template["product_id"],
        "kind": "catalog",
        "template": True,
        "blueprint_id": template["blueprint_id"],
        "provider_id": template["provider_id"],
        "brand": template["brand"],
        "title": template["title"],
        "colours": list(template["colours"]),
        "sizes": list(template["sizes"]),
        "all_colours": list(template["colours"]),
        "all_sizes": list(template["sizes"]),
        "print_area": dict(template["print_area"]),
        "images": list(template["images"]),
        "hero_image": template["images"][0] if template["images"] else None,
        "position": "front",
        "mockups": [],
        "locked": True,
        "override_placement": None,
        "sale_price": None,
        "compare_at_price": None,
        "base_cost": None,
    }
    return entry


def get_template(product_id):
    for t in TEMPLATES:
        if t["product_id"] == product_id:
            return t
    return None
