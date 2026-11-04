# Scale / Printify-photo / Auto-select fix test log (Ovi, 2026-11-04 19:54)

## New suite
- `server/scale_mockup_fix_test.py`: 31 passed, 0 failed (test-first:
  15 failed before the fix, then 1 placeAt-check wording failure fixed
  in the test itself, then all green).

## Reruns, all 0 failed
- mockup_fix 60, designer_fix 45, gearlaunch_pages 80,
  gearlaunch_flow 58, fix3 89, rebuild 45, rebuild2 49, fix 24,
  mockup OK. Total with the new suite: 481 automated checks +
  mockup OK. Real `data/sets.json` byte-identical
  (sha256 cfe1882ff2a230135aa35c26dc255896b1f1685bc8f9f8ac32e4f33e352d3ad2).

## Independent code review: first verdict DO NOT SHIP, both fixed
- B1: unlocked Design-size change was discarded by "Save placement
  for this product" because syncDesignSize() never updated the
  per-product #ps-* slider. Fixed: syncDesignSize() now syncs
  #px-/#py-/#ps-/#pa-* for unlocked products, with node regression
  tests (PS=0.20 after setDesignSize(0.2) on an unlocked product).
- B2: syncDesignSize() overwrote master #s from an unlocked override,
  corrupting master on the next Save. Fixed: #s is only synced when
  the selected product is locked (or none); regression tests assert
  #s and master placement stay 0.5 after an unlocked 0.2 change.
- Lows fixed: classic branch moved before v-neck in both JS and
  catalog.py; master #s max changed 1 -> 0.5; set_product_variants()
  now resets a stale default_color when colours are cleared.
- No second review round was run after these fixes; they are covered
  by the new regression tests and all suites pass.

## Local verification
- Temp copy of the real Oregon set (id oregon-ducks-set, 3 products):
  login 200, designer 200 with designSize slider present, JS markers
  for designSize / printifyImageOf / Remove product /
  selectAllColours present. Real sets.json untouched.
- No Gemini/Argon access was requested or used.
- Nothing published to Shopify by this build or its tests.
