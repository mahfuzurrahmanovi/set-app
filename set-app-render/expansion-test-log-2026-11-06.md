# Expansion test log — 2026-11-06

Build: Claude round 2 (Sonnet 5.5, medium effort) + Muse updates to Ovi's
decided spec (2026-11-06). Changes: Grouped-mode >100-variant guard fix
(app.py), catalog templates for the 3 new types (Long Sleeve Gildan 2400
bp 80, Classic Gildan Softstyle 64400 bp 2806, V-neck Bella+Canvas bp 48)
with Ovi's Oregon colours, Long Sleeve S-5XL, prices $27/$29/$29 USD,
4 cleaned design-area templates, new expansion_types_test.py, and the 3
older suites updated to the decided spec (945 -> 2806, grid 224 -> 138).

## Suites run (final, all green, on a full copy — never the live data dir)
- expansion_types_test.py: 93 passed, 0 failed
- part7_fixes_test.py: 21 passed, 0 failed
- four_fixes_test.py: real sets.json unchanged
- designer_mobile_fix_test.py: 28 passed, 0 failed
- scale_mockup_fix_test.py: 31 passed, 0 failed
- mockup_fix_test.py: 60 passed, 0 failed
- designer_fix_test.py: 45 passed, 0 failed
- gearlaunch_pages_test.py: PASS, sets.json byte-identical
- gearlaunch_flow_test.py: PASS, sets.json byte-identical
- fix3_test.py: 89 passed, 0 failed
- rebuild2_test.py: 49 passed, 0 failed
- fix_test.py: 24 passed, 0 failed
- rebuild_test.py: 46 passed, 0 failed
- Total: 486 checks, 0 failed. Live data/sets.json sha256 unchanged
  (cfe1882f...352d3ad2).

Verified live via Printify CLI (provider 99): Long Sleeve 76 real
variants with his 11 colours, Classic 30 with his 5, V-neck 20 with
his 4. New set total 126; Oregon set becomes 184 + 126 = 310.

NOT done here: creating the 3 products in Printify, publishing them to
Shopify, adding them to the Oregon set in the app. Those need Ovi's go.
