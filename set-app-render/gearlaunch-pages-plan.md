# Gearlaunch separate pages — plan (2026-11-03)

## Problem, owned plainly
The 2026-11-03 Gearlaunch build (commit 7913ccd, live on Render) stacked
Campaigns, Campaign settings, Designer, upload, placement, picker,
catalog and variants into one scrolling `index.html`. Ovi (21:28 Dhaka)
said he cannot understand anything and it is not user friendly. He
wants the EXACT Gearlaunch pages, exact format, as separate pages.

## Scope change, 21:30 Dhaka (supersedes draft-only)
Publish is now DIRECT publish, not draft only. Tapping Publish in the
designer creates live/active Shopify products immediately, with no
draft review step. This plan, the code and the tests all reflect that.
Testing and verification use mock Shopify clients only and NEVER
publish anything live to the real store.

## Page map — Gearlaunch screenshot element -> exact page/route -> template
Reference screenshots: `gearlaunch-reference-20261103/` (5 files).

### 1. Campaigns list — GET /campaigns — templates/campaigns.html
Gearlaunch "Campaigns" page (screenshot 20:38), minus PROFIT (Ovi:
Shopify already has profit, so no profit column, no profit calc).
- Header: "Campaigns", "Create campaign" button.
- Filter: "Filter by name, path, tags" (client-side, same fields as before).
- Bulk: Activate / Deactivate / Delete / Tag, with row checkboxes.
- Table, Gearlaunch column order exactly:
  ART | NAME | PATH | TAGS | ORDERS | ITEMS | STATUS | FULFILLMENT | END
  Orders is "-" (app tracks no orders). Items = product count.
  Status pill: DRAFT / ACTIVE / INACTIVE / LOCKED.
  Fulfillment: LAUNCH_END. End: campaign end_date or "-".
- On a phone the table scrolls horizontally
  (`.tableWrap { overflow-x: auto; }`), NOT stacked cards. This is a
  deliberate exception to the earlier stacked-mobile invention:
  "exact format" outranks it for this table.
- Clicking a campaign NAME goes to its settings page
  `/campaigns/<id>`. A "Designer" link in the name cell goes to
  `/campaigns/<id>/designer`. Create campaign redirects to the new
  campaign's settings page.
- NOTHING else on this page: no designer, no settings cards, no
  upload, no products, no pick-colors modal.

### 2. Campaign settings — GET /campaigns/<id> — templates/campaign_settings.html
Gearlaunch campaign settings page (screenshot 20:40), in card order:
- Header: campaign name + status pill + "Designer" button +
  "Delete campaign" button. Top nav back to Campaigns.
- Details: Name, URL path `fansfit.shop/<slug>`, Tags.
- Storefront: Add campaign to storefront homepage.
- Conversion tools: Display countdown timer, Hide # of purchases,
  Fudge factor.
- Cloak & Dagger: Hide from search engines, Social buttons on
  campaign landing page.
- Upsells: Upsell discount.
- Tik Tok Pixel. Snapchat Pixel.
- Override default pixels: New Facebook pixel (Custom Audience,
  Conversions API access token); Old Facebook pixels (Key Page View,
  Add to Cart, Checkout).
- Description, with "Use How To Order text" button.
- Save campaign settings button. Save uses the existing
  POST /api/sets/<id>/campaign endpoint (validated one-save).
- NOTHING else: no campaigns table, no designer mockup, no PRODUCTS
  list, no upload, no pick-colors modal. Set details (name/slug/tags/
  description) live here now, not on the designer page; grouping
  (combine/split) lives on the designer page under Variants, because
  that is where the variant guard is shown.

### 3. Designer — GET /campaigns/<id>/designer — templates/designer.html
Gearlaunch designer page (screenshots 20:43, 20:44), in order:
- Header: campaign name + status, nav back to Campaigns and to
  Campaign settings, Save button, Publish button (see direct publish).
- Design: FRONT / BACK tabs, large mockup with dashed placement box,
  Remove Artwork, Product Details (artwork dimensions + DPI, colours
  front/back), tap-to-place note, Back note (BACK is not printed yet).
- Layers: text layers list + add/edit form (existing tool).
- PRODUCTS list: header PRODUCTS (n), Refresh + Add products buttons,
  each product card with thumbnail, price fields, base cost as a plain
  input (NO profit, no profit calculation, no profit guard), Front/Back
  position, Pick colors swatches, Default color, per-product placement
  sliders, mockups + hero, lock/unlock.
- Pick colors modal, ONLY here: Select All, available colors grid
  with ticks, selected colors as removable chips, Default color,
  Cancel / Save.
- Upload design (bulk: first file replaces, extras duplicate sets).
- Master placement sliders + aids.
- Add products: search picker + add by product ID.
- Catalog products: Printify catalog templates.
- Variants and publish: variant counts + 100-variant guard message,
  grouping combine/split buttons, Preview what will be published
  (dry run, no changes), Publish button, hidden set-page create
  (tap-gated; the Page itself stays hidden, published_at null — that
  is a Shopify Page, not the product publish, and it stays gated).
- NOTHING else: no campaigns table, no campaign-settings cards.

### Shared chrome (every page)
- Top nav: "Campaigns" link on every page; settings <-> designer
  links on those two pages. Log in card + Log out on every page
  (password gate is API-level; pages themselves show the login card
  when unauthenticated, exactly as the old single page did).
- Shared CSS: templates are static files, so CSS lives in
  `server/static/app.css` and shared JS in `server/static/app.js`,
  loaded by each page. The old single `index.html` is DELETED as the
  default page (kept only as a redirect: GET / redirects to
  /campaigns). No hidden stacked version remains as a route.

## What moves where (from index.html)
- campaignsCard + campaignsList rendering -> campaigns.html, as a
  real <table> (was stacked .campaignRow divs).
- campaignSettingsCard + Settings card name/slug/tags/description ->
  campaign_settings.html (grouping moves out, to designer variants).
- editor (Design + PRODUCTS) + topbar (Save/Publish) + pickColorsModal
  + Upload + Master placement + pickerCard + Catalog + Variants and
  publish + New set (Create set stays on designer? No: "New set" is a
  campaigns action — Create campaign on /campaigns covers it; the
  old "New set" card is deleted, create goes through campaigns) ->
  designer.html.
- JS: one shared app.js, page-aware. Bottom init of the old file
  (showVals/checkAuth/loadSetList/loadCatalogTemplates on every load)
  is replaced by per-page init scripts: campaigns inits list only,
  settings inits its set only, designer inits its set + catalog only.
  Functions that touch elements absent on a page are guarded
  (el() null-checks) instead of throwing.

## Direct publish changes (21:30 scope change)
- `shopify.py`: `create_draft_product` -> `create_product` with
  `"status": "active"`. Error wording "draft create failed" -> "create
  failed". No draft-status expectation anywhere.
- `app.py`: route `/api/sets/<id>/publish-draft` -> `/api/sets/<id>/publish`,
  handler `publish_live`. publish_state "published_draft" ->
  "published". Already-published error now says "already published
  live". The Shopify status check now expects "active" and rejects
  anything else. Dry-run preview wording: "Publishing creates NEW
  live products; it does not update existing listings", checklist
  note "Nothing was created in Shopify. This is a preview only."
  (preview itself still creates nothing). Remove-product block and
  create-page gate now key on "published" instead of
  "published_draft". Save-draft / draft_saved_at stay as LOCAL set
  save timestamps (not Shopify drafts); UI "Draft saved" for a local
  save is kept, but publish UI never says draft again.
- Designer button labels: "Publish to Shopify (live)" and
  confirmation "Publish this set to Shopify as LIVE products?
  They will be visible in the store immediately." Publish status
  text: "Published live in Shopify".
- CONSEQUENCE, stated plainly for Ovi: Publish now goes live
  immediately with no draft review step. A mistaken tap publishes
  real, visible products. Preview (dry run) is the only safe check.

## API endpoints — unchanged except publish
All existing /api/* endpoints keep their paths and behaviour, except
/publish-draft -> /publish as above. This keeps existing sets, the
live data file, and the mock-client tests working with only the
publish assertions updated.

## Test list (new suite server/gearlaunch_pages_test.py, test-first)
Must FAIL before the fix (404s on the new routes, stacked markup on /)
and PASS after. Asserts:
1. GET / redirects to /campaigns (302 or 200 with campaigns table).
2. GET /campaigns (authed test client): 200, contains <table> with
   headers ART, NAME, PATH, TAGS, ORDERS, ITEMS, STATUS, FULFILLMENT,
   END in that order, contains "Create campaign", "Filter by name,
   path, tags", Activate/Deactivate/Delete/Tag; does NOT contain
   id="campaignSettingsCard", id="centreImg", id="pickColorsModal",
   or "PRODUCTS ("; table has a horizontal-scroll wrapper class.
3. GET /campaigns/<id>: 200, contains campaign name, status pill,
   "Designer", "Delete campaign", Details/Storefront/Conversion
   tools/Cloak & Dagger/Upsells/Tik Tok Pixel/Snapchat Pixel/
   Override default pixels/Description, "Use How To Order text",
   "fansfit.shop/"; does NOT contain the campaigns <table> or
   id="centreImg" or id="pickColorsModal".
4. GET /campaigns/<id>/designer: 200, contains FRONT, BACK,
   id="centreImg", "PRODUCTS", "Pick colors", id="pickColorsModal",
   "Select All", "Upload design", "Master placement", "Add products",
   "Catalog products", "Variants and publish", "Publish to Shopify
   (live)"; does NOT contain id="campaignSettingsCard" or the
   campaigns table headers as a table; does NOT contain
   "Publish as DRAFT" anywhere.
5. Navigation: every page contains a link to /campaigns; settings
   links to its designer URL; designer links to its settings URL.
6. No profit: no page contains "Profit:" or "profitOf" or
   "Profit per unit"; the only profit wording allowed is an
   explanatory "Profit is not shown" note.
7. No draft publish: no page and no publish response contains
   "Publish as DRAFT" or "published_draft" as a state; a mock live
   publish returns state "published" and the mock Shopify client
   received status "active".
8. Guards intact (mock Shopify only): combine over 100 variants
   still blocked; split passes; stale mockup blocks a real publish
   (dry-run warns); price below base cost does not block.
9. Auth: unauthenticated API calls still 401 (existing suites cover
   this); new page routes serve the login card markup when
   unauthenticated (they are static pages, API is the gate — same
   as the old single page, documented, not claimed as server-side
   gating).
10. Real data/sets.json byte-identical at the end of every suite.

## Rerun all existing suites, 0 failures allowed
gearlaunch_flow (58), fix3 (89), rebuild (45), rebuild2 (50), fix
(24), mockup OK. Updates allowed ONLY where an assertion assumed
the old single page (UI markers in gearlaunch_flow §6, publish
endpoint/state in fix3/rebuild/rebuild2) or draft-only publish.
Every update is documented in gearlaunch-pages-test-log.md.

## Review
One independent review subagent (only fan-out): regressions, auth
gating on new routes, mobile/horizontal-table behaviour, direct
publish guard (no live calls in tests, active status, publish state).
Fix what it finds, retest, then verify locally and report. Do NOT
deploy, do NOT push, do NOT touch Render, do NOT publish live.
