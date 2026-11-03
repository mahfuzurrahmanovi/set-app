# Gearlaunch-style flow — test log (2026-11-03)

Plan: `gearlaunch-flow-plan.md`. Method: plan first, new test suite
written before implementation (it failed on missing routes: 404s),
then implementation, then all suites rerun.

## New suite: server/gearlaunch_flow_test.py — 54 checks printed + byte-identical check, 0 failed

- Campaigns list: create 2 campaigns, row columns ART/NAME/PATH/TAGS/
  ORDERS/ITEMS/STATUS/FULFILLMENT/END, orders null, no "profit" in JSON.
- Filter by name, path (slug), and tag; non-matches hidden; empty
  name and bad slug rejected.
- Bulk activate, status filter, bulk tag (deduped), bulk deactivate,
  bogus action rejected, bulk delete, one campaign remains.
- Settings save/load round-trip for every field (toggles, fudge 30,
  upsell 2.00, end 3/1/26, TikTok/Snapchat/Facebook pixels, tags, slug,
  How To Order description); persisted on disk across load_sets();
  negative fudge, negative upsell, and non-boolean toggle rejected
  with nothing changed; locked campaign skipped by bulk activate.
- Designer breadth: seeded set with 14 products lists 14, each with a
  price source; position front/back saved, other values rejected;
  pick colors subset + default (default moves to front), select-all
  equivalent, outside-list colours and default-outside-selection
  rejected.
- No profit: price below base cost does NOT block a dry-run;
  checklist has no profit key and readiness no longer needs base
  cost; UI has no "Profit:" text, no profitOf, no "negative profit"
  text; editor JS passes node --check, exactly one script block.
- Guards intact: combine set with 192 priced variants blocked by the
  100-variant guard; same set in split mode passes.
- Real data/sets.json byte-identical (sha256 cfe1882f...352d3ad2,
  unchanged from before this build).

## Rerun of all existing suites — 0 failed

- fix3_test.py: 89 passed, 0 failed (includes its Gearlaunch markers
  check, which now passes with the new UI).
- rebuild_test.py: 45 passed, 0 failed.
- rebuild2_test.py: 50 passed, 0 failed.
- fix_test.py: 24 passed, 0 failed.
- mockup_test.py: OK (locked follows master, unlocked follows
  override).

Total across suites: 263 checks, 0 failed.

## Independent review + fixes (2026-11-03, after the first green run)

Review verdict: ship with fixes. Both FAILs fixed, with tests:
- Duplicate of a locked (or active) campaign now resets campaign
  status to draft (other campaign settings copied); before, the copy
  stayed locked with no UI way to unlock it. Test: duplicate of the
  locked Golden State Of copy has status draft, fudge_factor 30 kept.
- Campaign settings save now rejects a blank name and stores the
  stripped name, matching campaign create.
- Also fixed a review low: fractional fudge factor (30.5) is now
  rejected instead of silently truncated; pick-colors colours are
  deduped server-side.
- Review PASSes kept: no profit leak, no secret leak, auth/CSRF and
  all round-3 guards intact, mobile layout stacked/modal, hidden
  set page still draft-only. Review caveats left as-is (documented,
  not blocking): Facebook Conversions API token is stored in
  sets.json and returned to authed sessions (needed for the edit
  round-trip); product mockup files are not cleaned on set delete
  (pre-existing disk accumulation, not data loss); campaign
  thumbnails lack flex-shrink: 0 (cosmetic).

Rerun after review fixes: gearlaunch_flow 58 printed + byte-identical
check, fix3 89, rebuild 45, rebuild2 50, fix 24, mockup OK — 267
checks, 0 failed. Real data/sets.json still byte-identical
(cfe1882f...352d3ad2).

## Spec changes that required updating old tests (not regressions)

Round-3 profit guard superseded by Ovi's 2026-11-03 removal:
- rebuild_test.py "negative profit blocks dry-run" became "price below
  base cost does NOT block dry-run" (same setup, dry-run now 200).
- rebuild2_test.py "negative profit still blocks dry-run" became the
  same assertion, with one fix to the test itself: section 8 of that
  suite removes the design, so the dry-run was actually failing on
  the missing-design guard, not profit. The test now re-uploads the
  design first, so it genuinely proves the profit point.

## Local verification (not yet done at log time)

- App run + click-through campaigns -> settings -> designer ->
  pick colors -> save -> reload, and Oregon set load check: see the
  final report; the suites above cover the API and UI markers.
- NOT verified: Render deploy (no git repo locally, no push made),
  real phone layout, real draft publish (Ovi's to trigger), mockup
  from a remote catalog image in the new flow.
