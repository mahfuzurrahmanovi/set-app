# Set App (Fans Fit)

Standalone mobile-first app for product sets. Srity runs everything here
from her phone. No Cat Kiss Fish connection. Ovi fulfills manually after
sales. See SPEC.md for the full spec.

## Run locally
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd server && ../.venv/bin/python app.py
```
Open http://localhost:5000 on the phone (same network) or via a tunnel.

## App password + storage (fix round 3)
```
export SET_APP_PASSWORD=<chosen password>   # unset = open mode with a warning
export SETAPP_DATA_ROOT=/var/setapp-data    # persistent disk on Render; default is ./data
export FLASK_SECRET_KEY=<random secret>     # session signing; set it in production
```
Without `SETAPP_DATA_ROOT` on a persistent disk, every Render redeploy
wipes sets, uploads, mockups and the Shopify token file.

## Tests
```
.venv/bin/python server/fix3_test.py     # fix round 3: 84 checks
.venv/bin/python server/rebuild_test.py  # round 1: 45 checks
.venv/bin/python server/rebuild2_test.py # round 2: 49 checks
.venv/bin/python server/fix_test.py      # fix 2.1: 24 checks
```
All suites run against temp data roots and mock Shopify clients; none
touches the live store or the real `data/sets.json` (byte-identity is
asserted inside the suites). Full evidence: `fix3-test-log.md`.

## Configure Shopify (Dev Dashboard OAuth, at install time only)
The app is set-app-1 in the Shopify Dev Dashboard, already installed on
b2uus8-mt.myshopify.com. It fetches its own Admin API token via OAuth;
no static token is stored anywhere.
```
export SHOPIFY_SHOP_DOMAIN=b2uus8-mt.myshopify.com
export SHOPIFY_CLIENT_ID=<client ID from the Dev Dashboard app>
export SHOPIFY_CLIENT_SECRET=<client secret from the Dev Dashboard app>
export APP_PUBLIC_URL=<deployed app URL>
```
Start the app, open /auth/shopify, and approve the app in Shopify admin.
The token is stored in data/.shopify_token.json (gitignored, never
committed). On Render, set the same variables in the dashboard
(client secret via render.yaml sync: false, entered by hand) and add
https://<app-url>/auth/shopify/callback to the Dev Dashboard app's
allowed redirect URLs. After a redeploy the token file is lost, so run
/auth/shopify once again.

## Deploy
Needs stable hosting with a public URL (Fly.io / Render / VPS class).
Hosting choice confirmed with Ovi before any spend.
