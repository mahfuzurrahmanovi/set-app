# Gearlaunch-style flow — plan (2026-11-03)

Owner: Ovi. App: standalone Shopify set app, Fans Fit. Rule from Ovi
2026-11-03: build the FULL Gearlaunch-style flow, EXACT same experience
as the 5 screenshots in `gearlaunch-reference-20261103/`, with ONE
deliberate removal: NO live profit, because Shopify already has profit.

## 1. Brainstorm — what the screenshots actually are

1. Campaigns list (`20-38`): Create campaign, date tabs, filter by
   name/path/tags, bulk Activate / Deactivate / Delete / Tag, table
   ART NAME PATH TAGS PROFIT ORDERS ITEMS STATUS FULFILLMENT END.
   Rows: GOLDEN STATE OF /mind ACTIVE, WIN THE DAY /win INACTIVE,
   ANAHEIM /anaheim LOCKED, all fulfillment LAUNCH_END, END mostly
   blank, one 3/1/26. Profit column is shown as "-" in every row.
2. Campaign settings (`20-40`): GOLDEN STATE OF, ACTIVE, URL
   fansfit.shop/mind, tags, Delete campaign, Storefront (add to
   homepage), Conversion tools (countdown timer on, hide # purchases
   off, fudge factor 30), Cloak & Dagger (hide from search engines
   off, social buttons on), Upsells (discount 2.00), TikTok Pixel,
   Snapchat Pixel, Override default pixels (New Facebook pixel:
   Custom Audience, Conversions API token; Old Facebook pixels: Key
   Page View, Add to Cart, Checkout), Description with the
   "How To Order:" pattern.
3. Designer (`20-43` x2): GOLDEN STATE OF, FRONT / BACK tabs, large
   mockup with dashed placement box, Remove Artwork, artwork
   5120x4215 @ 457 DPI, Product Details, PRODUCTS (14) with Refresh +
   Add products. Per product: thumbnail, price $, unit cost, profit
   per unit, Position Front/Back, Pick colors swatches, Default color.
   The 14: crewneck tees, short sleeve tees, V-necks, hoodies, fleece
   sweatshirts, 11 oz Ceramic Mug, Mesh Trucker Hat, kids tees.
4. Pick colors modal (`20-44`): Unisex Classic Premium Crewneck Tee,
   Available colors grid with ticks, Select All, Selected colors as
   removable chips, Default: Deep Teal, Cancel / Save.

## 2. Scope map — screenshot element -> app element

| Screenshot element | App today | New work |
|---|---|---|
| Campaigns list, Create campaign | Set list (tap to open) + Create set at bottom | NEW campaigns home view: Create campaign, filter by name/path/tags, checkboxes, bulk Activate/Deactivate/Delete/Tag, row per campaign with ART, NAME, PATH, TAGS, ORDERS, ITEMS, STATUS, FULFILLMENT, END. PROFIT column deliberately omitted everywhere. |
| Status ACTIVE/INACTIVE/LOCKED | publish_state draft/published_draft/failed | NEW campaign.status: draft/active/inactive/locked. Draft = not yet activated. Locked = artwork locked after a draft publish (read-only status, cannot be activated by bulk). publish_state is kept separate and unchanged. |
| Fulfillment LAUNCH_END | none | Stored label, default "LAUNCH_END", shown only. It is NOT a real fulfillment mode: the app never fulfills, Ovi does manually. |
| END date | none | Optional campaign.end_date text field (e.g. 3/1/26), shown in list, "-" when blank. |
| Campaign settings: name, URL path, tags, description | Details card (name, slug, description, tags, grouping) | Settings page/card reuses those fields, adds the Gearlaunch blocks below, saves through one new endpoint. Slug is the URL path; preview shown as fansfit.shop/<slug> style. |
| Storefront homepage toggle | none | NEW campaign.storefront_homepage bool. Stored only; it does NOT change the live storefront (no live publish from this app). |
| Countdown timer + fudge factor, hide # purchases | Oregon campaign page has a countdown in theme code, not in the app | NEW campaign.show_countdown bool, fudge_factor int (0..10000, default 0), hide_purchases bool. Stored; fed into the hidden set-page body as data attributes/text only when a page is created (page stays hidden, published_at null). |
| Cloak & Dagger: hide from search engines, social buttons | none | NEW campaign.hide_from_search_engines bool, social_buttons bool. Stored only; hide-from-search-engines is honoured in the hidden set-page body as a noindex meta comment only, never by publishing anything live. |
| Upsell discount | none | NEW campaign.upsell_discount number >= 0 or null. Stored only; no checkout change in this app. |
| TikTok / Snapchat / Facebook pixels | none | NEW campaign pixel fields, all plain strings (max 255): tiktok_pixel, snapchat_pixel, facebook.custom_audience, facebook.conversions_api_token, facebook.page_view_pixel, facebook.add_to_cart_pixel, facebook.checkout_pixel. Stored only. Pixel IDs are config, not secrets of the app; the app password and Shopify token are never stored in a set and never returned in campaign responses beyond what the UI already holds. |
| Description + How To Order pattern | description field | NEW "Use How To Order text" button fills the pattern: Select Product Color/Size, Click "Add To Cart", Click "Secure Checkout" and Enter Shipping & Billing Information, 100% Printed and Made in the USA - Shipping Worldwide, 100% Secure Checkout experience. |
| Designer: FRONT/BACK, dashed box, artwork size/DPI, Remove Artwork, Product Details | already exists (tabs, dashed box, artwork spec, remove design) | Keep. BACK stays an honest placeholder: FRONT is the working side, as today. |
| PRODUCTS (n), Refresh, Add products | PRODUCTS header, Add products scrolls to picker, per-product Refresh inside details | Header gains a visible Refresh (selected product) next to Add products; per-product Refresh kept. No new Shopify calls beyond the existing refresh. |
| Product card: thumbnail, price, Position Front/Back, Pick colors swatches, Default color | thumb, price line (sale or store range), swatches, default color line; NO per-product position radio | NEW product.position field ("front"/"back", default "front") with Front/Back radios on the card and a new position endpoint. Selecting Back stores the choice and shows the existing back-side note; it does not change the mockup, because back printing is not built. |
| Many product types (14 in the example) | Picker adds any Shopify product; catalog has 3 templates; Oregon set has 3 | NO hardcoding of 14 products and NO invented prices/costs. A set may hold any number of products via the existing picker (store) or catalog templates. The 14-product breadth is proven in tests by seeding 14 products, not by inventing listings. |
| Pick colors modal: Select All, available grid with ticks, selected chips, Default, Cancel/Save | Pick colors is a <details> with checkboxes + default dropdown | NEW modal overlay (phone-width, scrollable): available grid with ticks, Select All, selected chips with x, Default color select, Cancel/Save. Save posts colours + default to a new endpoint. Sizes and price inputs move to a "Sizes + price" details block so nothing is lost. |
| Price field per product | sale price input, compare-at, base cost input | Keep sale/compare-at/base-cost inputs. Base cost stays a PLAIN cost input only. It is NOT sent to Shopify today (payloads carry price/compare-at only) and this build does not invent a cost sync; the field is kept for the seller's records and for future Shopify cost entry. |
| Profit per unit, live profit, negative-profit publish block | designer profit line, publish checklist profit, publish blocks on negative profit | DELIBERATELY REMOVED (Ovi 2026-11-03, Shopify already has profit): profitOf() and profit lines removed from the UI, profit key removed from the publish checklist, negative-profit publish guard removed. This SUPERSEDES the round-3 profit guard; the two old tests that asserted it are updated to assert the new behaviour (see section 5). The 100-variant guard, stale-mockup block, draft-only publish and all other guards stay. |

## 3. Data model changes (extend only, never rename/remove keys)

Set gains `campaign` (dict, defaults applied on read for old sets):
```json
{
  "status": "draft",
  "fulfillment": "LAUNCH_END",
  "end_date": null,
  "storefront_homepage": false,
  "show_countdown": false,
  "fudge_factor": 0,
  "hide_purchases": false,
  "hide_from_search_engines": false,
  "social_buttons": false,
  "upsell_discount": null,
  "tiktok_pixel": "",
  "snapchat_pixel": "",
  "facebook": {
    "custom_audience": "", "conversions_api_token": "",
    "page_view_pixel": "", "add_to_cart_pixel": "",
    "checkout_pixel": ""
  }
}
```
Product gains `position`: "front" (default) or "back".
Top-level name/slug/tags/description already exist and are the
campaign's name/path/tags/description; settings save writes both the
top-level fields and `campaign`.

## 4. New / changed endpoints

- GET /api/campaigns?q=&status= — summary list, filtered client-side
  semantics on the server: q matches name, slug, or any tag
  (case-insensitive substring). Fields: id, name, slug, path
  ("/"+slug), tags, art_url (design_url or first product image or
  null), orders (null, shown as "-": the app tracks no orders),
  items (product count), status, fulfillment, end (end_date or null).
  NO profit field in the response.
- POST /api/campaigns {name, slug?, tags?} — creates a set with
  campaign defaults, 201. Name required, slug validated like today.
- POST /api/sets/bulk-campaign {action, ids, tag?} — action in
  activate/deactivate/delete/tag. Locked campaigns are skipped by
  activate/deactivate and reported. Tag appends (deduped). Delete
  removes sets and cleans orphan files only after removal.
- GET /api/sets/<sid>/campaign — merged settings view (top-level
  name/slug/tags/description + campaign + url preview).
- POST /api/sets/<sid>/campaign — validate-then-save settings:
  name <=255, slug regex, fudge_factor int 0..10000, upsell_discount
  Decimal >=0, pixel strings <=255, booleans must be booleans,
  end_date <=20 chars. Stamps draft_saved_at, one atomic save.
- POST /api/sets/<sid>/products/<pid>/position {position} —
  front|back only, 400 otherwise.
- POST /api/sets/<sid>/products/<pid>/colors {colours, default_color?}
  — colours must be a subset of all_colours (fallback: current
  colours list); default_color, when given, must be in colours and
  moves to the front (existing default-color behaviour). One save.
- Changed: POST /api/sets/<sid>/publish-draft — negative-profit guard
  removed; checklist no longer returns a profit key and readiness no
  longer requires base_cost or non-negative profit. Variant guard,
  stale-mockup block, draft verification and resume stay.

## 5. Tests (new suite server/gearlaunch_flow_test.py, test-first)

1. Campaigns list: create 2 campaigns, list returns both with all
   columns above, orders null, no "profit" substring in the JSON.
2. Filter: q matches name, path (slug), and tag; non-matching hidden.
3. Bulk: activate, deactivate, tag (deduped), delete; locked skipped.
4. Settings save/load round-trip for every field above; invalid slug,
   fudge_factor, upsell_discount, and non-boolean toggle rejected
   with 400 and nothing saved.
5. Settings persist across a fresh load_sets() (disk round-trip).
6. Designer breadth: a seeded set with 14 products lists 14, each
   with title, price source (sale or store range), position default
   front, swatches/default color data.
7. Position endpoint: front/back saved, other values 400.
8. Pick colors: save colours subset + default, Select-All equivalent
   (all all_colours) saved, default moves to front, colours outside
   all_colours rejected.
9. No profit: index.html has no "Profit:" text, no profitOf function,
   no "negative profit" text; dry-run checklist has no profit key;
   a dry-run with sale price below base cost SUCCEEDS (no profit
   block) while still passing the variant guard.
10. Guards intact: combine set with 184 priced variants is still
    blocked by the 100-variant guard; split 88/48/48 passes the guard.
11. Oregon safety: real data/sets.json byte-identical before/after;
    all suites run on temp roots with mock Shopify clients only.
12. UI markers: campaigns card, settings card, pick-colors modal,
    FRONT/BACK tabs, Refresh + Add products header buttons present;
    editor JS passes node --check.

Updated old tests (spec change, not a regression): rebuild_test.py
"negative profit blocks dry-run" and rebuild2_test.py "negative
profit still blocks dry-run" become "price below base cost does NOT
block dry-run (profit removed, Shopify owns profit)". Any other suite
asserting a profit key in the checklist is updated the same way and
the change is recorded in gearlaunch-flow-test-log.md.

## 6. UI layout (mobile-first)

Campaigns view replaces the old "Open a set" card at the top: search
input, Create campaign (name input + button), bulk buttons, then one
row-card per campaign (checkbox, art thumb, name, path, tags, items,
status pill, fulfillment, end, Open / Settings / Duplicate / Delete).
On a phone this is a stacked list, not a 9-column table: the same
information, in phone order. Settings is a new card shown for the open
set, with the Gearlaunch blocks in order: Details, Storefront,
Conversion tools, Cloak & Dagger, Upsells, TikTok Pixel, Snapchat
Pixel, Facebook pixels, Description. Designer keeps the existing
two-column editor collapsing to one column under 900px; the pick
colors modal is fixed, full phone width, scrollable, with a dim
backdrop and Cancel/Save at the bottom. Every input keeps the
existing 17px / 12px touch sizing.

## 7. Deliberately NOT built

- Live profit anywhere (Ovi's removal).
- Live storefront publish: campaign pages stay hidden/draft-only and
  tap-gated, as today. Storefront homepage, countdown, hide-purchases,
  cloak, social buttons, upsell and pixels are stored settings, not
  live store changes.
- Real fulfillment, orders, or order stats: ORDERS shows "-" because
  the app has no orders. No Cat Kiss Fish connection, no order
  automation.
- Back-side printing: position radio is stored, back rendering is not
  built; the UI says so honestly.
- Invented products, prices, or unit costs for the 14-product example.
- Any password/token/secret in code, logs, or tests. Tests use a
  test-only password and temp roots.
- GitHub push / Render deploy from this build: the local copy is not
  a git repo, so deploy is a separate, documented step (see deploy
  note in the final report).
