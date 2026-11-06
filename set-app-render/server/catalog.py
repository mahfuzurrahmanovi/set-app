"""Catalog templates: the 3 missing Printify product types as designable
products in the app, so the seller can upload designs on them here.

Data verified live via the Printify CLI (blueprints and variants
endpoints, provider 99 = Printify Choice): titles, brands and image
URLs below are real catalog data, not invented. Print areas are the
front DTG placeholders from the provider-99 variants endpoint.

Colours and sizes are the subsets Ovi chose on 2026-11-06: the colours
already in use on his Oregon line in Shopify, and all sizes for the
Long Sleeve (S-5XL, his call). Prices are the USD prices Ovi gave
(Long Sleeve Tee $27, Classic $29, V-neck $29, confirmed 2026-11-06);
the store's currency app converts for viewers. The seller can still
change prices per product. Templates are clearly marked:
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
            "Ash", "Black", "Dark Heather", "Gold", "Irish Green",
            "Navy", "Purple", "Red", "Royal", "Sport Grey", "White",
        ],
        "sizes": ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
        "print_area": {"position": "front", "width": 3033, "height": 3442},
        # "T-shirt 27 USD" (Ovi, 2026-11-04), confirmed as this plain
        # Long Sleeve Tee and as USD on 2026-11-06. Colours are the 11
        # of his Oregon line the Gildan 2400 offers (not Cardinal Red,
        # Kelly Green or Orange). 76 real variants with these colours.
        "suggested_price": "27.00",
        "price_confirmed": True,
        "images": [
            "https://images.printify.com/66c436f540af02f3cd0aa5b4",
            "https://images.printify.com/66c436fc1496997ddf06eca3",
            "https://images.printify.com/5d073877d155b4001019f828",
        ],
    },
    {
        "product_id": "catalog:printify-2806",
        "kind": "catalog",
        "template": True,
        "blueprint_id": 2806,
        "provider_id": 99,
        "brand": "Gildan",
        "title": "Long Sleeve T-Shirt",
        "colours": ["Black", "Navy", "Royal", "Sport Grey", "White"],
        "sizes": ["S", "M", "L", "XL", "2XL", "3XL"],
        "print_area": {"position": "front", "width": 4500, "height": 5100},
        # Classic Long Sleeve is the Gildan Softstyle 64400 (Ovi,
        # 2026-11-06: "Gildan for both long sleeves"). 4.5oz 100%
        # ring-spun cotton, the soft one closest in feel to the
        # American Apparel 945 it replaces. Price $29 USD, confirmed
        # 2026-11-06. Colours are the 5 of his Oregon line it offers.
        # 30 real variants with these colours.
        "suggested_price": "29.00",
        "price_confirmed": True,
        "images": [
            "https://images.printify.com/6abd0492d97855c8c90cee12",
            "https://images.printify.com/6abd048c09b16bbcf9095b93",
            "https://images.printify.com/6abd04865da73d94240bb680",
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
        "colours": ["Black", "Navy", "Red", "White"],
        "sizes": ["S", "M", "L", "XL", "2XL"],
        "print_area": {"position": "front", "width": 3461, "height": 3922},
        # "V-neck tee is 29 USD" (Ovi, 2026-11-04), confirmed USD
        # 2026-11-06. Colours are the 4 of his Oregon line the
        # Bella+Canvas V-neck offers. 20 real variants with these
        # colours.
        "suggested_price": "29.00",
        "price_confirmed": True,
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
    The first catalog image is the hero image. The selling price starts
    at the template's suggested price so a design-first set is
    publishable without typing a price (still editable per product).
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
        "sale_price": template.get("suggested_price"),
        "compare_at_price": None,
        "base_cost": None,
    }
    return entry


def get_template(product_id):
    for t in TEMPLATES:
        if t["product_id"] == product_id:
            return t
    return None


def match_template_for_title(title):
    """Match a store product title to a Printify flat-photo template.

    Only the 3 verified templates exist, so only these map:
    - "v-neck" / "v neck" -> Bella+Canvas V-Neck (blueprint 48)
    - "classic" + "long sleeve" -> Gildan Softstyle Long Sleeve
      (blueprint 2806); classic must be checked first, or a
      classic title would wrongly fall through to Gildan 80
    - "long sleeve" (other) -> Gildan Ultra Cotton Long Sleeve
      (blueprint 80)
    Everything else (short sleeve, hoodie, crewneck, mug, hat, kids,
    etc.) returns None: no template exists, so no Printify URL is
    invented for it and the bare store photo must be used instead.
    """
    if not title:
        return None
    t = str(title).lower()
    if "classic" in t and "long sleeve" in t:
        return get_template("catalog:printify-2806")
    if "v-neck" in t or "v neck" in t:
        return get_template("catalog:printify-48")
    if "long sleeve" in t:
        return get_template("catalog:printify-80")
    return None
