"""Set App v1 shell: sets, master placement + unlock, mockup rendering.

Storage is a JSON file (data/sets.json) for v1. Shopify wiring lives in
shopify.py and uses the Dev Dashboard OAuth flow: the merchant approves
once at /auth/shopify and the app stores its own Admin API token
server-side. No static token is configured.
No Cat Kiss Fish connection exists in this app by design: Srity runs
everything here from her phone, Ovi fulfills manually after sales.
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import requests
from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory, session

import shopify as shopify_api
from catalog import get_template
import product_types as ptypes
from design_validation import validate_design
from mockup import effective_placement, render_set_mockups
from text_layers import composite_layers, render_text_png, validate_layer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Durable storage: SETAPP_DATA_ROOT points at a persistent directory
# (a Render disk in production). Unset = current behaviour, paths
# under the project tree. Tests override the DATA_FILE/UPLOAD_DIR/
# MOCKUP_DIR globals directly, which still works.
_DATA_ROOT = os.environ.get("SETAPP_DATA_ROOT", "").strip()
if _DATA_ROOT:
    DATA_FILE = os.path.join(_DATA_ROOT, "sets.json")
    UPLOAD_DIR = os.path.join(_DATA_ROOT, "uploads")
    MOCKUP_DIR = os.path.join(_DATA_ROOT, "mockups")
else:
    DATA_FILE = os.path.join(BASE, "data", "sets.json")
    UPLOAD_DIR = os.path.join(BASE, "server", "static", "uploads")
    MOCKUP_DIR = os.path.join(BASE, "server", "static", "mockups")

# Flat garment outlines (design-area templates), served as /static/
# files. Local product types render their mockups on these.
TEMPLATE_DIR = os.path.join(BASE, "server", "static",
                            "design-area-templates")

app = Flask(__name__, static_folder="static", template_folder="templates")

# Needed for the OAuth state value kept in the session during login.
# Single-process server: a per-process random key is fine; set
# FLASK_SECRET_KEY in the environment for multi-process deployments.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)
app.config["MAX_CONTENT_LENGTH"] = 26 * 1024 * 1024
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
_public_url = (
    os.environ.get("APP_PUBLIC_URL")
    or os.environ.get("RENDER_EXTERNAL_URL", "")
).strip()
if _public_url.startswith("https://"):
    app.config["SESSION_COOKIE_SECURE"] = True

if not os.environ.get("SET_APP_PASSWORD"):
    print("WARNING: SET_APP_PASSWORD is not set; the app runs open "
          "(local dev/tests only). Set it in production.")

_WRITE_LOCK = threading.RLock()


def get_app_password():
    """App password, read per request so env changes apply live."""
    return os.environ.get("SET_APP_PASSWORD", "").strip() or None


def _csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(24)
        session["csrf_token"] = token
    return token


@app.before_request
def _gate_request():
    """Write lock + auth + CSRF gate for the API.

    Write lock: every POST /api/* holds one reentrant lock for the
    whole request, so a read-modify-write cycle cannot lose another
    request's edit (two users, one single-process server). Released in
    teardown, even when the gate below answers early.
    Auth/CSRF: exempt are the CSRF token + auth-status GETs (the UI
    needs them to decide whether to show the login form), the Shopify
    OAuth callback (validated by HMAC + state instead), and all
    non-API pages/assets. POST /api/login and /api/logout need CSRF
    but not auth (login is how auth is gained). Everything else under
    /api/ needs auth when a password is configured, and every POST
    needs a valid CSRF token.
    """
    from flask import g
    if request.method == "POST" and request.path.startswith("/api/"):
        _WRITE_LOCK.acquire()
        g._write_locked = True
    path = request.path
    if path in ("/api/csrf-token", "/api/auth-status"):
        return None
    if path == "/auth/shopify/callback":
        return None
    if path == "/auth/shopify":
        password = get_app_password()
        if password and not session.get("app_authed"):
            return jsonify({"error": "Login required."}), 401
        return None
    if not path.startswith("/api/"):
        return None
    if request.method == "POST":
        token = request.headers.get("X-CSRF-Token", "")
        if not token or token != session.get("csrf_token"):
            return jsonify(
                {"error": "CSRF token missing or invalid."}), 403
    if path in ("/api/login", "/api/logout"):
        return None
    password = get_app_password()
    if password and not session.get("app_authed"):
        return jsonify({"error": "Login required."}), 401
    return None


@app.teardown_request
def _release_write_lock(exc=None):
    from flask import g
    if getattr(g, "_write_locked", False):
        g._write_locked = False
        try:
            _WRITE_LOCK.release()
        except RuntimeError:
            pass


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(413)
@app.errorhandler(500)
def _json_error(err):
    code = getattr(err, "code", 500)
    message = "File too large." if code == 413 else (
        getattr(err, "description", None) or "Request failed.")
    if code == 500:
        message = "Something went wrong. Try again."
    return jsonify({"error": message}), code


def load_sets():
    with _WRITE_LOCK:
        for candidate in (DATA_FILE, DATA_FILE + ".bak"):
            if os.path.exists(candidate):
                try:
                    with open(candidate) as f:
                        data = json.load(f)
                    if candidate.endswith(".bak"):
                        print("WARNING: sets.json was corrupt; "
                              "loaded sets.json.bak instead.")
                    return data
                except (OSError, ValueError):
                    continue
    return {}


def save_sets(sets):
    with _WRITE_LOCK:
        parent = os.path.dirname(DATA_FILE)
        os.makedirs(parent, exist_ok=True)
        if os.path.exists(DATA_FILE):
            try:
                shutil.copyfile(DATA_FILE, DATA_FILE + ".bak")
            except OSError:
                pass
        tmp = DATA_FILE + ".tmp." + secrets.token_hex(6)
        with open(tmp, "w") as f:
            json.dump(sets, f, indent=2)
        os.replace(tmp, DATA_FILE)


def find_product(set_obj, pid):
    for p in set_obj.get("products", []):
        if p.get("product_id") == pid:
            return p
    return None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def design_version_of(set_obj):
    """Version counter for the set's artwork; old sets default to 1."""
    try:
        return int(set_obj.get("design_version", 1))
    except (TypeError, ValueError):
        return 1


def bump_design_version(set_obj):
    set_obj["design_version"] = design_version_of(set_obj) + 1
    return set_obj["design_version"]


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# --- Gearlaunch-style campaigns (2026-11-03) ---
# A campaign IS a set, with a Gearlaunch-style status and settings
# block. No profit is stored or computed anywhere in this flow:
# Shopify already owns profit, so the app only stores price and a
# plain base-cost input, and never blocks on cost.
CAMPAIGN_STATUSES = ("draft", "active", "inactive", "locked")


def campaign_defaults():
    return {
        "status": "draft",
        "fulfillment": "LAUNCH_END",
        "end_date": None,
        "storefront_homepage": False,
        "show_countdown": False,
        "fudge_factor": 0,
        "hide_purchases": False,
        "hide_from_search_engines": False,
        "social_buttons": False,
        "upsell_discount": None,
        "tiktok_pixel": "",
        "snapchat_pixel": "",
        "facebook": {
            "custom_audience": "",
            "conversions_api_token": "",
            "page_view_pixel": "",
            "add_to_cart_pixel": "",
            "checkout_pixel": "",
        },
    }


def campaign_of(set_obj):
    """Merged campaign settings for a set (old sets lack the field)."""
    merged = campaign_defaults()
    stored = set_obj.get("campaign") or {}
    for key, value in stored.items():
        if key == "facebook" and isinstance(value, dict):
            merged["facebook"].update(value)
        elif key in merged:
            merged[key] = value
    return merged


def campaign_view(set_obj):
    """Settings view for one set: top-level fields + campaign block."""
    campaign = campaign_of(set_obj)
    slug = set_obj.get("slug") or ""
    shop = shopify_api.shop_domain()
    return {
        "id": set_obj["id"],
        "name": set_obj.get("name") or "",
        "slug": slug,
        "url_path": "/" + slug if slug else "",
        "store_url": (f"https://{shop}/{slug}"
                      if shop and slug else None),
        "tags": list(set_obj.get("tags") or []),
        "description": set_obj.get("description") or "",
        "grouping": set_obj.get("grouping", "combine"),
        "campaign": campaign,
    }


def campaign_summary(set_obj):
    """One row of the campaigns list (Gearlaunch columns, no profit)."""
    campaign = campaign_of(set_obj)
    products = set_obj.get("products") or []
    art = set_obj.get("design_url")
    if not art and products:
        first = products[0]
        art = (first.get("hero_image")
               or (first.get("mockups") or [None])[0]
               or (first.get("images") or [None])[0]
               or first.get("image"))
    slug = set_obj.get("slug") or ""
    return {
        "id": set_obj["id"],
        "art_url": art,
        "name": set_obj.get("name") or "",
        "path": "/" + slug if slug else "",
        "tags": list(set_obj.get("tags") or []),
        # The app tracks no orders: Gearlaunch shows "-" here too.
        "orders": None,
        "items": len(products),
        "status": campaign["status"],
        "fulfillment": campaign["fulfillment"],
        "end": campaign["end_date"],
    }


def _validate_campaign(raw):
    """Validate a partial campaign dict; returns (cleaned, error)."""
    if not isinstance(raw, dict):
        return None, "campaign must be an object"
    cleaned = {}
    if "status" in raw:
        if raw["status"] not in CAMPAIGN_STATUSES:
            return None, "campaign status must be draft, active, " \
                         "inactive or locked"
        cleaned["status"] = raw["status"]
    if "fulfillment" in raw:
        value = str(raw["fulfillment"] or "").strip()
        if len(value) > 50:
            return None, "fulfillment must be 50 characters or fewer"
        cleaned["fulfillment"] = value or "LAUNCH_END"
    if "end_date" in raw:
        value = raw["end_date"]
        if value in (None, ""):
            cleaned["end_date"] = None
        elif isinstance(value, str) and len(value) <= 20:
            cleaned["end_date"] = value
        else:
            return None, "end date must be 20 characters or fewer"
    for field in ("storefront_homepage", "show_countdown",
                  "hide_purchases", "hide_from_search_engines",
                  "social_buttons"):
        if field in raw:
            if not isinstance(raw[field], bool):
                return None, f"{field} must be true or false"
            cleaned[field] = raw[field]
    if "fudge_factor" in raw:
        value = raw["fudge_factor"]
        if isinstance(value, bool):
            return None, "fudge factor must be a whole number"
        if isinstance(value, float) and not value.is_integer():
            return None, "fudge factor must be a whole number"
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None, "fudge factor must be a whole number"
        if not (0 <= number <= 10000):
            return None, "fudge factor must be between 0 and 10000"
        cleaned["fudge_factor"] = number
    if "upsell_discount" in raw:
        value = raw["upsell_discount"]
        if value in (None, ""):
            cleaned["upsell_discount"] = None
        else:
            dec = parse_money_decimal(value)
            if dec is None or dec < 0:
                return None, "upsell discount must be 0 or more"
            cleaned["upsell_discount"] = float(dec)
    for field in ("tiktok_pixel", "snapchat_pixel"):
        if field in raw:
            value = str(raw[field] or "")
            if len(value) > 255:
                return None, f"{field} must be 255 characters or fewer"
            cleaned[field] = value
    if "facebook" in raw:
        if not isinstance(raw["facebook"], dict):
            return None, "facebook pixels must be an object"
        fb = {}
        for field in ("custom_audience", "conversions_api_token",
                      "page_view_pixel", "add_to_cart_pixel",
                      "checkout_pixel"):
            if field in raw["facebook"]:
                value = str(raw["facebook"][field] or "")
                if len(value) > 255:
                    return None, f"{field} must be 255 characters or fewer"
                fb[field] = value
        cleaned["facebook"] = fb
    return cleaned, None


def _parse_tags(raw):
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return None


def layer_png_path(sid, lid):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return os.path.join(UPLOAD_DIR, f"text_{sid}_{lid}.png")


def layer_png_url(sid, lid):
    return f"/static/uploads/text_{sid}_{lid}.png"


def visible_layer_pngs(set_obj, product):
    """Rendered PNGs for layers visible on this product.

    Returns (path, x, y) tuples; x/y None means the placement centre
    (old layers without a position).
    """
    out = []
    per_product_hidden = set(product.get("hidden_layers") or [])
    for layer in set_obj.get("text_layers", []) or []:
        if layer.get("hidden") or layer["id"] in per_product_hidden:
            continue
        path = layer_png_path(set_obj["id"], layer["id"])
        if os.path.exists(path):
            out.append((path, layer.get("x"), layer.get("y")))
    return out


def parse_money(value):
    """Float from a price field, or None when blank/invalid."""
    dec = parse_money_decimal(value)
    return float(dec) if dec is not None else None


def parse_money_decimal(value):
    """Decimal from a price field, or None when blank/invalid.

    Money compares in Decimal (no binary-float surprises); storage
    stays float so the sets.json shape does not change.
    """
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool):
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def product_variant_count(product):
    """Variants this product will actually create on publish, or None.

    The displayed count matches the created count: only pairs with a
    known price are created. A flat sale price prices every selected
    pair; otherwise only pairs with a stored per-variant price count
    (real listings are often non-rectangular: the Oregon tee has 88
    variants across 12 colours x 8 sizes, not 96, because 8 pairs
    have no store price). When no price is recorded at all, fall back
    to the stored variant count from the listing, else the selected
    grid. None when colours or sizes are missing.
    """
    colours = product.get("colours") or []
    sizes = product.get("sizes") or []
    if not colours or not sizes:
        return None
    if (parse_money_decimal(product.get("sale_price")) is not None
            or product.get("variant_prices")):
        return priced_pair_count(product)
    stored = product.get("variants")
    if isinstance(stored, int) and stored >= 0:
        return stored
    return len(colours) * len(sizes)


def variant_summary(set_obj):
    """Per-product counts, combine total, and the 100-variant guard."""
    per_product = {}
    total = 0
    unknown = []
    for p in set_obj.get("products", []):
        n = product_variant_count(p)
        per_product[p["product_id"]] = n
        if n is None:
            unknown.append(p["product_id"])
        else:
            total += n
    grouping = set_obj.get("grouping", "combine")
    if grouping == "grouped":
        return {
            "grouping": grouping,
            "per_product": per_product,
            "total_combine": total,
            "guard_ok": True,
            "message": "Grouped: %d variants, one campaign link." % total,
        }
    if grouping == "combine":
        guard_ok = total <= 100
        message = (
            "Combine mode: %d variants in one listing. Shopify allows "
            "100 per product." % total
        )
        if not guard_ok:
            message += " Over the limit: split the set or reduce colours/sizes."
    else:
        over = [pid for pid, n in per_product.items()
                if n is not None and n > 100]
        guard_ok = not over
        message = "Split mode: one listing per product."
        if not guard_ok:
            message += " Over the 100-variant limit: " + ", ".join(over)
    if unknown:
        message += " Variant count unknown for products without recorded colours/sizes."
    return {
        "grouping": grouping,
        "per_product": per_product,
        "total_combine": total,
        "guard_ok": guard_ok,
        "message": message,
    }


def variant_price_for_pair(product, colour, size):
    """Price for one variant pair, or None when unknown.

    An explicitly set sale_price overrides ALL variants of the product.
    Otherwise the stored per-variant price (from the Shopify listing)
    is used when it covers the pair.
    """
    sale = parse_money_decimal(product.get("sale_price"))
    if sale is not None:
        return sale
    prices = product.get("variant_prices") or {}
    raw = prices.get(f"{colour}||{size}")
    if raw is None:
        raw = prices.get(f"{colour}|{size}")
    return parse_money_decimal(raw)


def priced_pair_count(product):
    """Selected colour/size pairs with a known price.

    An explicit sale price prices every pair. Otherwise only pairs
    with a stored per-variant price count: real store listings are
    often non-rectangular (the Oregon tee has 88 variants across
    12 colours x 8 sizes, not 96), so unpriced pairs are simply not
    created, not a reason to block the whole publish.
    """
    colours = product.get("colours") or []
    sizes = product.get("sizes") or []
    if parse_money_decimal(product.get("sale_price")) is not None:
        return len(colours) * len(sizes)
    n = 0
    for colour in colours:
        for size in sizes:
            if variant_price_for_pair(product, colour, size) is not None:
                n += 1
    return n


def skipped_pair_count(product):
    """Selected pairs with no price (never created on publish)."""
    selected = len(product.get("colours") or []) \
        * len(product.get("sizes") or [])
    return selected - priced_pair_count(product)


def incomplete_products(set_obj):
    """Products missing colours, sizes, or a usable price.

    A product is publishable on price when it has an explicit sale
    price OR at least one priced pair. Unpriced pairs are skipped on
    publish (and warned about in the dry-run), not a blocker: real
    listings are non-rectangular, so demanding full coverage would
    make the Oregon tee (88 real variants over 96 selected pairs)
    unpublishable.
    """
    missing = []
    for p in set_obj.get("products", []):
        reasons = []
        if not (p.get("colours") or []):
            reasons.append("colours")
        if not (p.get("sizes") or []):
            reasons.append("sizes")
        if (parse_money_decimal(p.get("sale_price")) is None
                and priced_pair_count(p) == 0):
            reasons.append("sale price")
        if reasons:
            missing.append({
                "product_id": p["product_id"],
                "title": p.get("title") or p["product_id"],
                "missing": reasons,
            })
    return missing


def absolute_url(path):
    """Absolute URL for a /static/... path, or None without a public URL."""
    base = shopify_api.public_url()
    if not base or not path:
        return None
    return base.rstrip("/") + path


def build_product_payloads(set_obj):
    """Shopify product payloads for a set (combine or split, live).

    Images are absolute mockup URLs when a public app URL is
    configured; otherwise images are omitted (recorded honestly in
    the publish record) because Shopify cannot fetch relative URLs.
    Hero rule: the payload image list is [hero] + [other mockups];
    reorder changes the rest, never the hero slot.
    """
    grouping = set_obj.get("grouping", "combine")
    description = set_obj.get("description", "") or ""
    tags = set_obj.get("tags", []) or []

    def product_images(product):
        urls = []
        hero = product.get("hero_image")
        if hero:
            urls.append(hero)
        for url in product.get("mockups", []) or []:
            if url not in urls:
                urls.append(url)
        absolute = [absolute_url(u) if u.startswith("/") else u for u in urls]
        return [u for u in absolute if u]

    def variant_row(colour, size, price, compare, style=None):
        if style is not None:
            row = {"option1": style, "option2": colour, "option3": size,
                   "price": format(price, ".2f")}
        else:
            row = {"option1": colour, "option2": size,
                   "price": format(price, ".2f")}
        if compare is not None:
            row["compare_at_price"] = format(compare, ".2f")
        return row

    def product_payload(title, product):
        colours = product.get("colours") or []
        sizes = product.get("sizes") or []
        compare = parse_money_decimal(product.get("compare_at_price"))
        variants = []
        for colour in colours:
            for size in sizes:
                price = variant_price_for_pair(product, colour, size)
                if price is None:
                    continue
                variants.append(variant_row(colour, size, price, compare))
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "options": [
                {"name": "Color", "values": colours},
                {"name": "Size", "values": sizes},
            ],
            "variants": variants,
            "images": product_images(product),
        }

    if grouping == "split":
        payloads = []
        for p in set_obj.get("products", []):
            title = p.get("title") or p["product_id"]
            payloads.append(product_payload(title, p))
        return payloads
    if grouping == "grouped":
        # Grouped (Ovi 2026-11-04): one campaign link in the app, but
        # Shopify cannot hold 500 variants in one product (100 cap).
        # Build the full combined variant list, then chunk it into
        # listings of 95 or fewer, titled Set, Set (2), Set (3), ...
        # Each chunk keeps only the Style/Color/Size values it uses,
        # and every variant maps to exactly one chunk, so the
        # storefront picker can map a choice to the correct listing.
        all_variants = []
        for p in set_obj.get("products", []):
            style = p.get("title") or p["product_id"]
            compare = parse_money_decimal(p.get("compare_at_price"))
            for colour in p.get("colours") or []:
                for size in p.get("sizes") or []:
                    price = variant_price_for_pair(p, colour, size)
                    if price is None:
                        continue
                    all_variants.append(variant_row(
                        colour, size, price, compare, style=style))
        images = []
        for p in set_obj.get("products", []):
            for url in product_images(p):
                if url not in images:
                    images.append(url)
        payloads = []
        base_title = set_obj.get("name", "Untitled set")
        for ci in range(0, len(all_variants), 95):
            chunk = all_variants[ci:ci + 95]
            styles = []
            colours = []
            sizes = []
            for v in chunk:
                if v["option1"] not in styles:
                    styles.append(v["option1"])
                if v["option2"] not in colours:
                    colours.append(v["option2"])
                if v["option3"] not in sizes:
                    sizes.append(v["option3"])
            title = base_title if ci == 0 else "%s (%d)" % (
                base_title, ci // 95 + 1)
            payloads.append({
                "title": title,
                "description": description,
                "tags": tags,
                "options": [
                    {"name": "Style", "values": styles},
                    {"name": "Color", "values": colours},
                    {"name": "Size", "values": sizes},
                ],
                "variants": chunk,
                "images": images,
            })
        return payloads
    # Combine: one listing. A Style option keeps each member's variants
    # distinct even when colours/sizes overlap (tee Black/S and hoodie
    # Black/S are different variants, not a duplicate Shopify rejects).
    colours, sizes, styles = [], [], []
    for p in set_obj.get("products", []):
        styles.append(p.get("title") or p["product_id"])
        for c in p.get("colours") or []:
            if c not in colours:
                colours.append(c)
        for s in p.get("sizes") or []:
            if s not in sizes:
                sizes.append(s)
    variants = []
    for p in set_obj.get("products", []):
        style = p.get("title") or p["product_id"]
        compare = parse_money_decimal(p.get("compare_at_price"))
        for colour in p.get("colours") or []:
            for size in p.get("sizes") or []:
                price = variant_price_for_pair(p, colour, size)
                if price is None:
                    continue
                variants.append(variant_row(colour, size, price, compare,
                                            style=style))
    images = []
    for p in set_obj.get("products", []):
        for url in product_images(p):
            if url not in images:
                images.append(url)
    return [{
        "title": set_obj.get("name", "Untitled set"),
        "description": description,
        "tags": tags,
        "options": [
            {"name": "Style", "values": styles},
            {"name": "Color", "values": colours},
            {"name": "Size", "values": sizes},
        ],
        "variants": variants,
        "images": images,
    }]


def _page_authed():
    password = get_app_password()
    return password is None or bool(session.get("app_authed"))


@app.route("/")
def index():
    return redirect("/campaigns")


@app.route("/campaigns")
def campaigns_page():
    if not _page_authed():
        return render_template("login.html", next="/campaigns")
    sets = load_sets()
    rows = [campaign_summary(sets[k]) for k in sorted(sets)]
    return render_template("campaigns.html", rows=rows)


@app.route("/campaigns/<sid>")
def campaign_settings_page(sid):
    if not _page_authed():
        return render_template("login.html", next=f"/campaigns/{sid}")
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    return render_template("campaign_settings.html",
                           view=campaign_view(sets[sid]))


@app.route("/campaigns/<sid>/designer")
def campaign_designer_page(sid):
    if not _page_authed():
        return render_template(
            "login.html", next=f"/campaigns/{sid}/designer")
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    return render_template("designer.html",
                           view=campaign_view(sets[sid]),
                           product_types=ptypes.public_types())


@app.route("/auth/shopify")
def shopify_auth_start():
    """Start the Dev Dashboard OAuth login. Redirects to Shopify."""
    if not shopify_api.configured():
        return (
            jsonify(
                {
                    "error": "Shopify is not configured. Set SHOPIFY_SHOP_DOMAIN, "
                    "SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET."
                }
            ),
            500,
        )
    state = secrets.token_urlsafe(24)
    session["shopify_oauth_state"] = state
    shop = shopify_api.shop_domain()
    uri = shopify_api.redirect_uri(request.url_root)
    if not uri:
        return jsonify({"error": "No public app URL is configured."}), 500
    return redirect(shopify_api.authorize_url(shop, uri, state))


@app.route("/auth/shopify/callback")
def shopify_auth_callback():
    """Shopify redirects here with a code. Validates, exchanges, stores."""
    if request.args.get("state") != session.get("shopify_oauth_state"):
        return jsonify({"error": "state mismatch"}), 400
    shop = (request.args.get("shop") or "").strip().lower()
    expected_shop = shopify_api.shop_domain()
    if expected_shop and shop != expected_shop:
        return jsonify({"error": "shop mismatch"}), 400
    if not shopify_api.validate_hmac(
        request.args.to_dict(), shopify_api.client_secret()
    ):
        return jsonify({"error": "hmac validation failed"}), 400
    code = request.args.get("code", "")
    if not code:
        return jsonify({"error": "missing code"}), 400
    try:
        token = shopify_api.exchange_code(shop, code)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    shopify_api.save_token(token, shop)
    session.pop("shopify_oauth_state", None)
    # The token is never included in the response.
    return jsonify({"ok": True, "shop": shop, "authenticated": True})


@app.route("/api/shopify/status")
def shopify_status():
    """Connection state only. Never includes the token."""
    return jsonify(shopify_api.status())


@app.route("/api/csrf-token")
def csrf_token_route():
    """Per-session CSRF token. No auth needed for this GET: the UI
    fetches it on load, then sends it on every POST."""
    return jsonify({"csrf_token": _csrf_token()})


@app.route("/api/auth-status")
def auth_status():
    """Login state for the UI. Never includes the password."""
    password = get_app_password()
    if password is None:
        return jsonify({"authenticated": True, "password_configured": False})
    return jsonify({"authenticated": bool(session.get("app_authed")),
                    "password_configured": True})


@app.route("/api/login", methods=["POST"])
def login():
    """Log in with the app password. In open mode (no password
    configured) this always succeeds; the UI shows a warning banner
    instead of a login form."""
    password = get_app_password()
    if password is None:
        session["app_authed"] = True
        return jsonify({"authenticated": True, "password_configured": False})
    body = request.get_json(silent=True) or {}
    given = str(body.get("password") or "")
    if given and secrets.compare_digest(given, password):
        session["app_authed"] = True
        return jsonify({"authenticated": True, "password_configured": True})
    return jsonify({"error": "Wrong password."}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("app_authed", None)
    return jsonify({"authenticated": False})


@app.route("/api/products/search")
def search_products():
    """Search Shopify products by title. Returns only id, title,
    price and image URL per product. Never includes the token.
    ?limit= caps results (1-50, default 20)."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"products": []})
    try:
        limit = int(request.args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))
    try:
        results = shopify_api.search_products(q, limit=limit)
    except RuntimeError as exc:
        msg = str(exc)
        if "not authenticated" in msg:
            return (
                jsonify(
                    {
                        "error": "Shopify is not connected. "
                        "Open /auth/shopify and approve the app first."
                    }
                ),
                503,
            )
        return jsonify({"error": "Product search failed. Try again."}), 502
    # Slice defensively: a provider that ignores the limit must not
    # leak more rows than the caller asked for.
    return jsonify({"products": (results or [])[:limit]})


@app.route("/static/uploads/<name>")
def serve_upload(name):
    """Serve an uploaded file from the configured upload dir.

    Needed once storage moves off the Flask static folder (Render
    disk). Only bare filenames are served; paths are rejected.
    """
    if "/" in name or "\\" in name or name.startswith("."):
        return jsonify({"error": "not found"}), 404
    return send_from_directory(UPLOAD_DIR, name)


@app.route("/static/mockups/<name>")
def serve_mockup(name):
    """Serve a rendered mockup from the configured mockup dir."""
    if "/" in name or "\\" in name or name.startswith("."):
        return jsonify({"error": "not found"}), 404
    return send_from_directory(MOCKUP_DIR, name)


@app.route("/api/sets", methods=["GET"])
def list_sets():
    return jsonify(list(load_sets().values()))


@app.route("/api/campaigns", methods=["GET"])
def list_campaigns():
    """Gearlaunch-style campaigns list (one row per set, no profit).

    ?q= filters by name, path (slug) or tag; ?status= filters by
    campaign status. Orders are always null: the app tracks no
    orders, so the list honestly shows "-" for orders.
    """
    q = (request.args.get("q") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()
    rows = []
    for s in load_sets().values():
        row = campaign_summary(s)
        if status and row["status"] != status:
            continue
        if q:
            hay = " ".join([row["name"], row["path"]]
                           + row["tags"]).lower()
            if q not in hay:
                continue
        rows.append(row)
    return jsonify(rows)


@app.route("/api/campaigns", methods=["POST"])
def create_campaign():
    """Create a campaign: creates a set with campaign defaults."""
    body = request.get_json(force=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Campaign name is required."}), 400
    if len(name) > 255:
        return jsonify({"error": "Title must be 255 characters or fewer."}), 400
    slug = str(body.get("slug") or "").strip()
    if slug and (len(slug) > 100 or not SLUG_RE.match(slug)):
        return jsonify({
            "error": "URL slug may only use lowercase letters, numbers "
                     "and hyphens, e.g. oregon-ducks-set."
        }), 400
    tags = _parse_tags(body.get("tags"))
    if tags is None:
        tags = []
    sets = load_sets()
    sid = uuid.uuid4().hex[:12]
    new_set = {
        "id": sid,
        "name": name,
        "description": "",
        "tags": tags,
        "slug": slug,
        "campaign": campaign_defaults(),
        "grouping": "grouped",
        "publish_state": "draft",
        "publish_error": None,
        "artwork_locked": False,
        "design_url": None,
        "design_version": 1,
        "text_layers": [],
        "draft_saved_at": None,
        "products": [],
        "master_placement": {"x": 0.5, "y": 0.45, "scale": 0.5,
                             "angle": 0},
    }
    sets[sid] = new_set
    save_sets(sets)
    return jsonify(new_set), 201


@app.route("/api/sets/bulk-campaign", methods=["POST"])
def bulk_campaign():
    """Bulk Activate / Deactivate / Delete / Tag for campaigns.

    Locked campaigns are skipped by activate/deactivate and listed
    in "skipped". Delete removes the sets (orphan files cleaned
    after removal). Returns the affected full sets for the UI.
    """
    body = request.get_json(force=True) or {}
    action = body.get("action")
    if action not in ("activate", "deactivate", "delete", "tag"):
        return jsonify({
            "error": "action must be activate, deactivate, delete or tag"
        }), 400
    ids = body.get("ids") or []
    if not isinstance(ids, list):
        return jsonify({"error": "ids must be a list"}), 400
    tag = None
    if action == "tag":
        tag = str(body.get("tag") or "").strip()
        if not tag:
            return jsonify({"error": "tag is required for Tag"}), 400
    sets = load_sets()
    updated, skipped, deleted, doomed = [], [], [], []
    for sid in ids:
        s = sets.get(str(sid))
        if s is None:
            continue
        if action in ("activate", "deactivate") \
                and campaign_of(s)["status"] == "locked":
            skipped.append(s["id"])
            continue
        if action == "activate":
            s["campaign"] = campaign_of(s)
            s["campaign"]["status"] = "active"
            updated.append(s)
        elif action == "deactivate":
            s["campaign"] = campaign_of(s)
            s["campaign"]["status"] = "inactive"
            updated.append(s)
        elif action == "tag":
            if tag not in (s.get("tags") or []):
                s.setdefault("tags", []).append(tag)
            updated.append(s)
        elif action == "delete":
            doomed.append(sets.pop(s["id"]))
            deleted.append(s["id"])
    save_sets(sets)
    for gone in doomed:
        _delete_file_if_orphan(sets, gone.get("design_url"))
        for layer in gone.get("text_layers") or []:
            _delete_file_if_orphan(
                sets, layer_png_url(gone["id"], layer["id"]))
    return jsonify({"updated": len(updated), "skipped": skipped,
                    "deleted": len(deleted), "sets": updated})


@app.route("/api/sets/<sid>/campaign", methods=["GET"])
def get_campaign_settings(sid):
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    return jsonify(campaign_view(sets[sid]))


@app.route("/api/sets/<sid>/campaign", methods=["POST"])
def save_campaign_settings(sid):
    """Save campaign settings: validate everything first, then one
    atomic save. Top-level name/slug/tags/description and the
    campaign block are saved together; campaign fields not sent
    keep their current values."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    s = sets[sid]
    if "name" in body:
        name = str(body["name"]).strip()
        if not name:
            return jsonify({"error": "Campaign name is required."}), 400
        if len(name) > 255:
            return jsonify({"error": "Title must be 255 characters or fewer."}), 400
    if "slug" in body:
        slug = str(body["slug"]).strip()
        if slug and (len(slug) > 100 or not SLUG_RE.match(slug)):
            return jsonify({
                "error": "URL slug may only use lowercase letters, numbers "
                         "and hyphens, e.g. oregon-ducks-set."
            }), 400
    tags = None
    if "tags" in body:
        tags = _parse_tags(body["tags"])
        if tags is None:
            return jsonify({"error": "tags must be a list or a string"}), 400
    cleaned, err = _validate_campaign(body.get("campaign") or {})
    if err:
        return jsonify({"error": err}), 400
    if "name" in body:
        s["name"] = str(body["name"]).strip()
    if "slug" in body:
        s["slug"] = str(body["slug"]).strip()
    if "description" in body:
        s["description"] = str(body["description"])
    if tags is not None:
        s["tags"] = tags
    merged = campaign_of(s)
    merged.update(cleaned)
    if "facebook" in cleaned:
        merged["facebook"].update(cleaned["facebook"])
    s["campaign"] = merged
    s["draft_saved_at"] = now_iso()
    save_sets(sets)
    return jsonify(campaign_view(s))


@app.route("/api/sets/<sid>/export", methods=["GET"])
def export_set(sid):
    """Download one set as JSON (backup / move between installs)."""
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    data = json.dumps(sets[sid], indent=2)
    return Response(
        data,
        mimetype="application/json",
        headers={"Content-Disposition":
                 f"attachment; filename={sid}.json"},
    )


@app.route("/api/sets", methods=["POST"])
def create_set():
    body = request.get_json(force=True) or {}
    sets = load_sets()
    sid = uuid.uuid4().hex[:12]
    new_set = {
        "id": sid,
        "name": body.get("name", "Untitled set"),
        "description": "",
        "tags": [],
        "slug": "",
        "campaign": campaign_defaults(),
        "grouping": "grouped",
        "publish_state": "draft",
        "publish_error": None,
        "artwork_locked": False,
        "design_url": None,
        "design_version": 1,
        "text_layers": [],
        "draft_saved_at": None,
        "products": [
            {"product_id": pid, "locked": True, "override_placement": None}
            for pid in body.get("products", [])
        ],
        "master_placement": body.get(
            "master_placement", {"x": 0.5, "y": 0.45, "scale": 0.5, "angle": 0}
        ),
    }
    sets[sid] = new_set
    save_sets(sets)
    return jsonify(new_set), 201


@app.route("/api/sets/<sid>/master", methods=["POST"])
def set_master(sid):
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    placement, err = _validate_placement(body.get("placement"))
    if err:
        return jsonify({"error": err}), 400
    if placement != sets[sid].get("master_placement"):
        sets[sid]["master_placement"] = placement
        bump_design_version(sets[sid])
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products", methods=["POST"])
def add_product(sid):
    """Add a store product, enriched from Shopify.

    A bare product_id used to create a shell entry (no title, colours,
    sizes or prices) that could never be configured or published. Now
    the entry is filled from the live listing; an unknown id, or a
    catalog id sent here by mistake, is rejected and nothing is added.

    Optional body fields (2026-11-07):
      product_type: a type key from product_types.py, stored on the
        product so its design-area template never depends on the title.
        Without it the type is inferred from the Shopify title.
      link_local: the id of a LOCAL product in this set (for example
        "local:long-sleeve"). The new store product REPLACES it in the
        same position: the synced listing wins for title, colours,
        sizes and prices, while the type, lock state, override
        placement and Front/Back position carry over.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    raw = body.get("product_id")
    pid = str(raw).strip() if raw is not None else ""
    if not pid:
        return jsonify({"error": "product_id is required"}), 400
    products = sets[sid]["products"]
    if pid.startswith("catalog:"):
        return jsonify({
            "error": "Catalog templates were removed from the app "
                     "(2026-11-06), so catalog IDs cannot be added."
        }), 400
    if ptypes.is_local_id(pid):
        return jsonify({
            "error": "Local products are added with the product-type "
                     "buttons, not by ID."
        }), 400
    if any(p["product_id"] == pid for p in products):
        return jsonify(sets[sid])
    wanted_type = body.get("product_type")
    if wanted_type not in (None, "") and not ptypes.is_type_key(wanted_type):
        return jsonify({"error": "Unknown product type."}), 400
    local = None
    link_id = body.get("link_local")
    if link_id not in (None, ""):
        local = find_product(sets[sid], str(link_id))
        if local is None or local.get("kind") != "local":
            return jsonify({
                "error": "link_local must be a local product in this set."
            }), 400
    if not shopify_api.authenticated():
        return jsonify({
            "error": "Shopify is not connected. "
                     "Open /auth/shopify and approve the app first."
        }), 503
    try:
        details = shopify_api.get_product_details(pid)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    if details is None:
        return jsonify({
            "error": "No Shopify product with that ID was found."
        }), 400
    entry = _entry_from_details(details)
    if local is not None:
        entry = _linked_entry(entry, local)
    if wanted_type:
        entry["product_type"] = wanted_type
    if local is not None:
        index = next(i for i, p in enumerate(products)
                     if p["product_id"] == local["product_id"])
        products[index] = entry
    else:
        products.append(entry)
    save_sets(sets)
    if local is not None:
        # The local placeholder's renders were drawn on the flat
        # outline: drop them, and delete files nothing else uses.
        old = list(local.get("mockups") or [])
        if (local.get("hero_image") or "").startswith("/static/mockups/"):
            old.append(local["hero_image"])
        for url in set(old):
            _delete_file_if_orphan(sets, url)
    return jsonify(sets[sid])


def _linked_entry(fresh, local):
    """A synced store entry that takes over from a local placeholder.

    Source-of-truth rule: the Shopify listing wins for everything it
    knows (title, handle, photos, colours, sizes, per-variant prices),
    and the working price is dropped so the listing's prices apply.
    What the seller set up in the app carries over: the product type,
    the lock state and override placement, Front/Back position, and
    per-product design hiding. Renders made on the flat outline do not
    carry over (they are stale for a real product photo).
    """
    entry = dict(fresh)
    entry["product_type"] = (local.get("product_type")
                             or fresh.get("product_type")
                             or ptypes.DEFAULT_TYPE)
    for key in ("locked", "override_placement", "position",
                "hide_design", "hidden_layers"):
        if key in local:
            entry[key] = local[key]
    return entry


def _entry_from_details(details):
    """A set-product entry filled from a Shopify listing.

    Products are auto-selected: colours/sizes default to the full
    lists. If a details dict arrives with empty colours/sizes but a
    full list on file, fill from the full list so no product can
    arrive unselected (nothing is invented: only lists already
    present in details are used).
    """
    colours = list(details.get("colours") or
                   details.get("all_colours") or [])
    sizes = list(details.get("sizes") or
                 details.get("all_sizes") or [])
    all_colours = list(details.get("all_colours") or colours)
    all_sizes = list(details.get("all_sizes") or sizes)
    shop = shopify_api.shop_domain()
    handle = details.get("handle") or ""
    url = f"https://{shop}/products/{handle}" if shop and handle else ""
    prices = {}
    for key, price in (details.get("variant_prices") or {}).items():
        # Real listings arrive with (colour, size) tuple keys; accept
        # string keys too ("Black||S" or "Black / S") so a JSON
        # round-trip of a details dict can never crash the add.
        if isinstance(key, (list, tuple)) and len(key) == 2:
            colour, size = key
        elif isinstance(key, str) and "||" in key:
            colour, size = key.split("||", 1)
        elif isinstance(key, str) and " / " in key:
            colour, size = key.split(" / ", 1)
        else:
            continue
        prices[f"{colour}||{size}"] = str(price)
    return {
        "product_id": details["product_id"],
        "kind": "store",
        "title": details.get("title") or details["product_id"],
        "handle": handle,
        "url": url,
        "image": details.get("image"),
        "images": list(details.get("images") or []),
        "colours": colours,
        "all_colours": all_colours,
        "sizes": sizes,
        "all_sizes": all_sizes,
        "variant_prices": prices,
        "variants": details.get("variants"),
        "default_color": colours[0] if colours else None,
        "position": "front",
        "mockups": [],
        "mockup_versions": {},
        "hero_image": None,
        "locked": True,
        "override_placement": None,
        "sale_price": None,
        "compare_at_price": None,
        "base_cost": None,
        # Stored type: the design-area template follows this, not the
        # title, so a later rename cannot move it. Inferred from the
        # title once, here, for products added without a type.
        "product_type": (ptypes.infer_type_key(
            details.get("title") or details["product_id"])
            or ptypes.DEFAULT_TYPE),
    }


@app.route("/api/sets/<sid>/products/<path:pid>/refresh", methods=["POST"])
def refresh_product(sid, pid):
    """Re-sync one store product from Shopify.

    Updates title/handle/image/images/options/variant prices/count.
    Never overwrites the seller's selected colours/sizes, sale or
    compare-at prices, base cost, default colour, lock or placement.
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    if p.get("kind") == "catalog":
        return jsonify({
            "error": "Catalog templates have no Shopify listing to "
                     "refresh from."
        }), 400
    if p.get("kind") == "local":
        return jsonify({
            "error": "This is a local product with no Shopify listing "
                     "yet. Link it to its Shopify product first."
        }), 400
    if not shopify_api.authenticated():
        return jsonify({
            "error": "Shopify is not connected. "
                     "Open /auth/shopify and approve the app first."
        }), 503
    try:
        details = shopify_api.get_product_details(pid)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    if details is None:
        return jsonify({
            "error": "This product no longer exists in Shopify."
        }), 400
    fresh = _entry_from_details(details)
    # Pin the type from the OLD title before the title is overwritten,
    # so a rename in Shopify cannot silently change the template of a
    # product that was added before types existed.
    if not ptypes.is_type_key(p.get("product_type")):
        p["product_type"] = (ptypes.resolve_type_key(p)
                             or ptypes.DEFAULT_TYPE)
    for key in ("title", "handle", "url", "image", "images",
                "all_colours", "all_sizes", "variant_prices", "variants"):
        p[key] = fresh[key]
    save_sets(sets)
    return jsonify(sets[sid])


def _title_taken(set_obj, title, except_pid=None):
    """True when another product in the set already has this title.

    Titles become the Style option of a grouped or combined listing,
    so two products with the same title would create duplicate
    variants that Shopify rejects. Compared case-insensitively.
    """
    wanted = " ".join(str(title).split()).lower()
    for p in set_obj.get("products", []):
        if p["product_id"] == except_pid:
            continue
        have = " ".join(str(p.get("title") or "").split()).lower()
        if have == wanted:
            return True
    return False


def _clear_renders(p):
    """Forget a product's rendered mockups; returns the old URLs."""
    old = list(p.get("mockups") or [])
    if (p.get("hero_image") or "").startswith("/static/mockups/"):
        old.append(p["hero_image"])
        p["hero_image"] = None
    p["mockups"] = []
    p["mockup_versions"] = {}
    p["mockup_version"] = None
    return old


@app.route("/api/product-types", methods=["GET"])
def list_product_types():
    """The locally defined product types (no supplier, no catalogue)."""
    return jsonify(ptypes.public_types())


@app.route("/api/sets/<sid>/local-products", methods=["POST"])
def add_local_product(sid):
    """Add one of the new types as a LOCAL product, before its real
    Shopify listing exists.

    Body: {"type": "long-sleeve" | "classic-long-sleeve" | "v-neck"}.
    The entry starts from the type's working title, colours, sizes and
    price, is locked (follows the master placement) and designs on the
    type's flat outline. A real publish is blocked until it is linked
    to its Shopify listing. One local product per type per set.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    key = body.get("type")
    if not (isinstance(key, str) and key in ptypes.NEW_TYPE_KEYS):
        return jsonify({
            "error": "Choose one of: " + ", ".join(ptypes.NEW_TYPE_KEYS)
        }), 400
    pid = ptypes.local_product_id(key)
    if find_product(sets[sid], pid) is not None:
        return jsonify({
            "error": "That product type is already in this set."
        }), 400
    try:
        entry = ptypes.local_entry(key)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if _title_taken(sets[sid], entry["title"]):
        return jsonify({
            "error": "A product in this set already has the title "
                     "'%s'. Rename it first." % entry["title"]
        }), 400
    sets[sid]["products"].append(entry)
    save_sets(sets)
    return jsonify(sets[sid]), 201


@app.route("/api/sets/<sid>/products/<path:pid>/type", methods=["POST"])
def set_product_type(sid, pid):
    """Set (or clear) a product's stored type.

    The design-area template follows the stored type. Clearing it
    (type null) falls back to the title keywords. A LOCAL product's
    renders were drawn on the old outline, so they are cleared when its
    template changes; store products render on their own photo, so
    nothing is cleared for them.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    key = body.get("type")
    if key not in (None, "") and not ptypes.is_type_key(key):
        return jsonify({"error": "Unknown product type."}), 400
    before = ptypes.template_url(p, "front")
    if key in (None, ""):
        p.pop("product_type", None)
    else:
        p["product_type"] = key
    old = []
    if p.get("kind") == "local" \
            and ptypes.template_url(p, "front") != before:
        old = _clear_renders(p)
    save_sets(sets)
    for url in set(old):
        _delete_file_if_orphan(sets, url)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/title", methods=["POST"])
def rename_local_product(sid, pid):
    """Rename a LOCAL product (Ovi chooses the final titles).

    Store products keep the title Shopify has: rename them in Shopify,
    then tap Refresh. Titles must be unique inside the set because the
    title is the Style option of a grouped or combined listing. The
    template does not change: it follows the stored type.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    if p.get("kind") != "local":
        return jsonify({
            "error": "The title of a Shopify product comes from Shopify. "
                     "Rename it there, then tap Refresh."
        }), 400
    title = " ".join(str(body.get("title") or "").split())
    if not title:
        return jsonify({"error": "Type a title first."}), 400
    if len(title) > 255:
        return jsonify({
            "error": "Title must be 255 characters or fewer."}), 400
    if _title_taken(sets[sid], title, except_pid=pid):
        return jsonify({
            "error": "Another product in this set already has that "
                     "title. Titles must be different."
        }), 400
    p["title"] = title
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/default-color",
           methods=["POST"])
def set_default_color(sid, pid):
    """Set a product's default colour (must be a selected colour).

    The default moves to the front of the colours list, so the first
    variant of the listing is the default.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    colour = str(body.get("colour") or "").strip()
    if not colour or colour not in (p.get("colours") or []):
        return jsonify({
            "error": "Default colour must be one of the selected colours."
        }), 400
    p["default_color"] = colour
    p["colours"] = [colour] + [c for c in p["colours"] if c != colour]
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/position",
           methods=["POST"])
def set_product_position(sid, pid):
    """Per-product Front/Back position (Gearlaunch designer radio).

    Stored only. Back-side printing is not built, so choosing Back
    does not change the mockup; the UI says so honestly.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    position = str(body.get("position") or "").strip().lower()
    if position not in ("front", "back"):
        return jsonify({"error": "position must be front or back"}), 400
    p["position"] = position
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/colors",
           methods=["POST"])
def set_product_colors(sid, pid):
    """Pick colors modal save: selected colours + default colour.

    Colours must come from the product's full colour list
    (all_colours, falling back to the current selection). The
    default, when given, must be in the selection and moves to the
    front, matching the existing default-colour behaviour.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    if "colours" not in body or not isinstance(body["colours"], list):
        return jsonify({"error": "colours must be a list"}), 400
    colours = list(dict.fromkeys(str(c) for c in body["colours"]))
    allowed = p.get("all_colours") or p.get("colours") or []
    if any(c not in allowed for c in colours):
        return jsonify({
            "error": "Colours must come from the product's colour list."
        }), 400
    default = body.get("default_color")
    if default is not None and default != "":
        default = str(default)
        if default not in colours:
            return jsonify({
                "error": "Default colour must be one of the selected colours."
            }), 400
        colours = [default] + [c for c in colours if c != default]
        p["default_color"] = default
    else:
        if p.get("default_color") not in colours:
            p["default_color"] = colours[0] if colours else None
    p["colours"] = colours
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/remove", methods=["POST"])
def remove_product(sid, pid):
    """Remove a product from the set (the trash icon).

    Blocked once the set is published live: the live listing already
    lists the product, so duplicate the set instead of editing it.
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    if sets[sid].get("publish_state") == "published":
        return jsonify({
            "error": "This set is already published live. "
                     "Duplicate the set to change its products."
        }), 409
    before = len(sets[sid]["products"])
    sets[sid]["products"] = [
        p for p in sets[sid]["products"] if p["product_id"] != pid
    ]
    if len(sets[sid]["products"]) == before:
        return jsonify({"error": "product not in set"}), 404
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<pid>/lock", methods=["POST"])
def set_lock(sid, pid):
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    for p in sets[sid]["products"]:
        if p["product_id"] == pid:
            before = p.get("override_placement")
            p["locked"] = bool(body.get("locked", True))
            if "placement" in body and body["placement"] is not None:
                # Clamp to the fixed print area, like every other
                # placement save, instead of storing raw values.
                placement, placement_err = _validate_placement(
                    body["placement"])
                if placement_err:
                    return jsonify({"error": placement_err}), 400
                p["override_placement"] = placement
            if p["locked"]:
                p["override_placement"] = None
            # A changed override changes what renders, so mark
            # mockups stale until re-previewed (previously the
            # version check kept reporting current and publish
            # could ship the pre-drag image).
            if p.get("override_placement") != before:
                bump_design_version(sets[sid])
            save_sets(sets)
            return jsonify(sets[sid])
    return jsonify({"error": "product not in set"}), 404


@app.route("/api/sets/<sid>/details", methods=["POST"])
def set_details(sid):
    """Title (max 255), URL slug, description, tags, combine/split.

    Every save stamps draft_saved_at: the set is a saved draft, not a
    published product. Publishing is direct (live) via /publish.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    s = sets[sid]
    if "name" in body:
        name = str(body["name"])
        if len(name) > 255:
            return jsonify({"error": "Title must be 255 characters or fewer."}), 400
        s["name"] = name
    if "slug" in body:
        slug = str(body["slug"]).strip()
        if slug and (len(slug) > 100 or not SLUG_RE.match(slug)):
            return jsonify({
                "error": "URL slug may only use lowercase letters, numbers "
                         "and hyphens, e.g. oregon-ducks-set."
            }), 400
        s["slug"] = slug
    if "description" in body:
        s["description"] = str(body["description"])
    if "tags" in body:
        raw_tags = body["tags"]
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        s["tags"] = tags
    if "grouping" in body:
        if body["grouping"] not in ("combine", "split", "grouped"):
            return jsonify({"error": "grouping must be combine or split"}), 400
        s["grouping"] = body["grouping"]
    s["draft_saved_at"] = now_iso()
    save_sets(sets)
    return jsonify(s)


@app.route("/api/sets/<sid>/save-draft", methods=["POST"])
def save_draft(sid):
    """Explicit Save Draft: stamps draft_saved_at, changes nothing else.

    The set remains a local draft, not a published product. This is the
    Gearlaunch "Save and exit" equivalent; publishing is separate and
    direct (live).
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    sets[sid]["draft_saved_at"] = now_iso()
    save_sets(sets)
    return jsonify(sets[sid])


def _validate_placement(raw):
    """Placement dict or an error string."""
    if not isinstance(raw, dict):
        return None, "placement must be an object"
    try:
        x = float(raw["x"])
        y = float(raw["y"])
        scale = float(raw["scale"])
        angle = float(raw.get("angle", 0))
    except (KeyError, TypeError, ValueError):
        return None, "placement needs numeric x, y, scale"
    # Review fix (mockup fix, B1): clamp to the FIXED print area
    # (left 25%, top 20%, width 50%, height 50%) and cap scale at
    # 0.5 (the box width), instead of merely range-checking 0-1.
    # This is what makes preview and published mockups agree: a
    # slider at 0.10 can no longer save/publish outside the box.
    # Rotation is about the design centre and may extend past the
    # box corners at large angles; only centre and width are clamped.
    x = min(0.75, max(0.25, x))
    y = min(0.70, max(0.20, y))
    scale = min(0.5, max(0.1, scale))
    if not (-180 <= angle <= 180):
        return None, "placement angle must be between -180 and 180"
    return {"x": x, "y": y, "scale": scale, "angle": angle}, None


@app.route("/api/sets/<sid>/save-all", methods=["POST"])
def save_all(sid):
    """Save EVERYTHING the editor holds, in one atomic save.

    The top Save button used to stamp draft_saved_at only, silently
    dropping slider, details, colour/size and price edits. This
    endpoint validates everything FIRST (so a bad field saves nothing),
    then applies placement, details, grouping and every product's
    colours/sizes/pricing, and stamps draft_saved_at.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    s = sets[sid]
    placement, placement_err = None, None
    if "placement" in body and body["placement"] is not None:
        placement, placement_err = _validate_placement(body["placement"])
        if placement_err:
            return jsonify({"error": placement_err}), 400
    details = body.get("details") or {}
    if "name" in details:
        if len(str(details["name"])) > 255:
            return jsonify({"error": "Title must be 255 characters or fewer."}), 400
    if "slug" in details:
        slug = str(details["slug"]).strip()
        if slug and (len(slug) > 100 or not SLUG_RE.match(slug)):
            return jsonify({
                "error": "URL slug may only use lowercase letters, numbers "
                         "and hyphens, e.g. oregon-ducks-set."
            }), 400
    if "grouping" in details and details["grouping"] not in ("combine", "split", "grouped"):
        return jsonify({"error": "grouping must be combine or split"}), 400
    if "grouping" in body and body["grouping"] not in ("combine", "split", "grouped"):
        return jsonify({"error": "grouping must be combine or split"}), 400
    product_updates = {}
    for entry in body.get("products") or []:
        pid = str(entry.get("product_id") or "")
        p = find_product(s, pid)
        if p is None:
            return jsonify({"error": f"product {pid} is not in the set"}), 400
        prices = {}
        for field in ("sale_price", "compare_at_price", "base_cost"):
            if field in entry:
                value = parse_money_decimal(entry[field])
                if entry[field] not in (None, "") and value is None:
                    return jsonify({"error": f"{field} must be a number"}), 400
                prices[field] = value
        sale = prices.get("sale_price")
        compare = prices.get("compare_at_price")
        if sale is not None and compare is not None and compare <= sale:
            return jsonify({
                "error": "Compare-at must be higher than the sale price."
            }), 400
        override = None
        if "override_placement" in entry and entry["override_placement"] is not None:
            # SaveAll must carry unlocked overrides too: previously
            # a drag on an unlocked product was silently discarded
            # by Save, which then reported saved.
            override, override_err = _validate_placement(
                entry["override_placement"])
            if override_err:
                return jsonify({"error": override_err}), 400
        product_updates[pid] = {
            "colours": ([str(c) for c in entry["colours"]]
                        if "colours" in entry else None),
            "sizes": ([str(z) for z in entry["sizes"]]
                      if "sizes" in entry else None),
            "prices": prices,
            "override_placement": override,
        }
    if placement is not None and placement != s.get("master_placement"):
        s["master_placement"] = placement
        bump_design_version(s)
    if "name" in details:
        s["name"] = str(details["name"])
    if "slug" in details:
        s["slug"] = str(details["slug"]).strip()
    if "description" in details:
        s["description"] = str(details["description"])
    if "tags" in details:
        raw_tags = details["tags"]
        if isinstance(raw_tags, str):
            s["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            s["tags"] = [str(t).strip() for t in raw_tags if str(t).strip()]
    if "grouping" in details:
        s["grouping"] = details["grouping"]
    elif "grouping" in body:
        s["grouping"] = body["grouping"]
    for pid, upd in product_updates.items():
        p = find_product(s, pid)
        if upd["colours"] is not None:
            p["colours"] = upd["colours"]
        if upd["sizes"] is not None:
            p["sizes"] = upd["sizes"]
        if upd.get("override_placement") is not None and \
                p.get("override_placement") != upd["override_placement"]:
            p["override_placement"] = upd["override_placement"]
            bump_design_version(s)
        for field, value in upd["prices"].items():
            p[field] = float(value) if value is not None else None
    s["draft_saved_at"] = now_iso()
    save_sets(sets)
    return jsonify(s)


def _orphan_files_referenced(sets, url):
    """True when any remaining set still references a file URL."""
    for s in sets.values():
        if s.get("design_url") == url:
            return True
        for p in s.get("products", []):
            if url in (p.get("mockups") or []) or p.get("hero_image") == url:
                return True
    return False


def _delete_file_if_orphan(sets, url):
    """Delete a /static/uploads|mockups file when no set references it."""
    if not url or not url.startswith("/static/"):
        return
    if _orphan_files_referenced(sets, url):
        return
    if "/uploads/" in url:
        base = UPLOAD_DIR
    elif "/mockups/" in url:
        base = MOCKUP_DIR
    else:
        return
    path = os.path.join(base, os.path.basename(url))
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@app.route("/api/sets/<sid>/duplicate", methods=["POST"])
def duplicate_set(sid):
    """Duplicate a set: new id, " (copy)" name, draft state, artwork
    unlocked. Bulk-clone rule (Ovi, 2026-11-03): a clone starts with
    NO design, so a new design never stacks on the old printed one.
    Products, colours, sizes, prices, placement and campaign settings
    are kept; design, text layers and rendered mockups are blanked."""
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    import copy
    new_set = copy.deepcopy(sets[sid])
    new_sid = uuid.uuid4().hex[:12]
    new_set["id"] = new_sid
    new_set["name"] = (new_set.get("name") or "Untitled set") + " (copy)"
    new_set["publish_state"] = "draft"
    new_set["publish_error"] = None
    new_set["artwork_locked"] = False
    new_set["publish_record"] = None
    new_set["publish_partial"] = None
    new_set["draft_saved_at"] = None
    # Review fix (2026-11-03): a duplicate is a fresh draft, so its
    # campaign status resets to draft even when the original was
    # locked or active; otherwise the copy could never be activated
    # from the UI. Other campaign settings (pixels, countdown, etc.)
    # are copied as-is.
    new_set["campaign"] = campaign_of(new_set)
    new_set["campaign"]["status"] = "draft"
    # Blank-clone: no design, no layers, no rendered mockups. The
    # original set is untouched (deepcopy was already made); no layer
    # PNG files are copied, so nothing old can render on the clone.
    new_set["design_url"] = None
    new_set["design_width"] = None
    new_set["design_height"] = None
    new_set["design_dpi"] = None
    new_set["design_warnings"] = []
    new_set["design_version"] = 1
    new_set["text_layers"] = []
    for p in new_set.get("products", []):
        p["mockups"] = []
        p["mockup_versions"] = {}
        p["mockup_version"] = None
        p["hidden_layers"] = []
        if (p.get("hero_image") or "").startswith("/static/mockups/"):
            p["hero_image"] = None
    sets[new_sid] = new_set
    save_sets(sets)
    return jsonify(new_set), 201


@app.route("/api/sets/<sid>/delete", methods=["POST"])
def delete_set(sid):
    """Delete a set. Orphaned design/layer files are removed only when
    no remaining set references them."""
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    doomed = sets.pop(sid)
    save_sets(sets)
    _delete_file_if_orphan(sets, doomed.get("design_url"))
    for layer in doomed.get("text_layers") or []:
        _delete_file_if_orphan(
            sets, layer_png_url(sid, layer["id"]))
    return jsonify({"deleted": sid})


@app.route("/api/sets/<sid>/products/<path:pid>/variants", methods=["POST"])
def set_product_variants(sid, pid):
    """Colour/size tick selection for one product in the set."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    if "colours" in body:
        p["colours"] = [str(c) for c in body["colours"]]
    if "sizes" in body:
        p["sizes"] = [str(s) for s in body["sizes"]]
    # Clearing colours must not leave a stale default that is no
    # longer selected.
    if p.get("default_color") not in (p.get("colours") or []):
        p["default_color"] = (p["colours"][0] if p["colours"] else None)
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/pricing", methods=["POST"])
def set_product_pricing(sid, pid):
    """Sale price, compare-at price and base cost for one product.

    Compare-at must be higher than the sale price when both are set.
    Base cost is a plain cost input: no profit is computed from it
    and nothing is blocked on cost (Shopify already owns profit).
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    values = {}
    for field in ("sale_price", "compare_at_price", "base_cost"):
        if field in body:
            value = parse_money_decimal(body[field])
            if body[field] not in (None, "") and value is None:
                return jsonify({"error": f"{field} must be a number"}), 400
            values[field] = value
    sale = values.get("sale_price", parse_money_decimal(p.get("sale_price")))
    compare = values.get(
        "compare_at_price", parse_money_decimal(p.get("compare_at_price")))
    if sale is not None and compare is not None and compare <= sale:
        return jsonify({
            "error": "Compare-at must be higher than the sale price."
        }), 400
    for field, value in values.items():
        p[field] = float(value) if value is not None else None
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/hero", methods=["POST"])
def set_product_hero(sid, pid):
    """Choose which mockup image is the hero for one product."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    image = (body.get("image") or "").strip()
    if not image:
        return jsonify({"error": "image is required"}), 400
    allowed = list(p.get("mockups", []) or [])
    if p.get("hero_image"):
        allowed.append(p["hero_image"])
    if p.get("image"):
        allowed.append(p["image"])
    for img in p.get("images", []) or []:
        allowed.append(img)
    if image not in allowed:
        return jsonify({"error": "image is not one of this product's mockups"}), 400
    p["hero_image"] = image
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/mockups/reorder",
           methods=["POST"])
def reorder_mockups(sid, pid):
    """Reorder a product's mockups (up/down beyond the hero pick).

    Body {order: [...]} must be a permutation of the current mockups
    list. The hero pick is untouched.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    current = list(p.get("mockups", []) or [])
    order = body.get("order") or []
    if sorted(order) != sorted(current):
        return jsonify({
            "error": "order must list each current mockup exactly once."
        }), 400
    p["mockups"] = list(order)
    save_sets(sets)
    return jsonify(sets[sid])


def _find_layer(set_obj, lid):
    for layer in set_obj.get("text_layers", []) or []:
        if layer["id"] == lid:
            return layer
    return None


@app.route("/api/sets/<sid>/design/remove", methods=["POST"])
def remove_design(sid):
    """Remove the design from the whole set (text layers stay).

    Blocked once the artwork is locked after a real publish.
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    if sets[sid].get("artwork_locked"):
        return jsonify({
            "error": "This set's design is locked after publishing. "
                     "Duplicate the set to change the design."
        }), 409
    sets[sid]["design_url"] = None
    sets[sid]["design_width"] = None
    sets[sid]["design_height"] = None
    sets[sid]["design_dpi"] = None
    sets[sid]["design_warnings"] = []
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/layers", methods=["POST"])
def add_text_layer(sid):
    """Add a basic text layer (content, font, size, colour, lettercase,
    rotation, opacity, position). Renders its transparent PNG
    immediately. Position defaults to the master placement, so text
    starts at the design spot; old layers without a position fall
    back to the placement centre at render time."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    if sets[sid].get("artwork_locked"):
        return jsonify({
            "error": "This set's design is locked after publishing. "
                     "Duplicate the set to change it."
        }), 409
    layer, error = validate_layer(body)
    if error:
        return jsonify({"error": error}), 400
    master = sets[sid].get("master_placement") or {}
    if layer.get("x") is None:
        layer["x"] = float(master.get("x", 0.5))
    if layer.get("y") is None:
        layer["y"] = float(master.get("y", 0.47))
    render_text_png(layer, layer_png_path(sid, layer["id"]))
    sets[sid].setdefault("text_layers", []).append(layer)
    bump_design_version(sets[sid])
    save_sets(sets)
    return jsonify({"layer": layer, "set": sets[sid]}), 201


@app.route("/api/sets/<sid>/layers/<lid>/edit", methods=["POST"])
def edit_text_layer(sid, lid):
    """Edit a text layer (any field incl. position) and re-render
    its PNG. Position fields omitted keep their current values."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    if sets[sid].get("artwork_locked"):
        return jsonify({
            "error": "This set's design is locked after publishing. "
                     "Duplicate the set to change it."
        }), 409
    layer = _find_layer(sets[sid], lid)
    if layer is None:
        return jsonify({"error": "layer not found"}), 404
    merged = dict(layer)
    for key in ("content", "font", "size", "colour", "lettercase",
                "rotation", "opacity", "x", "y"):
        if key in body:
            merged[key] = body[key]
    merged["id"] = layer["id"]
    merged["hidden"] = layer.get("hidden", False)
    new_layer, error = validate_layer(merged)
    if error:
        return jsonify({"error": error}), 400
    new_layer["id"] = layer["id"]
    new_layer["hidden"] = layer.get("hidden", False)
    render_text_png(new_layer, layer_png_path(sid, lid))
    for i, old in enumerate(sets[sid].get("text_layers", [])):
        if old["id"] == lid:
            sets[sid]["text_layers"][i] = new_layer
            break
    bump_design_version(sets[sid])
    save_sets(sets)
    return jsonify({"layer": new_layer, "set": sets[sid]})


@app.route("/api/sets/<sid>/layers/<lid>/move", methods=["POST"])
def move_text_layer(sid, lid):
    """Move a text layer up/down in the layer order (swap with the
    neighbour). Body {dir: -1 | 1}."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    layers = sets[sid].get("text_layers", []) or []
    idx = next((i for i, l in enumerate(layers) if l["id"] == lid), None)
    if idx is None:
        return jsonify({"error": "layer not found"}), 404
    try:
        direction = int(body.get("dir", body.get("direction", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "dir must be -1 or 1"}), 400
    if direction not in (-1, 1):
        return jsonify({"error": "dir must be -1 or 1"}), 400
    target = idx + direction
    if target < 0 or target >= len(layers):
        return jsonify({"error": "layer is already at that end"}), 400
    layers[idx], layers[target] = layers[target], layers[idx]
    bump_design_version(sets[sid])
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/layers/<lid>/hide", methods=["POST"])
def hide_text_layer(sid, lid):
    """Eye hide/show for a text layer, across the whole set."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    layer = _find_layer(sets[sid], lid)
    if layer is None:
        return jsonify({"error": "layer not found"}), 404
    layer["hidden"] = bool(body.get("hidden", True))
    bump_design_version(sets[sid])
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/layers/<lid>/delete", methods=["POST"])
def delete_text_layer(sid, lid):
    """Delete a text layer on ALL products (global delete)."""
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    before = len(sets[sid].get("text_layers", []) or [])
    sets[sid]["text_layers"] = [
        layer for layer in (sets[sid].get("text_layers") or [])
        if layer["id"] != lid
    ]
    if len(sets[sid]["text_layers"]) == before:
        return jsonify({"error": "layer not found"}), 404
    for p in sets[sid]["products"]:
        p["hidden_layers"] = [
            x for x in (p.get("hidden_layers") or []) if x != lid
        ]
    path = layer_png_path(sid, lid)
    if os.path.exists(path):
        os.remove(path)
    bump_design_version(sets[sid])
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/layers/<lid>/hide",
           methods=["POST"])
def hide_layer_on_product(sid, pid, lid):
    """Hide a text layer on THIS product only (per-product delete)."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    if _find_layer(sets[sid], lid) is None:
        return jsonify({"error": "layer not found"}), 404
    hidden = set(p.get("hidden_layers") or [])
    if body.get("hidden", True):
        hidden.add(lid)
    else:
        hidden.discard(lid)
    p["hidden_layers"] = sorted(hidden)
    bump_design_version(sets[sid])
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/design-hide",
           methods=["POST"])
def hide_design_on_product(sid, pid):
    """Hide the main design on THIS product only (its mockup renders
    the bare photo, plus any visible text layers)."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    p["hide_design"] = bool(body.get("hidden", True))
    bump_design_version(sets[sid])
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/variant-count", methods=["GET"])
def get_variant_count(sid):
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    return jsonify(variant_summary(sets[sid]))


def mockup_is_current(set_obj, product):
    """True when the product's display mockup matches the design version.

    Missing version info counts as stale (old renders predate
    versioning). A product with no mockups at all is NOT stale here:
    it simply has no images, which the publish preview warns about
    but does not block — only stale renders block a real publish.
    """
    mockups = product.get("mockups") or []
    hero = product.get("hero_image")
    display = hero if hero in mockups else (mockups[0] if mockups else None)
    if display is None:
        return True
    if display.startswith("/static/mockups/"):
        versions = product.get("mockup_versions") or {}
        if versions.get(display) == design_version_of(set_obj):
            return True
        return product.get("mockup_version") == design_version_of(set_obj)
    return True


def publish_checklist(set_obj, payloads):
    """Per-product publish readiness, for the dry-run preview."""
    combine = set_obj.get("grouping", "combine") == "combine"
    by_title = {}
    for payload in payloads:
        by_title[payload["title"]] = payload
    rows = []
    for p in set_obj.get("products", []):
        title = p.get("title") or p["product_id"]
        payload = by_title.get(title)
        sale = parse_money_decimal(p.get("sale_price"))
        prices = []
        for colour in p.get("colours") or []:
            for size in p.get("sizes") or []:
                price = variant_price_for_pair(p, colour, size)
                if price is not None:
                    prices.append(price)
        # No profit is computed here: Shopify already owns profit.
        # base_cost stays a plain cost input for the seller's records.
        base = parse_money_decimal(p.get("base_cost"))
        if combine:
            combined = payloads[0] if payloads else None
            variants = len([v for v in (combined or {}).get("variants", [])
                            if v.get("option1") == title]) \
                if combined else 0
            image_urls = []
            if p.get("hero_image"):
                image_urls.append(p["hero_image"])
            for url in p.get("mockups") or []:
                if url not in image_urls:
                    image_urls.append(url)
            images = len(image_urls)
        else:
            variants = len(payload["variants"]) if payload else 0
            images = len(payload["images"]) if payload else 0
        rows.append({
            "product_id": p["product_id"],
            "title": title,
            "design": bool(set_obj.get("design_url")),
            "mockup_current": mockup_is_current(set_obj, p),
            "colours": len(p.get("colours") or []),
            "sizes": len(p.get("sizes") or []),
            "price": (f"{float(sale):.2f}" if sale is not None
                      else (f"{float(min(prices)):.2f} to "
                            f"{float(max(prices)):.2f}" if prices else None)),
            "price_source": ("sale price" if sale is not None
                             else ("store prices" if prices else None)),
            "base_cost": (f"{float(base):.2f}" if base is not None else None),
            "variants": variants,
            "skipped_pairs": skipped_pair_count(p),
            "images": images,
            "kind": p.get("kind", "store"),
            "linked": p.get("kind") != "local",
            "ready": bool(set_obj.get("design_url")
                          and p.get("kind") != "local"
                          and mockup_is_current(set_obj, p)
                          and p.get("colours") and p.get("sizes")
                          and (sale is not None or prices)),
        })
    return rows


@app.route("/api/sets/<sid>/publish", methods=["POST"])
def publish_live(sid):
    """Publish a set to Shopify as LIVE/ACTIVE products, immediately.

    DIRECT PUBLISH (Ovi, 2026-11-03 21:30): there is no draft review
    step. Tapping Publish creates visible, buyable products at once.
    Guards, in order: already published; no design uploaded; products
    missing colours/sizes/price; variant-limit guard; stale mockups
    (real publish only). No profit guard: Shopify already owns profit,
    so a price below base cost never blocks a publish. Body
    {"dry_run": true} returns
    the planned payloads plus warnings and a per-product checklist,
    without calling Shopify and without changing publish state.
    A real publish records publish_state "published" and locks
    the artwork (design uploads are then rejected until the set is
    duplicated). Failures never leave "launching" stuck: the state
    becomes "failed" with the partial progress saved, and a retry
    resumes from the first payload that was not created instead of
    duplicating the ones that already exist.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    s = sets[sid]
    dry_run = bool(body.get("dry_run"))
    if not dry_run and s.get("publish_state") == "published":
        return jsonify({
            "error": "This set is already published live. "
                     "Duplicate the set to publish a new version."
        }), 409
    if not s.get("design_url"):
        return jsonify({"error": "Upload a design first."}), 400
    if not s.get("products"):
        return jsonify({"error": "Add a product to the set first."}), 400
    missing = incomplete_products(s)
    if missing:
        return jsonify({
            "error": "Some products are missing details.",
            "products": missing,
        }), 400
    local_products = [p for p in s.get("products", [])
                      if p.get("kind") == "local"]
    if local_products and not dry_run:
        return jsonify({
            "error": "Link these products to their Shopify listings "
                     "before publishing for real: "
                     + ", ".join(p.get("title") or p["product_id"]
                                 for p in local_products)
                     + ". Their mockups use a flat garment outline, "
                       "not a product photo.",
            "products": [{"product_id": p["product_id"],
                          "title": p.get("title") or p["product_id"]}
                         for p in local_products],
        }), 400
    summary = variant_summary(s)
    # The variant-limit guard counts variants that will actually be
    # created (priced pairs), not selected pairs: a non-rectangular
    # listing creates fewer variants than colours x sizes.
    publishable = {p["product_id"]: priced_pair_count(p)
                   for p in s.get("products", [])}
    if s.get("grouping", "combine") == "combine":
        publishable_total = sum(publishable.values())
        if publishable_total > 100:
            return jsonify({
                "error": f"Combine mode: {publishable_total} variants "
                         "in one listing. Shopify allows 100 per "
                         "product. Over the limit: split the set or "
                         "reduce colours/sizes.",
            }), 400
    elif s.get("grouping", "combine") == "split":
        over = [p.get("title") or p["product_id"]
                for p in s.get("products", [])
                if publishable[p["product_id"]] > 100]
        if over:
            return jsonify({
                "error": "Split mode: one listing per product. Over the "
                         "100-variant limit: " + ", ".join(over),
            }), 400
    # Grouped: no per-product variant check here. build_product_payloads
    # chunks the combined variant list into listings itself, so a
    # product with more than 100 variants (the Gildan Long Sleeve has
    # 117) must not be blocked, and no limit text is shown in this mode.
    payloads = build_product_payloads(s)
    warnings = []
    if local_products:
        warnings.append(
            "Not linked to a Shopify listing yet (a real publish is "
            "blocked until they are): "
            + ", ".join(p.get("title") or p["product_id"]
                        for p in local_products)
            + ". Their mockups use the flat garment outline, not a "
              "product photo.")
    skipped = [(p.get("title") or p["product_id"],
                skipped_pair_count(p))
               for p in s.get("products", [])
               if skipped_pair_count(p) > 0]
    if skipped:
        warnings.append(
            "These selected colour/size pairs have no store price and "
            "will not be created: "
            + ", ".join(f"{t} ({n})" for t, n in skipped) + ".")
    if not shopify_api.public_url():
        warnings.append(
            "No public app URL is configured, so published products will "
            "have no images. Set APP_PUBLIC_URL and re-publish.")
    stale = [p.get("title") or p["product_id"]
             for p in s.get("products", [])
             if not mockup_is_current(s, p)]
    if stale:
        if dry_run:
            warnings.append(
                "These products need a fresh Preview first (their "
                "mockups are older than the current design): "
                + ", ".join(stale))
        else:
            return jsonify({
                "error": "Some mockups are older than the current design. "
                         "Tap Preview all mockups, then publish again.",
                "products": stale,
            }), 400
    if dry_run:
        if s.get("grouping", "combine") == "split" \
                and shopify_api.authenticated():
            try:
                for payload in payloads:
                    hits = shopify_api.search_products(payload["title"])
                    if any((h.get("title") or "").strip().lower()
                           == payload["title"].strip().lower()
                           for h in hits):
                        warnings.append(
                            f"A Shopify product called "
                            f"'{payload['title']}' already exists. "
                            f"Publishing creates NEW live products; it does "
                            f"not update the existing listing.")
            except RuntimeError:
                warnings.append(
                    "Could not check for existing titles (Shopify "
                    "search failed); publishing still creates new live products.")
        elif s.get("grouping", "combine") == "split":
            warnings.append(
                "Shopify is not connected, so the existing-title check "
                "was skipped; publishing creates new live products.")
        return jsonify({
            "dry_run": True,
            "grouping": s.get("grouping", "combine"),
            "variant_summary": summary,
            "publishable_variants": publishable,
            "products": payloads,
            "warnings": warnings,
            "checklist": publish_checklist(s, payloads),
            "note": "Nothing was created in Shopify. This is a preview only. "
                    "A real publish creates LIVE products immediately.",
        })
    if not shopify_api.authenticated():
        return jsonify({
            "error": "Shopify is not connected. "
                     "Open /auth/shopify and approve the app first."
        }), 503
    partial = s.get("publish_partial") or {}
    if s.get("publish_state") in ("failed", "launching") and partial:
        created = list(partial.get("created") or [])
        start_index = int(partial.get("next_index") or 0)
    else:
        created = []
        start_index = 0
    s["publish_state"] = "launching"
    s["publish_error"] = None
    save_sets(sets)
    try:
        for index in range(start_index, len(payloads)):
            payload = payloads[index]
            made = shopify_api.create_live_product(
                title=payload["title"],
                description=payload["description"],
                tags=payload["tags"],
                options=payload["options"],
                variants=payload["variants"],
                images=payload["images"],
            )
            status = (made or {}).get("status")
            if status != "active":
                raise RuntimeError(
                    "Shopify returned product "
                    f"{(made or {}).get('id')} with status "
                    f"'{status}' instead of active. It was NOT counted "
                    f"as published; check it in Shopify admin, delete "
                    f"it if needed, then publish again.")
            created.append({
                "index": index,
                "title": payload["title"],
                "shopify_id": (made or {}).get("id"),
                "handle": (made or {}).get("handle"),
            })
            s["publish_partial"] = {"created": created,
                                    "next_index": index + 1}
            save_sets(sets)
    except Exception as exc:
        s["publish_state"] = "failed"
        s["publish_error"] = str(exc)
        s["publish_partial"] = {"created": created,
                                "next_index": len(created)}
        save_sets(sets)
        return jsonify({"error": str(exc)}), 502
    s["publish_state"] = "published"
    s["publish_error"] = None
    s["artwork_locked"] = True
    s["publish_partial"] = None
    s["publish_record"] = {
        "mode": s.get("grouping", "combine"),
        "products": created,
        "shopify_ids": [c.get("shopify_id") for c in created],
        "images_included": bool(payloads and payloads[0].get("images")),
        "warnings": warnings,
    }
    save_sets(sets)
    return jsonify({
        "published": True,
        "state": "published",
        "shopify_ids": s["publish_record"]["shopify_ids"],
    })


@app.route("/api/sets/<sid>/create-page", methods=["POST"])
def create_set_page(sid):
    """Create a HIDDEN Shopify Page for a published set.

    Title = set name, body = description + one linked block per
    created live product (title link + image). published_at is null,
    so the page stays hidden until Ovi publishes it in Shopify admin.
    The app never publishes the page live. A second create is rejected:
    the page already exists (its id is in the publish record).
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    s = sets[sid]
    if s.get("publish_state") != "published":
        return jsonify({
            "error": "Publish the set first, then create "
                     "its page."
        }), 400
    record = s.get("publish_record") or {}
    if record.get("page_id"):
        return jsonify({
            "error": "This set already has a page "
                     f"(page id {record['page_id']})."
        }), 409
    if not shopify_api.authenticated():
        return jsonify({
            "error": "Shopify is not connected. "
                     "Open /auth/shopify and approve the app first."
        }), 503
    shop = shopify_api.shop_domain()
    blocks = []
    for item in record.get("products") or []:
        title = item.get("title") or ""
        handle = item.get("handle") or ""
        link = f"https://{shop}/products/{handle}" if handle else ""
        if link:
            blocks.append(f'<p><a href="{link}">{title}</a></p>')
        else:
            blocks.append(f"<p>{title}</p>")
    # Campaign settings feed the hidden page as plain notes only:
    # the page stays hidden (published_at null), so no setting here
    # changes anything live in the store.
    campaign = campaign_of(s)
    notes = []
    if campaign["show_countdown"]:
        notes.append(
            f"<p>Countdown timer enabled (fudge factor "
            f"{campaign['fudge_factor']}).</p>")
    if campaign["social_buttons"]:
        notes.append("<p>Social buttons enabled on the campaign page.</p>")
    if campaign["hide_from_search_engines"]:
        notes.append("<!-- noindex: hidden from search engines -->")
    body_html = (s.get("description") or "") + "\n" + "\n".join(blocks) \
        + ("\n" + "\n".join(notes) if notes else "")
    try:
        page = shopify_api.create_page(s.get("name") or "Untitled set",
                                       body_html)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502
    record["page_id"] = page.get("id")
    s["publish_record"] = record
    save_sets(sets)
    return jsonify({"page_id": page.get("id"),
                    "published": False,
                    "note": "Hidden until you publish it in Shopify admin."})


@app.route("/api/sets/<sid>/upload", methods=["POST"])
def upload_design(sid):
    """Upload + validate a design. Rejects non-transparent files.

    After a real publish the artwork is locked and uploads
    return 409 (duplicate the set to change the design). A new design
    makes every rendered mockup stale, so all mockup lists and
    mockup-URL heroes are cleared (files are deleted only when no
    other set references them) and the design version is bumped.
    The response never includes a server filesystem path.
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    if sets[sid].get("artwork_locked"):
        return jsonify({
            "error": "This set's design is locked after publishing. "
                     "Duplicate the set to change the design."
        }), 409
    if "design" not in request.files:
        return jsonify({"error": "no design file"}), 400
    f = request.files["design"]
    result = validate_design(f.stream, f.filename)
    if not result["ok"]:
        return jsonify({"error": result["error"]}), 400
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = os.path.basename(f.filename or "design.png")
    path = os.path.join(UPLOAD_DIR, f"{sid}_{uuid.uuid4().hex[:8]}_{safe_name}")
    f.stream.seek(0)
    f.save(path)
    url = "/static/uploads/" + os.path.basename(path)
    old_url = sets[sid].get("design_url")
    sets[sid]["design_url"] = url
    # Artwork spec line data for the editor (dimensions + est. DPI).
    sets[sid]["design_width"] = result.get("width")
    sets[sid]["design_height"] = result.get("height")
    sets[sid]["design_dpi"] = result.get("dpi_estimate")
    sets[sid]["design_warnings"] = result.get("warnings", [])
    old_mockups = []
    for p in sets[sid].get("products", []):
        old_mockups.extend(p.get("mockups") or [])
        if (p.get("hero_image") or "").startswith("/static/mockups/"):
            old_mockups.append(p["hero_image"])
    for p in sets[sid].get("products", []):
        p["mockups"] = []
        p["mockup_versions"] = {}
        p["mockup_version"] = None
        if (p.get("hero_image") or "").startswith("/static/mockups/"):
            p["hero_image"] = None
    bump_design_version(sets[sid])
    save_sets(sets)
    if old_url and old_url != url:
        _delete_file_if_orphan(sets, old_url)
    for old_mockup in set(old_mockups):
        _delete_file_if_orphan(sets, old_mockup)
    return jsonify({"url": url, "validation": result})


@app.route("/api/sets/<sid>/products/<path:pid>/photo", methods=["GET"])
def product_photo(sid, pid):
    """Product photo URL for the centre mockup.

    Default priority: the product's own stored mockups/hero/images,
    then the Shopify featured image via the stored token. With ?bare=1
    the priority is the BARE photo only (stored image/images[0],
    Shopify featured) — never a rendered mockup — so rendering never
    composites design-on-design. Never mutates sets.json. No photo (no
    token, failed lookup, or none on file) returns photo null with an
    honest error instead of an invented image.
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    bare = request.args.get("bare") == "1"
    if not bare:
        for url in (p.get("mockups") or []):
            if url:
                return jsonify({"photo": url, "source": "mockup"})
        if p.get("hero_image"):
            return jsonify({"photo": p["hero_image"], "source": "hero"})
    for url in (p.get("images") or []):
        if url:
            return jsonify({"photo": url, "source": "product"})
    if p.get("image"):
        return jsonify({"photo": p["image"], "source": "product"})
    if p.get("kind") == "local":
        # No Shopify listing yet: design on the type's flat outline.
        url = ptypes.template_url(p, "front")
        if url:
            return jsonify({"photo": url, "source": "template"})
        return jsonify({"photo": None,
                        "error": "no template for this product type"}), 200
    template = get_template(pid)
    if template and template.get("images"):
        return jsonify({"photo": template["images"][0],
                        "source": "catalog"})
    if p.get("kind") == "catalog":
        return jsonify({"photo": None,
                        "error": "no catalog image on file"}), 200
    try:
        url = shopify_api.get_product_image(pid)
    except Exception:
        return jsonify({"photo": None,
                        "error": "Shopify photo unavailable"}), 200
    if url:
        return jsonify({"photo": url, "source": "shopify"})
    return jsonify({"photo": None,
                    "error": "no photo on file for this product"}), 200


def bare_photo_for_product(set_obj, product):
    """Bare (unrendered) photo URL for a product, or None.

    Order: stored image/images[0], Shopify featured.
    Rendered mockups are never returned here.
    """
    for url in (product.get("images") or []):
        if url:
            return url
    if product.get("image"):
        return product["image"]
    if product.get("kind") == "local":
        return ptypes.template_url(product, "front") or None
    template = get_template(product["product_id"])
    if template and template.get("images"):
        return template["images"][0]
    if product.get("kind") == "catalog":
        return None
    try:
        return shopify_api.get_product_image(product["product_id"])
    except Exception:
        return None


MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


def download_image(url, dest):
    """Download an https image URL to dest, with guards.

    https only, content-type must start with image/, at most
    MAX_DOWNLOAD_BYTES (checked on Content-Length first, then while
    streaming). Raises ValueError/RuntimeError on any violation.
    """
    if not url.startswith("https://"):
        raise ValueError("only https image URLs can be downloaded")
    r = requests.get(url, timeout=30, stream=True)
    try:
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip()
        if not ctype.startswith("image/"):
            raise ValueError("URL did not return an image")
        declared = r.headers.get("Content-Length")
        if declared is not None:
            try:
                if int(declared) > MAX_DOWNLOAD_BYTES:
                    raise ValueError("image is over the 25 MB limit")
            except ValueError as exc:
                if "over the 25 MB" in str(exc):
                    raise
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        total = 0
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    fh.close()
                    os.remove(dest)
                    raise ValueError("image is over the 25 MB limit")
                fh.write(chunk)
    finally:
        r.close()
    return dest


def _mockup_hash(design_path, placement, layer_items):
    """Short hash of everything a render depends on, so the filename
    is unique per input: re-rendering identical inputs reuses the
    file, changed inputs get a new file."""
    h = hashlib.sha256()
    if design_path and os.path.exists(design_path):
        with open(design_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    else:
        h.update(b"nodesign")
    h.update(json.dumps(placement, sort_keys=True).encode("utf-8"))
    for item in layer_items:
        path = item[0] if isinstance(item, (list, tuple)) else item
        if path and os.path.exists(path):
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
        h.update(str(item).encode("utf-8"))
    return h.hexdigest()[:10]


@app.route("/api/sets/<sid>/mockups", methods=["POST"])
def make_mockups(sid):
    """Body: {design: path, photos: {product_id: photo_path}}.

    A missing or empty design renders the bare product photo (plus any
    visible text layers) instead of failing, so Preview mockup works
    before a design is uploaded. Each product renders with its
    effective placement (master or override), skipping the design for
    products that hide it, and compositing each product's visible text
    layers on top. A photo that is itself a rendered mockup
    (/static/mockups/…) is replaced with that product's bare photo,
    so design is never composited on design. Rendered filenames are
    unique per input and APPENDED (cap 6 per product, oldest files
    deleted only when no set references them). Rendered URLs are
    stamped with the set's current design version. Per-product
    failures are reported in "errors" while other products still
    render; nothing is saved for a product that failed.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    set_obj = sets[sid]

    def static_local(path):
        """Map a server-issued /static/ URL to its configured dir."""
        name = os.path.basename(path)
        if "/design-area-templates/" in path:
            # Only the known outline files, never an arbitrary path.
            if name in ptypes.template_filenames():
                return os.path.join(TEMPLATE_DIR, name)
            return None
        if "/uploads/" in path:
            return os.path.join(UPLOAD_DIR, name)
        if "/mockups/" in path:
            return os.path.join(MOCKUP_DIR, name)
        return None

    def resolve(path, product=None):
        """Resolve a render input to a local file.

        Allowed: /static/… URLs the server itself issued, or https
        image URLs (downloaded with guards). A rendered mockup given
        as a product's photo is replaced with the bare photo. Client
        filesystem paths are rejected.
        """
        if not path:
            return None
        if path.startswith("/static/mockups/") and product is not None:
            bare = bare_photo_for_product(set_obj, product)
            if bare is None:
                raise ValueError("no bare photo for this product")
            return resolve(bare, product)
        if path.startswith("/static/"):
            local = static_local(path)
            if local is None or not os.path.exists(local):
                raise ValueError("photo not found on the server")
            return local
        if path.startswith("https://"):
            name = hashlib.md5(path.encode("utf-8")).hexdigest() + ".jpg"
            local = os.path.join(UPLOAD_DIR, "_photo_" + name)
            if not os.path.exists(local):
                download_image(path, local)
            return local
        raise ValueError("photo must be a server /static/ URL or https URL")

    try:
        design_arg = body.get("design") or None
        design_path = None
        if design_arg:
            if design_arg.startswith("/static/"):
                design_path = static_local(design_arg)
                if design_path is None or not os.path.exists(design_path):
                    return jsonify(
                        {"error": "design not found on the server"}), 400
            else:
                return jsonify(
                    {"error": "design must be a server /static/ URL"}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    os.makedirs(MOCKUP_DIR, exist_ok=True)
    urls = {}
    errors = {}
    for p in set_obj["products"]:
        pid = p["product_id"]
        photo_arg = (body.get("photos") or {}).get(pid)
        if not photo_arg:
            continue
        try:
            photo = resolve(photo_arg, product=p)
            placement = effective_placement(set_obj, pid)
            layers = visible_layer_pngs(set_obj, p)
            digest = _mockup_hash(
                None if p.get("hide_design") else design_path,
                placement, layers)
            safe_pid = re.sub(r"[^A-Za-z0-9_-]", "_", pid)
            out = os.path.join(MOCKUP_DIR,
                               f"{sid}_{safe_pid}_{digest}.jpg")
            design = None if p.get("hide_design") else design_path
            composite_layers(photo, design, placement, layers, out)
            url = "/static/mockups/" + os.path.basename(out)
            urls[pid] = url
        except Exception as exc:
            errors[pid] = str(exc)
    for pid, url in urls.items():
        p = find_product(set_obj, pid)
        if p is None:
            continue
        mockups = [u for u in (p.get("mockups") or []) if u != url]
        mockups.append(url)
        while len(mockups) > 6:
            oldest = mockups.pop(0)
            keep = False
            for s in sets.values():
                for other in s.get("products", []):
                    if oldest in (other.get("mockups") or []) \
                            or other.get("hero_image") == oldest:
                        keep = True
            if not keep:
                _delete_file_if_orphan(sets, oldest)
        p["mockups"] = mockups
        versions = dict(p.get("mockup_versions") or {})
        versions[url] = design_version_of(set_obj)
        p["mockup_versions"] = versions
        p["mockup_version"] = design_version_of(set_obj)
        if not p.get("hero_image"):
            p["hero_image"] = url
    save_sets(sets)
    result = {"mockups": urls}
    if errors:
        result["errors"] = errors
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
