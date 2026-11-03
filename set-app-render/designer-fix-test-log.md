# Designer fix test log (Ovi, 2026-11-03 22:18, 4 fixes)

Plan: designer-fix-plan.md. Tests on temp data roots, mock Shopify
only, never live, real data/sets.json byte-identical
(sha256 cfe1882ff2a230135aa35c26dc255896b1f1685bc8f9f8ac32e4f33e352d3ad2).

## New suite: server/designer_fix_test.py — 45 passed, 0 failed
Test-first: before the fix it was 27 passed, 16 failed (topbar
present, campaigns paragraph present, duplicate copied design/dims/
layers/mockups/hero, no touch/drag handlers). One failure during the
fix was the test itself: the centreImageUrl check tripped on the
word "/static/mockups/" inside a code comment, then on the guard
`indexOf('/static/mockups/')` itself; the check was corrected to
assert no p.mockups/mockups[0] return plus the guard present.

## Independent code review — verdict SHIP WITH FIXES, both fixed
Reviewer reran the new suite (43 passed at that point) and found:
1. HIGH: dragged box did not follow the pointer, because placeAt
   only wrote slider values while positionPlaceBox reads the saved
   master placement. Fixed: placeAt now also updates
   currentSet.master_placement live, so the box follows during a
   drag; Save still persists it. The weak "drag" substring check
   was replaced with a real node stub-DOM execution test:
   placeAt(100, 300) on a 400x400 mockup moves master to
   x 0.25 / y 0.75, sliders to "0.25"/"0.75", box to left 0% /
   top 50%.
2. MEDIUM: publish status, draft line and unsaved indicator were
   gone from the designer (JS was null-guarded, so nothing threw,
   but the displays were lost). Fixed: a compact draftLine /
   dirtyNote / publishStatus line was added to the Variants and
   publish card, with new presence checks; dead .topbar CSS removed.
Review also confirmed: Fix 2 clean, Fix 3 clean with no missed
design fields, bare-photo centre clean, touch double-firing clean,
no live profit, publish still direct live, pages stay separate,
no secrets in changed files. Reviewer did NOT re-verify the other
suites' counts; I did, below.

## Reruns — 0 failures
- gearlaunch_pages_test: 74 passed
- gearlaunch_flow_test: 58 passed
- fix3_test: 89 passed
- rebuild_test: 45 passed
- rebuild2_test: 49 passed
- fix_test: 24 passed
- mockup_test: OK (locked follows master, unlocked follows override)
Total with new suite: 384 automated checks + mockup OK, 0 failed.

## Changes
- server/templates/designer.html: whole `.card.topbar` deleted
  (set name, Save, Publish, Download, Log out, publish status,
  "Save stores everything..." paragraph). Save, Publish to Shopify
  (live) and Download set JSON added to the Variants and publish
  card; Log out already in the top nav. Designer hint updated to
  "tap ... or drag the dashed box itself". Designer now opens with
  the mockup editor first.
- server/templates/campaigns.html: explanatory paragraph deleted,
  no replacement.
- server/app.py duplicate_set(): blank-clone — design_url/dims/dpi/
  warnings cleared, design_version reset to 1, text_layers [],
  per-product mockups/mockup_versions/mockup_version cleared,
  hidden_layers [], mockup-URL hero cleared. Products, colours,
  sizes, prices, master/per-product placement, campaign settings,
  grouping, slug, tags kept. Original untouched (deepcopy).
- server/static/app.js: centreImageUrl() returns bare photos only,
  filters out any /static/mockups/ URL; renderCentreMockup()
  fetches ?bare=1 and stores _photoBare; uploadDesign() clears the
  client's local mockups/mockup heroes/_photo flags and re-renders
  the centre from the bare photo; tapToPlace() has a 500 ms
  last-touch click guard; centreImg touchstart/touchend place by
  touch; placeBox pointerdown/move/up drag writes into the master
  sliders (showVals, markDirty), and Save persists them.
- server/static/app.css: .placebox pointer-events auto, cursor
  grab/grabbing, touch-action none (was pointer-events none, so it
  could not be dragged at all).

## Local verification (temp copy of the real Oregon set)
Real local set id oregon-ducks-set, 3 products, no design on file
in the local seed. Duplicate -> design None, layers [], mockups
[[], [], []] for all 3 products, products kept. Upload of a test
transparent PNG -> exactly one design URL on the copy, no rendered
mockups. Master placement move to x 0.35 / y 0.6 / scale 0.42 /
angle 5 persisted. Original untouched. Designer page has no
topbar, campaigns page has no explanatory paragraph. Real
data/sets.json hash unchanged.

## Honest gaps
- Touch/drag and bare-centre behaviour verified by node --check,
  source checks and server placement round-trips, not by a real
  phone browser click-through (generic subagents cannot run a live
  browser). That click-through remains Ovi's check after deploy.
- The real local Oregon seed has no design on file, so the
  design-on-design stack was reproduced with a seeded set in the
  test suite (old design + rendered mockup + layers), not with the
  live Render disk set.
- Deploy outstanding: local only, not a git repo, no push, Render
  untouched, nothing published to Shopify, nothing sent to Ovi.
  Publish in the app is DIRECT live (status active) per Ovi
  2026-11-03 21:30 — Preview is the only safe check before tapping
  Publish.
