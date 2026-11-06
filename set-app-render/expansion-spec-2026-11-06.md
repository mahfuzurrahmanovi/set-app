Superseded 2026-11-06: the Printify catalog templates were removed per Ovi; the app has no Printify connection.

# Set app 7-type expansion: specs, code changes, checklist (2026-11-06)

Status: BUILD + SPECS ONLY. Nothing deployed, nothing published to Shopify,
no Printify product created, no credentials used or needed.

Base: live code with the Part 7 fixes (commit b2f2692), as uploaded in the
second message (`app_1.py`, `catalog_1.py`, `designer_1.html`, `app_1.css`,
`app_1.js`, `mockup_1.py`, `shopify_1.py`). I diffed these against the
first-round uploads: Part 7 changed only app.py (3 spots), app.js (2 spots)
and app.css/designer.html. mockup.py, shopify.py, catalog.py were identical.

---------------------------------------------------------------------------
## 1. Files changed (complete files, same repo paths)

| File | Lines | Status |
|---|---|---|
| set-app-render/server/app.py | 2784 (live 2780) | CHANGED, 1 fix |
| set-app-render/server/catalog.py | 164 (live 149) | CHANGED, prices |
| set-app-render/server/static/design-area-templates/crewneck-front.png | 1000x666 | CLEANED (required check) |
| .../longsleeve-front.png, vneck-front.png, hoodie-front.png | 1000x666 | CLEANED (optional, same defect) |
| set-app-render/server/expansion_types_test.py | new | NEW test, 85 checks |

NOT changed, no change needed: shopify.py, mockup.py, app.js, app.css,
designer.html, campaigns.html, campaign_settings.html, text_layers.py.

### app.py (one fix, around line 2236)
Live bug found while checking the 117-variant Long Sleeve against the
publish guard: the guard was `if combine: ... else: <per-product > 100 check>`,
so GROUPED mode fell into the `else`. Any grouped set holding a product with
more than 100 variants was blocked on publish AND on Preview with the text
"Split mode: one listing per product. Over the 100-variant limit: ...".
That is both a blocker for this expansion and exactly the limit text Ovi
asked never to see in Grouped.
Fix: `else:` became `elif grouping == "split":`. Grouped now skips the
per-product check (build_product_payloads already chunks at 95). Combine and
split guards and messages are unchanged. Lines 2236 and 2245-2248.
Reproduced first: against the live app.py the new test fails with exactly
that 400 error; against the patched file it passes.

### catalog.py (default prices)
- Docstring: 4 lines about suggested prices.
- Each template gets `suggested_price` and `price_confirmed`:
  bp80 "27.00" / False (UNCONFIRMED), bp945 "29.00" / True, bp48 "29.00" / True.
- `template_entry()`: `sale_price` now starts at `template["suggested_price"]`
  instead of None, so a design-first set is publishable without typing a
  price. Still editable per product.
- Catalog titles stay generic ("Unisex Ultra Cotton Long Sleeve Tee"), because
  templates are reused for any design. The Oregon titles belong on the real
  Printify products (section 3).
- RISK: any existing test that asserts a catalog entry has `sale_price` None
  or the UI text "Selling price: not set" for a template will now fail. I did
  not have the existing suites, so Muse must run them all.

### Templates (static/design-area-templates)
Crewneck check result: no red pixels and no baked dashed box, but a faint
ghost remained in all four stripped images. The old dashes were repainted
with the wrong grey (250 on the white background, 255 on the garment, plus
small white notches where dashes crossed outlines). Contrast about 2 percent,
nearly invisible, but real. Cleaned by restoring only those pixels (about
650 to 950 per image), palette unchanged (140, 180, 240, 242, 250, 255).
Garment outline, size, no model, no pre-printed design all unchanged.
The hoodie keeps a few single-pixel specks that show only under 12x contrast.
Short-sleeve front/back were not in the second upload, so not touched.
The app's placebox (25% / 20% / 50% / 50%) remains the only dashed area.

---------------------------------------------------------------------------
## 2. Tests
New file only: `server/expansion_types_test.py` (does not overwrite anything).
Run: `python server/expansion_types_test.py` from the repo root. It uses a
temp data dir, only calls dry-run publish, never touches data/sets.json.
Result in my sandbox (live app.py/catalog.py/templates copied from the
uploads, with stub design_validation.py and text_layers.py because those two
files were not uploaded): patched files 85 passed, 0 failed. Live files:
16 failed (prices, ghost dashes, grouped guard), which are the three defects.
NOT run by me: your existing suites (scale_mockup_fix, mockup_fix,
designer_fix, gearlaunch_pages, gearlaunch_flow, fix3, rebuild, rebuild2, fix,
mockup_test, four_fixes, designer_mobile_fix, Part 7 tests). Run them all.

---------------------------------------------------------------------------
## 3. Product creation specs (ready to execute in the Printify dashboard)

Shared: design = existing Oregon badge, Printify upload id
`6a7f138ad39bbc0186ba24c9` (file 1000031662.png, 4095x4608; id taken from
the earlier build record, not re-verified). Front print only. Provider 99
Printify Choice for all three. Prices are USD (Ovi, 2026-11-06); the
store's currency app converts for viewers.

### A. Oregon Ducks Long Sleeve Tee
- Blueprint 80, "Unisex Ultra Cotton Long Sleeve Tee", Gildan, provider 99.
- Front DTG area 3033 x 3442.
- Price $27 USD (confirmed 2026-11-06).
- Variants: 76 with Ovi's 11 colours, sizes S to 5XL (all kept, his call
  2026-11-06). Colours: Ash, Black, Dark Heather, Gold, Irish Green,
  Navy, Purple, Red, Royal, Sport Grey, White. Verified live via the
  Printify CLI variants endpoint (provider 99).

### B. Oregon Ducks Classic Long Sleeve Tee
- Blueprint 2806, "Long Sleeve T-Shirt", Gildan Softstyle 64400,
  provider 99. Front DTG 4500 x 5100. Price $29 USD (confirmed
  2026-11-06). Gildan, not American Apparel (Ovi, 2026-11-06: "Gildan
  for both long sleeves"). 4.5oz ring-spun cotton, closest in feel to
  the AA 945 it replaces.
- Variants: 30 (5 colours x 6 sizes), publish all.
  Colours: Black, Navy, Royal, Sport Grey, White. Sizes S, M, L, XL,
  2XL, 3XL. Verified live via the Printify CLI variants endpoint
  (provider 99).

### C. Oregon Ducks V-Neck Tee
- Blueprint 48, "Unisex Jersey Short Sleeve V-Neck Tee", Bella+Canvas,
  provider 99. Front DTG 3461 x 3922. Price $29 USD (confirmed
  2026-11-06).
- Variants: 20 (4 colours x 5 sizes), publish all.
  Colours: Black, Navy, Red, White.
  Sizes S, M, L, XL, 2XL. Verified live via the Printify CLI variants
  endpoint (provider 99).

### Placement (Printify placeholder terms)
Start: front, x 0.5, y 0.5, scale 1, angle 0. The live hoodie needed y 0.55
and scale 0.75, so expect to adjust. Check each mockup for the badge
clear of the collar/neckline (the V-neck is the likeliest to need y lowered)
and not wider than the chest. Do not publish a mockup you have not looked at.

### Totals for the Oregon set
Existing 184 + A 76 + B 30 + C 20 = 310 variants, inside the
approx 500 target. Grouped mode chunks them in the app; no app change needed.

---------------------------------------------------------------------------
## 4. Execution checklist (Muse, in this order)
1. Run all existing suites plus `expansion_types_test.py` on the patched files.
2. Diff app.py and catalog.py against live (small diffs above). Do not deploy
   until Ovi confirms the decisions in section 5 and Muse sees all green.
3. Printify dashboard (CLI publish is broken, HTTP 400 code 8150): create the
   three products from section 3 with the Oregon badge, provider 99, titles and
   variants as specified. Set prices in store currency.
4. For each product, open the mockup view and check placement, adjust, save.
5. Publish each to Shopify from the Printify dashboard. Note the three new
   Shopify product IDs.
6. In the app, open Oregon Ducks Set (id 02153fb78d77) > Designer > Add
   products. Search by title or paste each product ID. Do NOT add the catalog
   templates (those are for new designs).
7. Check Variants and publish shows Grouped with the new total and no limit
   text. Do not tap Publish in the app for this set (see risk 1).
8. Report the IDs and the final variant counts back to Ovi.

---------------------------------------------------------------------------
## 5. Decisions — ALL RESOLVED (Ovi, 2026-11-06)
1. Same Oregon badge on all three types: YES. A different design is for
   the bulk-clone/clone version, not this expansion.
2. Classic Long Sleeve = Gildan, not American Apparel ("Gildan for both
   long sleeves"). Implemented as Gildan Softstyle 64400, blueprint 2806.
3. Titles: Ovi chooses them himself; the proposed titles were only
   proposals.
4. Long Sleeve variants: all sizes S to 5XL with his 11 colours (76
   variants, under the 100 cap, so no cut needed).
5. "T-shirt 27" = the new plain Long Sleeve Tee, $27 USD. Classic $29
   USD, V-neck $29 USD. The store's currency app converts for viewers.
6. Clogs stays out of this round: confirmed.

---------------------------------------------------------------------------
## 6. Risks and findings (not fixed, outside the brief)
1. Publishing from the app creates NEW live products and never updates
   existing ones. If the six store products are added to the Oregon set and
   Publish is tapped, all six are duplicated. Use the app only to group.
2. Mockup base for store products: the app renders on the product's stored
   image, which for Printify products already has the badge printed (and for
   the long sleeves is a model photo). Preview or Publish in the app on these
   products would double-print. The blank design-area templates are used only
   in the designer view, not as the server render base. Not changed here.
3. Live app.js side effect from Part 7: `fillDetails()` calls
   `setGrouping()`, which now also POSTs /details. Every `refreshAfterSet()`
   (Save, placement, product refresh) silently re-saves grouping and
   re-stamps `draft_saved_at`. Harmless data-wise, but wasteful and it moves
   the "Saved" time. Fix would be a separate UI-only `applyGroupingUI(g)` used
   by `fillDetails`, with `setGrouping` calling it after the save. Not
   applied, because it needs a full app.js (1778 lines) and is outside the
   brief; say the word and I will ship it.
4. Grouped Preview shows "0 variants" per product row, because
   `publish_checklist()` looks up payloads by product title and grouped
   payloads are titled after the set. Cosmetic, pre-existing, not changed.
5. The catalog grid overstates availability for bp80 (144 vs 117) and bp48
   (55 vs 51). That only matters for the design-first catalog path; the
   Printify-created store products carry the real variants.
6. Not verified: Printify behaviour with more than 100 variants (I rely on
   the 100-per-product cap recorded in the handoff), the real variant counts,
   the Oregon badge upload id, and existing test suites.

---------------------------------------------------------------------------
## 7. Second-message review (full conversation file + reference images)
Checked against everything delivered above. No code or spec change was needed.
- Confirmed: store currency is GBP, so the 27 / 29 prices need a currency
  check; the "t-shirt 27" mapping is still unconfirmed; questions 2 to 5 and
  the colour/size ranges are still unanswered by Ovi.
- Confirmed: Part 7 is live (commit b2f2692). Muse's own Part 7 test is
  `part7_fixes_test.py` (21 checks), which I did not have. Run it with the
  rest: it may assert template image pixels or catalog `sale_price` None.
  My app.py leaves the grouped message ("Grouped: %d variants, one campaign
  link.") untouched.
- The three Oregon Shopify photos, the two model first images (Gildan and
  American Apparel) and the Gearlaunch screenshots stay reference only. No
  new code or template uses them as a mockup base.
- Placement reference, eyeballed from the Oregon tee, hoodie and crewneck
  photos (rough, not measured): the badge is about 45 percent of the garment
  body width, centred on the chest, hoodie slightly higher and smaller to
  clear the pocket. Use that as the starting look for the new long sleeves
  and V-neck, then fix on the Printify mockup.
