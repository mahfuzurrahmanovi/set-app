"""Local product-type definitions for the set app (2026-11-07).

Every garment type the designer knows is defined HERE, inside the app:
its name, how to recognise it from a title (legacy fallback only), its
design-area template PNG, and, for the three new types, the starting
sizes, colours and working price. There is no supplier connection of
any kind: nothing in this module reads from, or calls, an outside
catalogue or API.

Which source wins (decided for this round, documented in SPEC.md):
  * A product LINKED to a Shopify listing: the synced listing wins for
    title, colours, sizes and per-variant prices. The type definition
    only supplies the template PNG (and the type label).
  * A LOCAL (not yet linked) product: the type definition is the
    starting point (working title, colours, sizes, working price) so
    Srity can design before the listing exists. Once the real listing
    is linked, the listing replaces those starting values.

Template resolution order for a product:
  1. its stored ``product_type`` (rename-proof),
  2. else the legacy title keywords (kept for products added before
     types existed, e.g. the Oregon tee / hoodie / crewneck),
  3. else the short-sleeve tee outline.

V-neck sizes are DECIDED (2026-11-08, the only sizes ever specified
for the V-neck in the expansion spec): S-2XL. The V-neck starts with
those five sizes selected. The list is still configurable through
the SETAPP_VNECK_SIZES environment variable (comma separated, e.g.
"S,M,L,XL,2XL") or by ticking sizes on the product card.

V-neck placement: the master placement would put a square badge over
the V opening, so the V-neck type has its own placement (see
VNECK_PLACEMENT below). The master is untouched and the other types
still follow it.
"""

import os
from collections import OrderedDict

TEMPLATE_URL_PREFIX = "/static/design-area-templates/"

# Every size the app ever lists, in order (used to validate the
# V-neck size setting; not a promise that every type has every size).
SIZE_LADDER = ["S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"]

# The Oregon line's 14-colour union. New types use subsets of it and
# never add a colour outside it.
COLOUR_UNION = [
    "Ash", "Black", "Cardinal Red", "Dark Heather", "Gold",
    "Irish Green", "Kelly Green", "Navy", "Orange", "Purple", "Red",
    "Royal", "Sport Grey", "White",
]

# The V-neck's tick-able size pool (S-3XL): the default S-2XL plus
# 3XL, so Srity can add 3XL on the card if she needs it.
VNECK_SIZE_POOL = ["S", "M", "L", "XL", "2XL", "3XL"]
VNECK_SIZES_ENV = "SETAPP_VNECK_SIZES"

# V-neck sizes, decided 2026-11-08 (the only sizes ever specified
# for the V-neck in the expansion spec): S-2XL. This is the default
# when SETAPP_VNECK_SIZES is unset; the env var still overrides it.
VNECK_DEFAULT_SIZES = ["S", "M", "L", "XL", "2XL"]

# The V-neck's own placement. The master placement (x 0.5, y 0.47,
# scale 0.32) would put a square badge over the V opening: on the
# 1000x666 vneck template the badge top edge lands at 0.230 of the
# image height while the V opening reaches 0.341, so the badge
# overlaps the V by about 74 px. The V-neck therefore renders with
# its own placement: same scale, centre lower (y 0.60), so the badge
# top (0.360) clears the V. The master placement is untouched, and
# the other types still follow it. An unlocked product's own override
# always wins over this type placement.
VNECK_PLACEMENT = {"x": 0.5, "y": 0.60, "scale": 0.32, "angle": 0}

LOCAL_PREFIX = "local:"

PRODUCT_TYPES = OrderedDict([
    ("tee", {
        "key": "tee",
        "name": "Unisex Tee",
        "garment": "",
        "keywords": [],
        "template_front": "shortsleeve-front.png",
        "template_back": "shortsleeve-back.png",
        "starter": None,
    }),
    ("hoodie", {
        "key": "hoodie",
        "name": "Hoodie",
        "garment": "",
        "keywords": ["hoodie"],
        "template_front": "hoodie-front.png",
        "template_back": None,
        "starter": None,
    }),
    ("crewneck", {
        "key": "crewneck",
        "name": "Crewneck Sweatshirt",
        "garment": "",
        "keywords": ["crewneck"],
        "template_front": "crewneck-front.png",
        "template_back": None,
        "starter": None,
    }),
    ("v-neck", {
        "key": "v-neck",
        "name": "V-Neck Tee",
        "garment": "Bella+Canvas 48",
        "keywords": ["v-neck", "v neck"],
        "template_front": "vneck-front.png",
        "template_back": None,
        # Own placement: the master would put a square badge over the
        # V opening (see VNECK_PLACEMENT above). Only the V-neck has one.
        "placement": dict(VNECK_PLACEMENT),
        "starter": {
            "title": "Oregon Ducks V-Neck Tee",
            "colours": ["Black", "Navy", "Red", "White"],
            "sizes": list(VNECK_DEFAULT_SIZES),
            "price": "29.00",
        },
    }),
    ("classic-long-sleeve", {
        "key": "classic-long-sleeve",
        "name": "Classic Long Sleeve",
        "garment": "Gildan Softstyle 64400 (4.5 oz ring-spun cotton)",
        "keywords": ["classic long sleeve"],
        # Same outline as the plain long sleeve for now. Whether the
        # Classic needs its own outline is an open decision for Ovi.
        "template_front": "longsleeve-front.png",
        "template_back": None,
        "starter": {
            "title": "Oregon Ducks Classic Long Sleeve Tee",
            "colours": ["Black", "Navy", "Royal", "Sport Grey", "White"],
            "sizes": ["S", "M", "L", "XL", "2XL", "3XL"],
            "price": "29.00",
        },
    }),
    ("long-sleeve", {
        "key": "long-sleeve",
        "name": "Long Sleeve Tee",
        "garment": "Gildan 80",
        "keywords": ["long sleeve"],
        "template_front": "longsleeve-front.png",
        "template_back": None,
        "starter": {
            "title": "Oregon Ducks Long Sleeve Tee",
            "colours": ["Ash", "Black", "Dark Heather", "Gold",
                        "Irish Green", "Navy", "Purple", "Red", "Royal",
                        "Sport Grey", "White"],
            "sizes": list(SIZE_LADDER),
            "price": "27.00",
        },
    }),
])

# Legacy keyword order. "classic long sleeve" must be tried before
# "long sleeve", otherwise every Classic title would match the plain
# long sleeve. The default (no keyword matches) is the plain tee.
INFERENCE_ORDER = ["hoodie", "crewneck", "v-neck",
                   "classic-long-sleeve", "long-sleeve"]
DEFAULT_TYPE = "tee"

# The three types Srity can add as local starting products.
NEW_TYPE_KEYS = ["long-sleeve", "classic-long-sleeve", "v-neck"]

# Working default colour for the new types (editable in the app).
DEFAULT_COLOUR = "Black"


def template_filenames():
    """Every design-area template file name any type points at."""
    names = set()
    for t in PRODUCT_TYPES.values():
        for side in ("template_front", "template_back"):
            if t.get(side):
                names.add(t[side])
    return names


def is_type_key(key):
    return isinstance(key, str) and key in PRODUCT_TYPES


def infer_type_key(title):
    """Legacy title-keyword inference (fallback only).

    Returns None for an empty title, otherwise a type key.
    """
    s = str(title or "").strip().lower()
    if not s:
        return None
    for key in INFERENCE_ORDER:
        for kw in PRODUCT_TYPES[key]["keywords"]:
            if kw in s:
                return key
    return DEFAULT_TYPE


def resolve_type_key(product):
    """The type of a product: stored type first, else title keywords."""
    product = product or {}
    stored = product.get("product_type")
    if is_type_key(stored):
        return stored
    return infer_type_key(product.get("title"))


def template_url(product, side="front"):
    """Design-area template URL for a product, or '' when none."""
    key = resolve_type_key(product)
    if key is None:
        return ""
    t = PRODUCT_TYPES[key]
    name = t["template_back"] if side == "back" else t["template_front"]
    return (TEMPLATE_URL_PREFIX + name) if name else ""


def _vneck_sizes():
    """(selected, pool) V-neck sizes.

    Default (decided 2026-11-08): S-2XL selected. Set
    SETAPP_VNECK_SIZES to pre-select a different list. Raises
    ValueError on an invalid setting.
    """
    raw = os.environ.get(VNECK_SIZES_ENV, "").strip()
    if not raw:
        return list(VNECK_DEFAULT_SIZES), list(VNECK_SIZE_POOL)
    wanted = [s.strip().upper() for s in raw.split(",") if s.strip()]
    bad = [s for s in wanted if s not in SIZE_LADDER]
    if not wanted or bad:
        raise ValueError(
            "%s must be a comma list of sizes from %s%s"
            % (VNECK_SIZES_ENV, ", ".join(SIZE_LADDER),
               (" (not valid: %s)" % ", ".join(bad)) if bad else ""))
    selected = [s for s in SIZE_LADDER if s in wanted]
    pool = [s for s in SIZE_LADDER if s in VNECK_SIZE_POOL or s in selected]
    return selected, pool


def starter_for(key):
    """Starting values for a new type, or None for template-only types.

    Returns {title, colours, all_colours, sizes, all_sizes, price}.
    """
    t = PRODUCT_TYPES.get(key)
    if not t or not t["starter"]:
        return None
    s = t["starter"]
    colours = list(s["colours"])
    if DEFAULT_COLOUR in colours:
        colours = [DEFAULT_COLOUR] + [c for c in colours if c != DEFAULT_COLOUR]
    if key == "v-neck":
        sizes, all_sizes = _vneck_sizes()
    else:
        sizes = list(s["sizes"])
        all_sizes = list(s["sizes"])
    return {
        "title": s["title"],
        "colours": colours,
        "all_colours": list(colours),
        "sizes": sizes,
        "all_sizes": all_sizes,
        "price": s["price"],
    }


def local_product_id(key):
    return LOCAL_PREFIX + key


def is_local_id(pid):
    return isinstance(pid, str) and pid.startswith(LOCAL_PREFIX)


def type_placement(key):
    """A type's own placement, or None.

    Only the V-neck defines one (VNECK_PLACEMENT): the master would
    put a square badge over its V opening. Returns a copy, or None.
    """
    t = PRODUCT_TYPES.get(key) or {}
    pl = t.get("placement")
    if not isinstance(pl, dict):
        return None
    return dict(pl)


def local_entry(key):
    """A new set-product entry for a local (not yet linked) product.

    Same shape as an entry filled from a Shopify listing, with
    kind "local" and the type stored. Locked, so it follows the set's
    master placement like every other product, except the V-neck,
    which follows its own type placement (the master would overlap
    its V opening).
    """
    starter = starter_for(key)
    if starter is None:
        raise ValueError("Unknown or template-only product type: %r" % (key,))
    colours = starter["colours"]
    return {
        "product_id": local_product_id(key),
        "kind": "local",
        "product_type": key,
        "title": starter["title"],
        "handle": "",
        "url": "",
        "image": None,
        "images": [],
        "colours": colours,
        "all_colours": starter["all_colours"],
        "sizes": starter["sizes"],
        "all_sizes": starter["all_sizes"],
        "variant_prices": {},
        "variants": None,
        "default_color": colours[0] if colours else None,
        "position": "front",
        "mockups": [],
        "mockup_versions": {},
        "hero_image": None,
        "locked": True,
        "override_placement": None,
        "sale_price": starter["price"],
        "compare_at_price": None,
        "base_cost": None,
    }


def public_types():
    """JSON-safe type table for the designer page and /api/product-types."""
    types = OrderedDict()
    for key, t in PRODUCT_TYPES.items():
        starter = None
        if t["starter"]:
            try:
                s = starter_for(key)
            except ValueError:
                s = {"title": t["starter"]["title"],
                     "colours": list(t["starter"]["colours"]),
                     "sizes": [], "all_sizes": list(VNECK_SIZE_POOL),
                     "price": t["starter"]["price"]}
            starter = {
                "title": s["title"], "colours": s["colours"],
                "sizes": s["sizes"], "all_sizes": s["all_sizes"],
                "price": s["price"], "sizes_decided": bool(s["sizes"]),
            }
        types[key] = {
            "key": key,
            "name": t["name"],
            "garment": t["garment"],
            "keywords": list(t["keywords"]),
            "placement": (dict(t["placement"])
                          if isinstance(t.get("placement"), dict) else None),
            "template_front_url": TEMPLATE_URL_PREFIX + t["template_front"],
            "template_back_url": ((TEMPLATE_URL_PREFIX + t["template_back"])
                                  if t["template_back"] else ""),
            "starter": starter,
        }
    return {"types": types, "order": list(PRODUCT_TYPES.keys()),
            "inference_order": list(INFERENCE_ORDER),
            "new_types": list(NEW_TYPE_KEYS),
            "default_type": DEFAULT_TYPE}
