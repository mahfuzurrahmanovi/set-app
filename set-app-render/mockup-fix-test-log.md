# Mockup fix test log (Ovi, 2026-11-03 22:43, Warriors screenshots)

## What was fixed
1. Design now renders inside the fixed print-area box in the designer
   centre mockup (was an empty dashed box).
2. Print area is FIXED at left 25%, top 20%, width 50%, height 50% of the
   mockup; only the design moves inside it, clamped to the box.
3. Centre base is a flat Printify photo when a template matches by title
   (v-neck -> Bella+Canvas 48, long sleeve -> Gildan 80); otherwise the
   bare store photo with an honest "Not a Printify flat photo" label.
4. Slug auto-generates from the name (settings + Create campaign) and
   stops after a manual slug edit.
5. TikTok, Snapchat, Facebook pixel and End date fields removed from
   the settings page and its save JS; old stored values are tolerated.

## Files changed
- server/catalog.py: match_template_for_title()
- server/static/app.js: PRINT_AREA, slugify, bindSlugAuto, flatTemplateForTitle,
  centreImageUrl, renderCentreMockup (designImg inside box, mockupSource
  label), positionPlaceBox (fixed box + design inside), placeAt (clamped
  to box), designDrag (replaces centreDrag box drag)
- server/static/app.css: no change needed (placebox already pointer-events auto)
- server/templates/designer.html: mockupSource label, fixed-print-area hint
- server/templates/campaigns.html: campaignSlug field + preview, bindSlugAuto
- server/templates/campaign_settings.html: TikTok/Snapchat/Override/End cards deleted
- server/mockup_fix_test.py: new suite, 52 checks
- server/designer_fix_test.py, server/gearlaunch_pages_test.py: updated
  only for the superseded box-moves and pixel-field expectations, documented
  in the test files.

## Review blockers fixed (first review: DO NOT SHIP, re-review pending)
- B1 preview/publish divergence: clampPlacement() in app.js (used in
  placeAt, saveMaster, saveAll, saveProductPlacement, positionPlaceBox),
  app.py _validate_placement() now clamps instead of range-checking,
  mockup.py clamp_to_print_area() + effective_placement() clamp legacy
  placements, so Preview and publish renders agree. Scale capped at
  0.5; aidScaleToFit now 0.5. Rotation is about the centre and may
  extend past box corners at large angles (documented, not clamped).
- B2 unlocked drag: placeAt() writes to the selected product's
  override_placement when unlocked, master_placement only when locked.
- B3 centre layers: each visible layer positioned from its own x/y
  mapped into the box, with font, size, rotation, opacity; layers
  render even when the design is hidden.
- Non-blocking review items applied: template fetch failure resets
  the tried flag, mockup source label shows "Loading flat photo…"
  before templates load, no-design case no longer wipes layer divs,
  weak tests strengthened (no `or True`, real slugify execution,
  save-all clamp assertion, old-pixel preservation assertion).

## Re-review fixes (second review: DO NOT SHIP -> fixed)
- saveAll now carries unlocked override_placement and save_all
  applies it (validated/clamped); previously Save silently discarded
  unlocked drags.
- set_lock now validates/clamps the override and bumps design_version
  when it changes, so saved overrides mark mockups stale.
- Server layer render (text_layers.composite_layers) now clamps
  layer x/y to the print area, matching the centre preview.
- Centre preview now also respects per-product hidden_layers.
- Total after re-review fixes: see counts below.

## Test counts (all 0 failed, real data/sets.json byte-identical)
- mockup_fix_test: 60 passed (test-first: failed before the fix)
- designer_fix_test: 45 passed
- gearlaunch_pages_test: 80 passed
- gearlaunch_flow_test: 58 passed
- fix3_test: 89 passed
- rebuild_test: 45 passed
- rebuild2_test: 49 passed
- fix_test: 24 passed
- mockup_test: OK
Total: 450 automated checks + mockup OK.

## Local verification (temp copy of the real Oregon set)
Login 200, Oregon Ducks Set loads with 3 products, designer page
contains mockupSource + fixed-print-area hint, settings page contains
no pixel fields and still contains campName/campSlug. Real sets.json
unchanged (sha256 cfe1882ff2a230135aa35c26dc255896b1f1685bc8f9f8ac32e4f33e352d3ad2
in every suite).

## Honest gaps
- Centre design/drag geometry was verified by node stub-DOM execution
  and server round-trips, not a real phone browser click-through.
- Product types with no Printify template (short sleeve, hoodie,
  crewneck, mug, hat, kids) still use the bare store photo, labelled
  honestly; no Printify URLs were invented for them.
- Published mockups (server composite) still use full-image placement
  coordinates, which the client now clamps to the fixed box, so preview
  and publish agree for placements inside the box. Placements outside
  the box are clamped in the preview only; server composite for an
  already-saved out-of-box placement is unchanged.
