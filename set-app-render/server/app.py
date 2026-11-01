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
import secrets
import uuid

from flask import Flask, jsonify, redirect, request, send_from_directory, session

import shopify as shopify_api
from mockup import render_set_mockups

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


@app.route("/api/sets/<sid>/upload", methods=["POST"])
def upload_design(sid):
    if "design" not in request.files:
        return jsonify({"error": "no design file"}), 400
    f = request.files["design"]
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, f"{sid}_{uuid.uuid4().hex[:8]}_{f.filename}")
    f.save(path)
    return jsonify({"path": path, "url": "/static/uploads/" + os.path.basename(path)})


@app.route("/api/sets/<sid>/mockups", methods=["POST"])
def make_mockups(sid):
    """Body: {design: path, photos: {product_id: photo_path}}.
    Renders each product with its effective placement (master or override).
    """
    body = request.get_json(force=True) or {}
    sets = load_sets()
    if sid not in sets:
        return jsonify({"error": "set not found"}), 404
    results = render_set_mockups(
        sets[sid], body["design"], body.get("photos", {}), MOCKUP_DIR
    )
    urls = {
        pid: "/static/mockups/" + os.path.basename(p) for pid, p in results.items()
    }
    return jsonify({"mockups": urls})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
