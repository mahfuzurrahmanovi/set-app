"""Set App v1 shell: sets, master placement + unlock, mockup rendering.

Storage is a JSON file (data/sets.json) for v1. Shopify wiring lives in
shopify.py and uses the Dev Dashboard OAuth flow: the merchant approves
once at /auth/shopify and the app stores its own Admin API token
server-side. No static token is configured.
No Cat Kiss Fish connection exists in this app by design: Srity runs
everything here from her phone, Ovi fulfills manually after sales.
"""

import json
import os
import re
import secrets
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, redirect, request, send_from_directory, session

import shopify as shopify_api
from catalog import TEMPLATES, get_template, template_entry
from design_validation import validate_design
from mockup import effective_placement, render_set_mockups
from text_layers import composite_layers, render_text_png, validate_layer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE, "data", "sets.json")
UPLOAD_DIR = os.path.join(BASE, "server", "static", "uploads")
MOCKUP_DIR = os.path.join(BASE, "server", "static", "mockups")

app = Flask(__name__, static_folder="static", template_folder="templates")

# Needed for the OAuth state value kept in the session during login.
# Single-process server: a per-process random key is fine; set
# FLASK_SECRET_KEY in the environment for multi-process deployments.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)


def load_sets():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}


def save_sets(sets):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(sets, f, indent=2)


def find_product(set_obj, pid):
    for p in set_obj.get("products", []):
        if p.get("product_id") == pid:
            return p
    return None


def now_iso():
    return datetime.now(timezone.utc).isoformat()


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def layer_png_path(sid, lid):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return os.path.join(UPLOAD_DIR, f"text_{sid}_{lid}.png")


def layer_png_url(sid, lid):
    return f"/static/uploads/text_{sid}_{lid}.png"


def visible_layer_pngs(set_obj, product):
    """Rendered PNG paths for layers visible on this product."""
    out = []
    per_product_hidden = set(product.get("hidden_layers") or [])
    for layer in set_obj.get("text_layers", []) or []:
        if layer.get("hidden") or layer["id"] in per_product_hidden:
            continue
        path = layer_png_path(set_obj["id"], layer["id"])
        if os.path.exists(path):
            out.append(path)
    return out


def parse_money(value):
    """Float from a price field, or None when blank/invalid."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def product_variant_count(product):
    """Selected colours x selected sizes, or None when not recorded."""
    colours = product.get("colours") or []
    sizes = product.get("sizes") or []
    if not colours or not sizes:
        return None
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


def profit_problems(set_obj):
    """Products where sale price is below base cost (negative profit)."""
    problems = []
    for p in set_obj.get("products", []):
        sale = parse_money(p.get("sale_price"))
        cost = parse_money(p.get("base_cost"))
        if sale is not None and cost is not None and sale < cost:
            problems.append({
                "product_id": p["product_id"],
                "title": p.get("title") or p["product_id"],
                "sale_price": sale,
                "base_cost": cost,
            })
    return problems


def incomplete_products(set_obj):
    """Products missing colours, sizes, or sale price (unpublishable)."""
    missing = []
    for p in set_obj.get("products", []):
        reasons = []
        if not (p.get("colours") or []):
            reasons.append("colours")
        if not (p.get("sizes") or []):
            reasons.append("sizes")
        if parse_money(p.get("sale_price")) is None:
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


def build_draft_payloads(set_obj):
    """Shopify draft product payloads for a set (combine or split).

    Images are absolute mockup URLs when a public app URL is
    configured; otherwise images are omitted (recorded honestly in
    the publish record) because Shopify cannot fetch relative URLs.
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

    def product_payload(title, product):
        colours = product.get("colours") or []
        sizes = product.get("sizes") or []
        sale = parse_money(product.get("sale_price"))
        compare = parse_money(product.get("compare_at_price"))
        variants = []
        for colour in colours:
            for size in sizes:
                row = {
                    "option1": colour,
                    "option2": size,
                    "price": "%.2f" % sale,
                }
                if compare is not None:
                    row["compare_at_price"] = "%.2f" % compare
                variants.append(row)
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
    # Combine: one listing; variants carry each member's own price.
    colours, sizes = [], []
    for p in set_obj.get("products", []):
        for c in p.get("colours") or []:
            if c not in colours:
                colours.append(c)
        for s in p.get("sizes") or []:
            if s not in sizes:
                sizes.append(s)
    variants = []
    for p in set_obj.get("products", []):
        sale = parse_money(p.get("sale_price"))
        compare = parse_money(p.get("compare_at_price"))
        for colour in p.get("colours") or []:
            for size in p.get("sizes") or []:
                row = {
                    "option1": colour,
                    "option2": size,
                    "price": "%.2f" % sale,
                }
                if compare is not None:
                    row["compare_at_price"] = "%.2f" % compare
                variants.append(row)
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
            {"name": "Color", "values": colours},
            {"name": "Size", "values": sizes},
        ],
        "variants": variants,
        "images": images,
    }]


@app.route("/")
def index():
    return send_from_directory(app.template_folder, "index.html")


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


@app.route("/api/products/search")
def search_products():
    """Search Shopify products by title. Returns only id, title,
    price and image URL per product. Never includes the token."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"products": []})
    try:
        results = shopify_api.search_products(q)
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
    return jsonify({"products": results})


@app.route("/api/sets", methods=["GET"])
def list_sets():
    return jsonify(list(load_sets().values()))


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
        "grouping": "combine",
        "publish_state": "draft",
        "publish_error": None,
        "artwork_locked": False,
        "design_url": None,
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
    sets[sid]["master_placement"] = body.get("placement", sets[sid]["master_placement"])
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products", methods=["POST"])
def add_product(sid):
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    raw = body.get("product_id")
    pid = str(raw).strip() if raw is not None else ""
    if not pid:
        return jsonify({"error": "product_id is required"}), 400
    products = sets[sid]["products"]
    if not any(p["product_id"] == pid for p in products):
        products.append(
            {"product_id": pid, "locked": True, "override_placement": None}
        )
        save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/remove", methods=["POST"])
def remove_product(sid, pid):
    """Remove a product from the set (the trash icon).

    Blocked once the set is published as a draft: the draft already
    lists the product, so duplicate the set instead of editing it.
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    if sets[sid].get("publish_state") == "published_draft":
        return jsonify({
            "error": "This set is already published as a draft. "
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
            p["locked"] = bool(body.get("locked", True))
            if "placement" in body and body["placement"] is not None:
                p["override_placement"] = body["placement"]
            if p["locked"]:
                p["override_placement"] = None
            save_sets(sets)
            return jsonify(sets[sid])
    return jsonify({"error": "product not in set"}), 404


@app.route("/api/sets/<sid>/details", methods=["POST"])
def set_details(sid):
    """Title (max 255), URL slug, description, tags, combine/split.

    Every save stamps draft_saved_at: the set is a saved draft, not a
    published product. Publishing stays draft-only via /publish-draft.
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
        if body["grouping"] not in ("combine", "split"):
            return jsonify({"error": "grouping must be combine or split"}), 400
        s["grouping"] = body["grouping"]
    s["draft_saved_at"] = now_iso()
    save_sets(sets)
    return jsonify(s)


@app.route("/api/sets/<sid>/save-draft", methods=["POST"])
def save_draft(sid):
    """Explicit Save Draft: stamps draft_saved_at, changes nothing else.

    The set remains a draft, not a published product. This is the
    Gearlaunch "Save and exit" equivalent; publishing is separate and
    draft-only.
    """
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    sets[sid]["draft_saved_at"] = now_iso()
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/catalog-templates", methods=["POST"])
def add_catalog_templates(sid):
    """Add catalog templates (1 or all 3) as designable set products.

    Body: {"product_ids": [...]} or {"all": true}. Deduplicates.
    Templates are clearly marked kind=catalog in the stored entry.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    if body.get("all"):
        wanted = [t["product_id"] for t in TEMPLATES]
    else:
        wanted = body.get("product_ids", [])
    added = []
    for pid in wanted:
        template = get_template(pid)
        if template is None:
            continue
        if find_product(sets[sid], pid) is None:
            sets[sid]["products"].append(template_entry(template))
            added.append(pid)
    save_sets(sets)
    return jsonify({"added": added, "set": sets[sid]})


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
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/products/<path:pid>/pricing", methods=["POST"])
def set_product_pricing(sid, pid):
    """Sale price, compare-at price and base cost for one product."""
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    p = find_product(sets[sid], pid)
    if p is None:
        return jsonify({"error": "product not in set"}), 404
    for field in ("sale_price", "compare_at_price", "base_cost"):
        if field in body:
            value = parse_money(body[field])
            if body[field] not in (None, "") and value is None:
                return jsonify({"error": f"{field} must be a number"}), 400
            p[field] = value
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

    Blocked once the artwork is locked after a real draft publish.
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
    rotation, opacity). Renders its transparent PNG immediately."""
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
    render_text_png(layer, layer_png_path(sid, layer["id"]))
    sets[sid].setdefault("text_layers", []).append(layer)
    save_sets(sets)
    return jsonify({"layer": layer, "set": sets[sid]}), 201


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
    save_sets(sets)
    return jsonify(sets[sid])


@app.route("/api/sets/<sid>/variant-count", methods=["GET"])
def get_variant_count(sid):
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    return jsonify(variant_summary(sets[sid]))


@app.route("/api/sets/<sid>/publish-draft", methods=["POST"])
def publish_draft(sid):
    """Publish a set to Shopify as DRAFT products only, never live.

    Guards, in order: already published; no design uploaded; products
    missing colours/sizes/price; negative profit; variant-limit guard.
    Body {"dry_run": true} returns the planned payloads without calling
    Shopify and without changing publish state. A real publish records
    publish_state "published_draft" and locks the artwork (design
    uploads are then rejected until the set is duplicated).
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    s = sets[sid]
    dry_run = bool(body.get("dry_run"))
    if not dry_run and s.get("publish_state") == "published_draft":
        return jsonify({
            "error": "This set is already published as a draft. "
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
    problems = profit_problems(s)
    if problems:
        return jsonify({
            "error": "Sale price is below base cost for some products. "
                     "Raise the price so profit is not negative.",
            "products": problems,
        }), 400
    summary = variant_summary(s)
    if not summary["guard_ok"]:
        return jsonify({"error": summary["message"]}), 400
    payloads = build_draft_payloads(s)
    if dry_run:
        return jsonify({
            "dry_run": True,
            "grouping": s.get("grouping", "combine"),
            "variant_summary": summary,
            "products": payloads,
            "note": "Nothing was created in Shopify. This is a preview only.",
        })
    if not shopify_api.authenticated():
        return jsonify({
            "error": "Shopify is not connected. "
                     "Open /auth/shopify and approve the app first."
        }), 503
    s["publish_state"] = "launching"
    save_sets(sets)
    created = []
    try:
        for payload in payloads:
            created.append(shopify_api.create_draft_product(
                title=payload["title"],
                description=payload["description"],
                tags=payload["tags"],
                options=payload["options"],
                variants=payload["variants"],
                images=payload["images"],
            ))
    except RuntimeError as exc:
        s["publish_state"] = "failed"
        s["publish_error"] = str(exc)
        save_sets(sets)
        return jsonify({"error": str(exc)}), 502
    s["publish_state"] = "published_draft"
    s["publish_error"] = None
    s["artwork_locked"] = True
    s["publish_record"] = {
        "mode": s.get("grouping", "combine"),
        "shopify_ids": [c.get("id") for c in created],
        "images_included": bool(payloads and payloads[0].get("images")),
    }
    save_sets(sets)
    return jsonify({
        "published": True,
        "state": "published_draft",
        "shopify_ids": s["publish_record"]["shopify_ids"],
    })


@app.route("/api/sets/<sid>/upload", methods=["POST"])
def upload_design(sid):
    """Upload + validate a design. Rejects non-transparent files.

    After a real draft publish the artwork is locked and uploads
    return 409 (duplicate the set to change the design).
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
    sets[sid]["design_url"] = url
    # Artwork spec line data for the editor (dimensions + est. DPI).
    sets[sid]["design_width"] = result.get("width")
    sets[sid]["design_height"] = result.get("height")
    sets[sid]["design_dpi"] = result.get("dpi_estimate")
    sets[sid]["design_warnings"] = result.get("warnings", [])
    save_sets(sets)
    return jsonify({"path": path, "url": url, "validation": result})


@app.route("/api/sets/<sid>/mockups", methods=["POST"])
def make_mockups(sid):
    """Body: {design: path, photos: {product_id: photo_path}}.

    Renders each product with its effective placement (master or
    override), skipping the design for products that hide it, and
    compositing each product's visible text layers on top. Paths may
    be local files, /static/... URLs (resolved to the server static
    dir), or http(s) URLs (downloaded first, e.g. catalog images).
    Rendered mockup URLs are stored on the product entries so the hero
    picker and the draft publish can use them.
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404

    def resolve(path):
        if not path:
            return path
        if path.startswith("/static/"):
            return os.path.join(BASE, "server", path.lstrip("/"))
        if path.startswith("http://") or path.startswith("https://"):
            import hashlib
            name = hashlib.md5(path.encode("utf-8")).hexdigest() + ".jpg"
            local = os.path.join(UPLOAD_DIR, "_photo_" + name)
            if not os.path.exists(local):
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                r = requests.get(path, timeout=30)
                r.raise_for_status()
                with open(local, "wb") as fh:
                    fh.write(r.content)
            return local
        return path

    try:
        design_path = resolve(body["design"])
        photos = {pid: resolve(p) for pid, p in body.get("photos", {}).items()}
    except Exception:
        return jsonify({"error": "Could not load a design or product photo."}), 400
    os.makedirs(MOCKUP_DIR, exist_ok=True)
    urls = {}
    for p in sets[sid]["products"]:
        pid = p["product_id"]
        photo = photos.get(pid)
        if not photo:
            continue
        out = os.path.join(MOCKUP_DIR, f"{sid}_{pid}.jpg")
        design = None if p.get("hide_design") else design_path
        composite_layers(
            photo, design, effective_placement(sets[sid], pid),
            visible_layer_pngs(sets[sid], p), out,
        )
        urls[pid] = "/static/mockups/" + os.path.basename(out)
    for pid, url in urls.items():
        p = find_product(sets[sid], pid)
        if p is not None:
            p["mockups"] = [url]
            if not p.get("hero_image"):
                p["hero_image"] = url
    save_sets(sets)
    return jsonify({"mockups": urls})


@app.route("/api/catalog/templates", methods=["GET"])
def list_catalog_templates():
    """The 3 catalog templates available to add to any set."""
    return jsonify([{
        "product_id": t["product_id"],
        "brand": t["brand"],
        "title": t["title"],
        "colours": t["colours"],
        "sizes": t["sizes"],
        "images": t["images"],
    } for t in TEMPLATES])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
