# Set App – SPEC (v1)

Owner: Ovi (Fans Fit, fansfitco.shop). Operator: Srity, MOBILE ONLY (no laptop/PC).
Status: build started 2026-10-30. Scope final per Ovi 2026-10-30 18:54.

## What it is
A standalone mobile-first web app for building and managing product SETS in
Shopify. It is NOT connected to Cat Kiss Fish and does NOT handle orders.
Ovi fulfills manually after sales: when an order comes in, he passes it to
Cat Kiss Fish himself. The app's job ends when the products are live in
Shopify with correct mockups.

## The gap it fills
Cat Kiss Fish cannot publish one design to many products at once. Srity
must do it product by product today. This app publishes one design to a
whole set in one go, with Printify-style mockups (Ovi prefers Printify's
mockup look).

## Reference set (template)
The Oregon Ducks Set is the app's template set, seeded 2026-10-30 from the
live store to match it exactly:
- Oregon Ducks Unisex Tee (15469998538906): 88 variants, 12 colours,
  8 sizes S-5XL, $18.88-28.88.
- Oregon Ducks Hoodie (15470002929818): 48 variants, 8 colours,
  6 sizes S-3XL, $44.
- Oregon Ducks Crewneck Sweatshirt (15470004568218): 48 variants,
  8 colours, 6 sizes S-3XL, $34.
- Set page template matches the live campaign page
  fansfitco.shop/pages/oregon-ducks-set (Style thumbnails, Colour pills,
  Size pills, quantity + black Add to cart, Shop Pay).
- Default master placement reproduces the Oregon mockup look on photos
  (badge about 31% of image width, centred chest). Srity can adjust it.
Later items and guidance from Ovi extend this template into new sets.

## Features (v1)
1. **Sets** – a set is a group of products (e.g. tee + hoodie + crewneck).
   Create a set, add/remove products, copy a whole set with a new design
   (products, colours, sizes, prices carried over).
2. **Bulk design upload** – upload one design, or many at once from the
   phone. Each design becomes / applies to a set.
3. **Master placement** – place the design ONCE on the first product
   (position x/y, size, rotation). That placement applies to every product
   in the set automatically. Fix the first, fix the rest.
4. **Unlock override** – any single product can be unlocked and adjusted
   on its own (its own x/y/size). Locked products always follow the master.
   Re-locking a product returns it to the master placement.
5. **Printify-style mockups** – the app draws the design onto each
   product's photo at the product's placement and sets the result as the
   Shopify product image. What the customer sees is a Printify-quality
   mockup, not a plain design file.
6. **Set page (single link)** – each set gets one link showing all its
   products together, like the Oregon Ducks Set campaign page
   (fansfitco.shop/pages/oregon-ducks-set). Built from the set's products.
7. **Mobile-first UI** – every screen works on a phone: big touch targets,
   upload from phone files/photos, sliders + tap-to-place for positioning,
   no computer needed, no scripts to run.

## Data model
- Set: { id, name, products: [product_id...], master_placement: {x, y, scale, angle} }
- Set product: { product_id, locked: true/false, override_placement: {x, y, scale, angle} | null }
- Placement semantics (shared by mockup engine and UI):
  x, y = centre of the design as a fraction of the product photo (0-1).
  scale = design width as a fraction of the photo width.
  angle = rotation in degrees (0 = upright).
- Effective placement for a product = override_placement if unlocked,
  else the set's master_placement.

## Shopify integration (only integration)
- Via the Dev Dashboard app set-app-1 (already installed on Fans Fit).
  The app fetches its own Admin API token through the OAuth
  authorization-code flow (client ID + client secret from env vars);
  the token is stored server-side in a gitignored file, never in code
  or chat.
- Uses Admin API to: create/duplicate products, update product details,
  attach mockup images, manage collections, and publish the set page.
- Mockup images are served from the app's own public URL and attached to
  products by URL (Shopify fetches them). Requires the app to be deployed
  on stable hosting with a public URL.

## Explicitly OUT of scope (v1)
- No Cat Kiss Fish connection, no Cat Kiss Fish API calls.
- No order import, no fulfillment, no automatic production.
- No payment handling inside the app (checkout stays on Shopify).
- No public Shopify App Store listing (custom app for Fans Fit only).

## Hosting
Render Starter web service ($7/mo, always on), chosen 2026-11-01.
Cannot live reliably on the Muse VM.

## Fix round 3 (2026-11-03, local only, not yet deployed)

Parent audit + independent ChatGPT review both found the app not
production-ready. Fix round 3 closed the gaps; full test evidence in
`fix3-test-log.md` (202 checks, 0 failed, including the older suites).

- **Login + CSRF.** Password gate (`SET_APP_PASSWORD` env, read per
  request; unset = open mode with a visible warning, never a hardcoded
  password). Every POST needs a session CSRF token; the editor fetches
  it automatically and reopens the login form on a 401.
- **Durable storage root.** `SETAPP_DATA_ROOT` env moves sets, uploads
  and mockups off the ephemeral filesystem. On Render this must point
  at a persistent disk (1 GB at `/var/setapp-data`), or redeploys keep
  wiping sets, uploads and the Shopify token.
- **Safe saves.** One Save button stores everything the editor holds
  (placement, details, colours, sizes, prices) in a single validated,
  atomic, write-locked save with a `.bak` fallback; an "Unsaved
  changes" note shows until it is saved, and switching sets with
  unsaved edits asks first.
- **Real product data.** Adding a store product fills title, colours,
  sizes and per-variant prices from the live listing (a bare ID used to
  create an empty shell); a Refresh button re-syncs one product without
  touching the seller's selections, sale price or lock.
- **Pricing.** Money uses Decimal for validation and profit math;
  compare-at must be higher than sale; publish still blocks negative
  profit. Per-variant store prices are used when no flat sale price is
  set; combine mode adds a Style option (product title) per variant.
  A product is publishable on price when it has a flat sale price or
  at least one priced pair: real listings are non-rectangular (the
  Oregon tee has 88 variants over 12 colours x 8 sizes), so unpriced
  pairs are skipped on publish and named in the dry-run warnings, not
  a blocker. The variant-limit guard counts variants that will
  actually be created, so the full Oregon set in combine mode
  (184 variants) is over Shopify's 100-per-product cap and must be
  split or trimmed; split mode (88/48/48) fits.
- **Publish safety.** Dry-run returns warnings plus a per-product
  readiness checklist and creates nothing. A real publish never gets
  stuck "launching": a failure records state "failed" with partial
  progress, and retrying resumes from the first uncreated product
  instead of duplicating. A Shopify product returned with any status
  other than draft is rejected, not counted as published. Drafts only,
  never live. After a successful draft publish the editor offers a
  hidden set-page create (published_at null, not linked anywhere).
- **Mockup freshness.** Every render stamps the current design version;
  placement, layer and master edits bump it, so an outdated render is
  flagged ("tap Preview mockup again") and blocks a real publish. A
  design re-upload clears outdated mockups. Renders only accept
  server-issued `/static/` photo URLs, never a rendered mockup or a
  private-network URL; photos are capped at 3000px wide.
- **Uploads.** Transparent PNG only, with a real transparency check
  (at least 3% of pixels must be transparent, not just transparent
  corners). Text rendering uses bundled DejaVu fonts, so it works on
  any host.
- **Editor extras.** Duplicate/delete set, layer edit/reorder/position,
  per-product placement sliders + rotation + tap-to-place, default
  colour dropdown, swatch tap toggles the colour checkbox, bulk upload
  (first file on this set, each extra file as a duplicated set),
  set export (JSON download, plus a server export endpoint), search
  capped at 50 results, JSON error responses everywhere.
- **Still not built (deliberate).** Back-side printing, full
  drag-to-place, buyer personalization, orders/fulfilment/billing/sync,
  SQLite migration, fees in profit, layer undo, multi-worker support,
  set-page theme work. First real draft publish is Ovi's to trigger;
  it has only ever been tested with a mock client and dry-run.

## Gearlaunch-style flow (2026-11-03, local only, not yet deployed)

Exact same experience as Ovi's 5 Gearlaunch screenshots, with one
deliberate removal: NO live profit anywhere, because Shopify already
has profit. Price fields stay; base cost stays a plain cost input
only, never computed into profit, and never blocks a publish. This
supersedes the round-3 negative-profit publish guard.

- **Campaigns list (home view):** Create campaign, filter by name /
  path / tags, bulk Activate / Deactivate / Delete / Tag, one row per
  campaign with art, name, path, tags, orders (-, the app tracks no
  orders), items, status (draft/active/inactive/locked), fulfillment
  (LAUNCH_END label only, not a real fulfillment mode), end date.
  On a phone the rows stack; the same columns are shown, not a
  9-column desktop table.
- **Campaign settings (per campaign):** name, URL path, tags,
  description (with a How To Order text button), storefront homepage
  toggle, countdown timer + fudge factor, hide # of purchases,
  Cloak & Dagger (hide from search engines, social buttons), upsell
  discount, TikTok / Snapchat / Facebook pixels. All stored and
  persisted on the Render disk; they feed the hidden set page as
  plain notes only. Nothing here publishes anything live.
- **Designer:** FRONT / BACK tabs, large mockup with dashed placement
  box, artwork dimensions + DPI, Remove Artwork, PRODUCTS list with
  Refresh + Add products. A set may hold any number of products via
  the existing Shopify picker (the 14-product Gearlaunch example is
  breadth, not a hardcoded list); no prices or costs are invented.
  Each product card has a thumbnail, price, Front/Back position
  radio (Back is stored; back printing is not built), Pick colors
  swatches, and Default color.
- **Pick colors modal:** Select All, available colors grid with
  ticks, selected colors as removable chips, Default color, Cancel /
  Save. Save updates that product's colours and default.
- Endpoints: GET/POST /api/campaigns, POST /api/sets/bulk-campaign,
  GET/POST /api/sets/<sid>/campaign, POST
  /api/sets/<sid>/products/<pid>/position, POST
  /api/sets/<sid>/products/<pid>/colors. Full plan:
  `gearlaunch-flow-plan.md`; tests: `gearlaunch-flow-test-log.md`
  (263 checks across suites, 0 failed). Deploy is outstanding: the
  local copy is not a git repo, so nothing was pushed to GitHub or
  Render by this build.

## Build order
1. Mockup engine (placement math + compositing) – proven with a test.
2. Set CRUD + master/unlock data model (JSON store for v1).
3. Mobile UI shell (create set, upload, place, unlock, publish).
4. Shopify wiring (product create/duplicate, image attach, set page).
5. Deploy + install (token, hosting) + one real test set with Srity.
