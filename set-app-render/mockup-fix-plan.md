# Mockup fix plan (Ovi, 2026-11-03 22:43, Warriors screenshots)

## Fix 1 - Uploaded design not visible in designer mockup
Root cause: `renderCentreMockup()` in `server/static/app.js` sets `centreImg` to
the bare product photo and draws an EMPTY dashed `placeBox` div. No design
image is ever rendered inside the box.
Change: render the uploaded design inside the fixed print-area box as
`<img src=design_url>` (plus visible text layers rendered as text in the
box, in layer order), filling/clamped to the box. Upload, save, reload and
product switch must all show it. No design -> box stays empty with the
"No design uploaded yet" note; never invent a design.
Test: designer centre HTML contains design_url inside placeBox after upload;
no-design case shows the note and no design img.

## Fix 2 - Print area fixed, only the design moves
Old model: `positionPlaceBox()` sized/moved the dashed box from the master
placement (x, y, scale, angle), and the box was draggable, so the print
area itself moved.
New model: the dashed box is a FIXED print area per product:
left 25%, top 20%, width 50%, height 50% of the mockup image, unless a
product carries explicit fractional print-area coordinates (none of the
current templates do: their print_area is a print-file size in px, e.g.
3033x3442, not on-photo coordinates, so the fixed chest area is used and
documented). The DESIGN inside the box moves: dragging the design,
tapping inside the box, and the left/right, up/down, size, angle sliders
move/scale/rotate the design WITHIN the box, clamped to it, and Save
persists that design placement (master_placement, migrated: existing
placements are reinterpreted as design offset inside the box, design
starts centred in the box when no placement exists). Dragging the box
itself no longer moves the print area. Hint text updated accordingly.
Test: print-area box geometry is identical before/after a design
placement change; design img geometry changes and persists.

## Fix 3 - Exact Gearlaunch mockup: product only, from Printify
Old: centre mockup uses bare Shopify photos, which for store products are
model photos (person wearing the tee).
New: centre base uses Printify flat product photos from `server/catalog.py`
templates via the existing `GET /api/catalog/templates` (3 templates,
real images.printify.com URLs, already verified):
- title contains "v-neck" or "v neck" -> Bella+Canvas V-Neck (blueprint 48)
- title contains "long sleeve" -> Gildan Ultra Cotton Long Sleeve (blueprint 80)
- product already a catalog template -> its own first image
- otherwise (short sleeve, hoodie, crewneck, mug, hat, kids, etc.):
  NO template exists, so use the bare Shopify photo and label it in the
  UI as "Not a Printify flat photo" - never invent a Printify URL, never
  claim a model photo is flat.
Test: matched titles resolve to the template image; unmatched titles
resolve to bare photo + honest label; no invented Printify URL in code.

## Fix 4 - URL path auto-generates from the name
Change: in campaign settings (`campName` -> `campSlug`) and in Create
campaign on /campaigns (new slug preview field), typing the name
auto-fills the slug: lowercase, spaces/punctuation -> hyphens, collapse
repeats, trim hyphens, and the fansfit.shop/<slug> preview updates live.
A manual-edit flag per field stops auto-overwriting once the user edits
the slug by hand. Existing slugs unchanged unless the name is edited.
Server slug validation is unchanged.
Test: slugify("Golden State Of Mind!") == "golden-state-of-mind";
manual edit stops auto-fill; preview updates.

## Fix 5 - Remove fields from campaign settings
Delete from the settings PAGE (`campaign_settings.html`) and from
`fillCampaignSettings`/`saveCampaignSettings` in app.js: Tik Tok Pixel,
Snapchat Pixel, Override default pixels (New Facebook pixel, Custom
Audience, Conversions API access token, Old Facebook pixels, Key Page
View, Add to Cart, Checkout), End date. Keep: Details, Storefront,
Conversion tools, Cloak & Dagger, Upsells, Description.
Backend: old fields stay tolerated in stored data and in the campaign
validation/defaults so existing sets do not break; the UI neither shows
nor requires nor sends them.
Test: settings page HTML contains none of the removed labels/ids;
save round-trip works without those fields; an old set carrying them
still loads.

## Hard constraints (unchanged)
Separate pages only; direct live publish (status active); no live profit;
password login; persistent disk; 100-variant guard; stale-mockup block;
no Cat Kiss Fish; no order automation. Oregon set byte-identical in
tests. Tests use mock Shopify only; nothing published live.
Deploy automatically after verification (standing rule 2026-11-03 22:31).
