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

## Build order
1. Mockup engine (placement math + compositing) – proven with a test.
2. Set CRUD + master/unlock data model (JSON store for v1).
3. Mobile UI shell (create set, upload, place, unlock, publish).
4. Shopify wiring (product create/duplicate, image attach, set page).
5. Deploy + install (token, hosting) + one real test set with Srity.
