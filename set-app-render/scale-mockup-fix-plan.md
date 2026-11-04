# Scale / Printify-photo / Auto-select fix plan (Ovi, 2026-11-04 19:54)

## Fix 1 - Design moves but cannot be scaled / reduced
Root causes (verified in code):
- Master Size slider (`#s` in designer.html Master placement card) only
  updates labels via `showVals()`; the preview only changes on Save
  (`saveMaster()` -> `positionPlaceBox()`).
- A locked product follows master, an unlocked product follows its own
  override, so the master Size slider does nothing visible on an unlocked
  product, and the per-product Size slider (`#ps-*`) lives only in the
  unlocked product card, below Preview, not next to the mockup.
- `placeAt()` in app.js forces `scale: 0.5, angle: 0` on every tap/drag,
  silently resetting any size the user had set.
Changes:
- Add a "Design size" slider directly under the designer mockup in the
  Design card (`#designSize`, range 0.1-0.5, step 0.01, label shows % of
  the fixed print area box: scale/0.5*100). On input it live-updates the
  design width inside the fixed print area (box 25%/20%/50%/50%) with no
  Save needed to see it, and marks the set dirty. It writes to the
  placement that actually applies: master if the selected product is
  locked, override if unlocked. It also syncs `#s` and `#ps-*` values.
- Make master `#s` and per-product `#ps-*` live-update the same preview
  on input (not only on Save), and show which placement applies:
  "Locked: follows master" / "Unlocked: this product only" next to the
  Design size slider, updated on product select.
- Fix `placeAt()` to preserve the current scale and angle instead of
  forcing 0.5/0.
- Save paths already persist master (`saveMaster`, `saveAll` placement)
  and override (`saveProductPlacement`, `saveAll` override_placement);
  the Design size slider must feed those same paths, so Save persists
  the new scale for both locked and unlocked products.
Tests: size 0.2 -> designImg width 40% of box; size 0.5 -> 100% of box;
Save persists scale for locked (master) and unlocked (override);
placeAt preserves scale.

## Fix 2 - Mockup images must be the exact photo used in Printify
Root causes (verified in code):
- `centreImageUrl()` in app.js: catalog kind -> own images[0] (good);
  otherwise `flatTemplateForTitle()` matches only v-neck and long sleeve
  (and for "classic long sleeve" it picks the Ultra Cotton template
  first, not the Classic template); otherwise it falls back to the bare
  Shopify photo, often a model photo.
Changes:
- `flatTemplateForTitle()`: check "classic" first -> American Apparel
  Classic Long Sleeve template; then "ultra cotton long sleeve";
  then any long sleeve; then v-neck. Keep the honest
  "Not a Printify flat photo" label when no match.
- New preference in `centreImageUrl()`: after catalog kind, if any
  stored image URL for the store product contains
  `images.printify.com`, use that exact URL as the centre base, in
  preference to a template match and to a model Shopify photo. Do not
  invent Printify URLs.
- Documented mapping with the current 3 templates only:
  v-neck -> Bella+Canvas V-Neck (48); long sleeve -> Gildan Ultra
  Cotton Long Sleeve (80); classic long sleeve -> American Apparel
  Classic Long Sleeve (945). Everything else (short sleeve, hoodie,
  crewneck, mug, hat, kids, etc.) has no template and keeps the bare
  store photo with the honest label.
- Gap (not guessed): template images are not labelled by colour in
  catalog.py, so colour-specific Printify photos cannot be selected
  reliably; the first template image is used, as before.
Tests: store product with a printify URL in images -> centre base is
that exact URL; classic long sleeve title -> Classic template;
v-neck -> V-Neck template; no printify URL and no template -> bare
photo + honest label, no invented URL.

## Fix 3 - Products auto-selected, clear remove option
Verified in code: `_entry_from_details()` in app.py already sets
colours/sizes to the full lists on add, and catalog entries do the
same. The UI makes it feel manual, and removal is only a small "X"
icon in the product-card header (app.js ~617).
Changes:
- Server guard in `_entry_from_details()` and in the add path: if
  colours/sizes arrive empty but all_colours/all_sizes are present,
  fill from the full lists, so no product can arrive unselected.
- Per product, add visible "Colours: Select all / Clear" and
  "Sizes: Select all / Clear" buttons on the product card (not inside
  a collapsed details section), calling the existing colours and
  variants endpoints and refreshing the set.
- Replace the small "X" with a clear "Remove product" button on every
  product card, visible without opening any collapsed section, calling
  the existing remove_product endpoint and refreshing the set.
- On set open, `renderProducts()` already renders every product card;
  keep that and assert it in tests (every product has a remove button).
Tests: add a product -> colours == all_colours and sizes == all_sizes;
Select all / Clear buttons present in rendered product HTML; remove
button present in rendered product HTML; remove via endpoint -> product
gone, set still loads.

## Hard constraints (unchanged)
Separate pages, fixed print area 25%/20%/50%/50% (only design moves
inside it), direct live publish (status active), no live profit,
password login, persistent disk, 100-variant guard, stale-mockup block,
no Cat Kiss Fish, no order automation, Oregon set byte-identical,
mock Shopify tests only, no publish to Shopify, no Gemini/Argon use.

## Deploy (standing rule, Ovi 2026-11-03 22:31)
After local verification, deploy automatically without asking Ovi:
re-clone mahfuzurrahmanovi/set-app if /tmp checkout is missing, copy
only changed files into set-app-render/, never data/sets.json, run new
+ key suites in the checkout, commit, push with gh, verify live by
curl (/campaigns 200, /static/app.js contains new size/Printify/
remove code), re-check once if Render is mid-deploy (502).
