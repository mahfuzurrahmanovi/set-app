# Designer fix plan (Ovi, 2026-11-03 22:18, 4 fixes)

Scope: ONLY these 4 fixes. Separate pages stay separate. Publish stays
DIRECT live (status active, 21:30 change). No live profit anywhere.
No deploy, no live publish, no message to Ovi. Tests on temp data
roots with mock Shopify only; real data/sets.json byte-identical.

## Fix 1 - Topbar hides half the designer screen
Root cause: designer.html has a sticky `.card.topbar` with set name,
Save, Publish (live), Download set JSON, Log out, publish status and
a "Save stores everything..." paragraph, all before the mockup. On a
phone that is ~50% of the viewport.
Change:
- Delete the whole `<div class="card topbar">...</div>` from
  designer.html, including its "Save stores everything..." paragraph.
- Preserve every function: Save and Publish (live) already exist in
  the Variants and publish card at the bottom of designer.html;
  Log out already exists in the top nav; Download set JSON is added
  to the Variants and publish card so it is not lost.
- JS safety: renderPublishStatus, renderDraftLine, updateCurrentSetLine,
  markDirty/clearDirty are already null-guarded, so removing
  topSetName/draftLine/publishStatus/dirtyNote elements cannot throw.
  Verified by a node stub-DOM execution test.
Test: designer page HTML contains no `topbar`, no `topSetName`,
no "Save stores everything", but still contains "Publish to Shopify
(live)", "Download set JSON", and a Log out control in nav.

## Fix 2 - Remove campaigns explanatory text
Root cause: campaigns.html line 12 has a paragraph Ovi did not ask for
and does not want.
Change: delete exactly
"Every set is a campaign, like Gearlaunch. Tap a campaign name for
its settings, or Designer for its designer page." No replacement.
Test: campaigns page HTML does not contain that string (nor
"Every set is a campaign").

## Fix 3 - Bulk clone must start with NO design (core bug)
Root cause: duplicate_set() in server/app.py deep-copies the whole
set, so a clone carries design_url, design dimensions/DPI, text
layers (with copied PNGs), rendered mockups, mockup versions and
mockup-URL heroes. Uploading a new design then sits on top of the
old printed design in the centre view, because centreImageUrl() in
app.js prefers mockups[0]/hero over the bare photo, and the client
never clears its local mockups after an upload.
Change (server, duplicate_set):
- After deepcopy, before saving: design_url = None,
  design_width/design_height/design_dpi = None, design_warnings = [],
  design_version = 1, text_layers = [], publish_state = "draft",
  campaign status = "draft" (already), artwork_locked = False.
- Per product: mockups = [], mockup_versions = {},
  mockup_version = None, hidden_layers = [],
  hero_image = None if it starts with "/static/mockups/".
- Do NOT copy any layer PNG files. Keep products, colours, sizes,
  prices, base costs, master placement and per-product placement,
  campaign settings (pixels, countdown, etc.), grouping, slug, tags.
- Do NOT touch the original set.
Change (centre mockup, app.js):
- centreImageUrl() must never return a rendered mockup: filter out
  any URL containing "/static/mockups/", prefer bare product
  images (images[0], image, bare photo fetched with ?bare=1).
- renderCentreMockup() fetches ?bare=1 when no bare photo is on file,
  stores it as _photoBare, and never falls back to a mockup URL.
- uploadDesign() clears the client's local mockups, mockup-URL
  heroes, _photo/_photoBare and _photoTried flags after a successful
  upload, then re-renders the centre mockup from the bare photo.
Test: seed a set with a design, layers, mockups and a mockup hero;
duplicate via API; assert the copy has design_url None, no layers,
no mockups, mockup_version None, hero not a mockup, design_version 1,
same products/colours/sizes/prices, and the original is unchanged.
Then upload a transparent PNG to the copy (via /api/sets/<id>/upload
with a real transparent PNG built in the test) and assert the copy
has exactly that one design_url and still no rendered mockups, and
the centre-photo endpoint ?bare=1 returns the bare photo, never a
mockup URL.

## Fix 4 - Can't move the design to place it perfectly
Root cause: tapToPlace is click-only (onclick on centreImg), the
placebox has pointer-events: none in app.css so it cannot be
dragged, and the topbar hid the mockup so taps landed on buttons.
Change (app.js + app.css):
- tapToPlace: ignore a click that follows a touch within 500 ms
  (lastTouchAt guard) to prevent double-firing.
- centreImg touchstart/touchend: touchend places at the touch point
  (changedTouches[0]) and records lastTouchAt.
- placeBox drag: pointerdown on the box starts a drag (touch-action:
  none, cursor grab in CSS, pointer-events auto on the box only);
  pointermove updates the master sliders x/y to the pointer position
  over the mockup and calls showVals() so the box follows; pointerup
  ends the drag and suppresses the following click if moved.
  Review fix: placeAt() also updates currentSet.master_placement
  live, because positionPlaceBox() reads the saved master — without
  this the dragged box snapped back to its old spot on every move.
  A compact draftLine / dirtyNote / publishStatus line lives in the
  Variants and publish card (the topbar's status displays, restored).
- Master sliders (x/y/scale/angle) and per-product placement sliders
  are unchanged and still save via saveMaster / save-all; dragging
  only writes into those same sliders, then Save persists them.
- After Fix 1 the mockup is the first large element on the designer
  page, fully visible on a phone viewport without scrolling past a
  button block.
Test: node --check on app.js; app.js source contains touchstart,
touchend, pointerdown/pointermove/pointerup drag handlers and the
last-touch click guard; CSS gives .placebox pointer-events auto,
cursor grab, touch-action none; server placement save round-trip
(master placement POST then GET) returns the moved values.

## Tests
New suite server/designer_fix_test.py, failing before, passing
after. Then rerun all: gearlaunch_pages 74, gearlaunch_flow 58,
fix3 89, rebuild 45, rebuild2 49, fix 24, mockup OK. 0 failures
required. Real data/sets.json byte-identical in every suite.
Review: one independent subagent review, fix what it finds.
Verify locally: temp copy of the real Oregon set -> duplicate ->
blank confirmed -> upload test transparent PNG -> move placement
via API -> only one design renders. No deploy, no live publish.
