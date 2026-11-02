"""Shopify wiring via the Dev Dashboard OAuth flow (no static token).

App: set-app-1 in the Shopify Dev Dashboard, installed on the store in
SHOPIFY_SHOP_DOMAIN. The app fetches its own Admin API access token
through the standard authorization-code flow and stores it server-side.
No token, client secret, or credential value is ever committed, logged,
or printed by this module.

Env:
  SHOPIFY_SHOP_DOMAIN  store domain, e.g. b2uus8-mt.myshopify.com
                       (SHOP_DOMAIN is also read, as a fallback for the
                       pre-OAuth scaffold)
  SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET  Dev Dashboard app credentials
  APP_PUBLIC_URL       deployed app URL (RENDER_EXTERNAL_URL is used as a
                       fallback on Render, else the request URL is used)
  SHOPIFY_TOKEN_FILE   optional override for where the token is kept
  SHOPIFY_ACCESS_TOKEN optional: if set, it is used directly, e.g. pasted
                       into Render env vars for deploy-persistent auth
  SHOPIFY_ADMIN_TOKEN  deprecated fallback, pre-OAuth scaffold

Flow:
  1. Merchant opens /auth/shopify -> redirected to
     https://{shop}.myshopify.com/admin/oauth/authorize with client_id,
     scopes and redirect_uri. A random state value is kept in the session.
  2. Shopify redirects back to /auth/shopify/callback with a code. The
     callback validates state + HMAC, exchanges the code at
     /admin/oauth/access_token with the client secret, and stores the
     resulting token in a file (0600, gitignored) outside the repo.
  3. API calls use the stored token.

Scopes (as installed for set-app-1): read_products, write_products,
read_content, write_content, read_product_listings, write_product_listings.
"""

import hashlib
import hmac as hmac_mod
import json
import os
import re

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCOPES = (
    "read_products,write_products,read_content,write_content,"
    "read_product_listings,write_product_listings"
)
REQUIRED_SCOPES = {"write_products", "write_content", "write_product_listings"}  # write implies read in Shopify

API_VERSION = "2025-07"


def shop_domain():
    shop = os.environ.get("SHOPIFY_SHOP_DOMAIN") or os.environ.get("SHOP_DOMAIN", "")
    shop = shop.strip().lower()
    for prefix in ("https://", "http://"):
        if shop.startswith(prefix):
            shop = shop[len(prefix):]
    return shop.rstrip("/")


def client_id():
    return os.environ.get("SHOPIFY_CLIENT_ID", "").strip()


def client_secret():
    return os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()


def public_url():
    url = (
        os.environ.get("APP_PUBLIC_URL")
        or os.environ.get("RENDER_EXTERNAL_URL", "")
    ).strip()
    return url.rstrip("/")


def token_file():
    return os.environ.get(
        "SHOPIFY_TOKEN_FILE",
        os.path.join(BASE, "data", ".shopify_token.json"),
    )


def configured():
    """True when an OAuth login can be started (shop + app credentials)."""
    return bool(shop_domain() and client_id() and client_secret())


def _read_token_file():
    try:
        with open(token_file()) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    token = data.get("access_token")
    if not token:
        return None
    # Never reuse a token saved for a different shop.
    saved_shop = (data.get("shop") or "").strip().lower()
    shop = shop_domain()
    if shop and saved_shop and saved_shop != shop:
        return None
    return token


def get_token():
    """Usable access token, or None when the app is not authenticated."""
    for env_name in ("SHOPIFY_ACCESS_TOKEN", "SHOPIFY_ADMIN_TOKEN"):
        token = os.environ.get(env_name, "").strip()
        if token:
            return token
    return _read_token_file()


def save_token(token, shop=None):
    """Store the token server-side in a 0600 file. Never logs the token."""
    path = token_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"shop": shop or shop_domain(), "access_token": token}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(data).encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def authenticated():
    return get_token() is not None


def status():
    """Connection state for the UI. Never includes the token."""
    return {
        "configured": configured(),
        "authenticated": authenticated(),
        "shop": shop_domain() or None,
    }


def redirect_uri(request_root=""):
    """Exact callback URL registered in the Dev Dashboard app."""
    base = public_url() or (request_root or "").rstrip("/")
    if not base:
        return ""
    return base + "/auth/shopify/callback"


def authorize_url(shop, uri, state):
    params = {
        "client_id": client_id(),
        "scope": SCOPES,
        "redirect_uri": uri,
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(v, safe='')}" for k, v in params.items())
    return f"https://{shop}/admin/oauth/authorize?{query}"


def validate_hmac(params, secret):
    """Validate Shopify's redirect HMAC (query-string method).

    params: mapping of the callback query string (single values).
    Returns True only when the HMAC matches. Never logs anything.
    """
    received = params.get("hmac", "")
    if not received or not secret:
        return False
    filtered = {k: v for k, v in params.items() if k not in ("hmac", "signature")}

    def esc(value):
        return str(value).replace("%", "%25").replace("&", "%26")

    message = "&".join(f"{esc(k)}={esc(v)}" for k, v in sorted(filtered.items()))
    digest = hmac_mod.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac_mod.compare_digest(digest, received)


def exchange_code(shop, code):
    """Exchange an authorization code for an access token.

    Raises RuntimeError on failure. The error never includes the token
    or the response body, only the HTTP status.
    """
    r = requests.post(
        f"https://{shop}/admin/oauth/access_token",
        json={
            "client_id": client_id(),
            "client_secret": client_secret(),
            "code": code,
        },
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Shopify token exchange failed (HTTP {r.status_code})")
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Shopify token exchange returned no access token")
    granted = data.get("scope")
    if granted:
        granted_set = {s.strip() for s in str(granted).split(",") if s.strip()}
        missing = REQUIRED_SCOPES - granted_set
        if missing:
            raise RuntimeError(
                "Shopify token is missing required scopes: " + ",".join(sorted(missing))
            )
    return token


def _headers():
    token = get_token()
    if not token:
        raise RuntimeError(
            "Shopify is not authenticated. Open /auth/shopify and approve "
            "the app in Shopify admin first."
        )
    return {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}


def _api(path):
    return f"https://{shop_domain()}/admin/api/{API_VERSION}{path}"


def create_product(title, product_type="", vendor="Fans Fit"):
    r = requests.post(
        _api("/products.json"),
        headers=_headers(),
        json={"product": {"title": title, "product_type": product_type, "vendor": vendor}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["product"]


def attach_image_by_url(product_id, image_url, position=1):
    r = requests.post(
        _api(f"/products/{product_id}/images.json"),
        headers=_headers(),
        json={"image": {"src": image_url, "position": position}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["image"]


def search_products(query, limit=20):
    """Search Shopify products by title, server-side.

    Returns ONLY id (numeric string), title, price (first variant) and
    featured image URL. The access token is used in the request header
    only and never appears in the returned data, logs or errors.
    Raises RuntimeError when Shopify is not authenticated or the
    search fails; error messages carry the HTTP status only.
    """
    term = re.sub(r'[*"\\]', "", (query or "")).strip()
    if len(term) < 2:
        return []
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))
    gql = """
      query ($q: String!, $n: Int!) {
        products(first: $n, query: $q) {
          edges { node {
            id
            title
            featuredImage { url }
            variants(first: 1) { edges { node { price } } }
          } }
        }
      }
    """
    r = requests.post(
        _api("/graphql.json"),
        headers=_headers(),
        json={"query": gql, "variables": {"q": f"title:*{term}*", "n": limit}},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Shopify product search failed (HTTP {r.status_code})")
    data = r.json()
    if data.get("errors"):
        raise RuntimeError("Shopify product search failed")
    results = []
    for edge in data.get("data", {}).get("products", {}).get("edges", []):
        node = edge.get("node", {}) or {}
        gid = node.get("id", "") or ""
        pid = gid.rsplit("/", 1)[-1] if gid else ""
        if not pid:
            continue
        variant_edges = (node.get("variants") or {}).get("edges", []) or []
        price = None
        if variant_edges:
            price = (variant_edges[0].get("node") or {}).get("price")
        image = (node.get("featuredImage") or {}).get("url")
        results.append(
            {
                "id": pid,
                "title": node.get("title", ""),
                "price": price,
                "image": image,
            }
        )
    return results


def get_product_image(product_id):
    """Featured image URL for one Shopify product, or None.

    GraphQL lookup by product id (same pattern as search_products).
    Returns ONLY the image URL. Raises RuntimeError when Shopify is
    not authenticated or the lookup fails; the caller turns that into
    an honest "no photo" answer, never a fabricated image.
    """
    pid = re.sub(r"\D", "", str(product_id or ""))
    if not pid:
        return None
    gql = """
      query ($id: ID!) {
        product(id: $id) { featuredImage { url } }
      }
    """
    r = requests.post(
        _api("/graphql.json"),
        headers=_headers(),
        json={"query": gql,
              "variables": {"id": f"gid://shopify/Product/{pid}"}},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"Shopify product lookup failed (HTTP {r.status_code})")
    data = r.json()
    if data.get("errors"):
        raise RuntimeError("Shopify product lookup failed")
    node = (data.get("data") or {}).get("product") or {}
    return (node.get("featuredImage") or {}).get("url")


def create_draft_product(title, description="", tags=None, options=None,
                         variants=None, images=None):
    """Create a product in DRAFT status only. Never live.

    title: product title (max 255 chars, enforced by the caller).
    description: HTML/text body for the listing.
    tags: list of tag strings (sent comma-separated).
    options: list of {"name": ..., "values": [...]} (e.g. Color, Size).
    variants: list of {"option1": ..., "option2": ..., "price": ...,
        "compare_at_price": ...} (compare_at_price optional, omitted
        when empty).
    images: list of image URLs (mockups rendered by this app).
    Returns the created product dict. Raises RuntimeError with the
    HTTP status only on failure; the token never appears in errors.
    """
    product = {
        "title": title,
        "status": "draft",
        "body_html": description or "",
        "tags": ", ".join(tags or []),
    }
    if options:
        product["options"] = options
    if variants:
        product["variants"] = variants
    if images:
        product["images"] = [{"src": url, "position": i + 1}
                             for i, url in enumerate(images)]
    try:
        r = requests.post(
            _api("/products.json"),
            headers=_headers(),
            json={"product": product},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Shopify draft create failed ({exc})")
    if r.status_code not in (200, 201):
        raise RuntimeError(
            f"Shopify draft create failed (HTTP {r.status_code})"
        )
    return r.json().get("product", {})
