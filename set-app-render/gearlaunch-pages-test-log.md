# Gearlaunch separate pages — test log (2026-11-03)

## Problem
Ovi (21:28): the Gearlaunch build stacked Campaigns, Campaign
settings and Designer into one scrolling page; he could not
understand anything. Fix: exact Gearlaunch pages as separate pages.
Scope change (21:30): Publish is DIRECT (live/active), not draft only.

## What changed
- Routes: GET / -> redirect /campaigns; GET /campaigns (list table);
  GET /campaigns/<id> (settings only); GET /campaigns/<id>/designer
  (designer only). Unauthenticated page requests serve login.html
  (API remains gated as before); authenticated requests render the
  page with server-side name/status/links.
- Templates: campaigns.html (real <table>, Gearlaunch column order,
  horizontal scroll on phone), campaign_settings.html (Details,
  Storefront, Conversion tools, Cloak & Dagger, Upsells, Tik Tok,
  Snapchat, Override default pixels, Description), designer.html
  (FRONT/BACK, dashed mockup, PRODUCTS, pick-colors modal, upload,
  master placement, picker, catalog, variants + live publish),
  login.html. Old stacked index.html DELETED.
- Shared: server/static/app.css, server/static/app.js (page-aware,
  null-guarded; per-page init instead of one unconditional init).
- Direct publish: shopify.create_live_product sends status "active";
  app route /api/sets/<id>/publish (old /publish-draft removed);
  publish_state "published" (was "published_draft"); remove-product
  and create-page gates key on "published"; button "Publish to
  Shopify (live)" with live-immediately confirmation. Hidden
  set-page itself stays hidden (published_at null) and tap-gated.
- CONSEQUENCE: Publish now goes live immediately with no draft
  review step. Preview (dry run) is the only safe check.

## Tests (all on temp data roots, mock Shopify only, never live)
- New server/gearlaunch_pages_test.py: 71 passed, 0 failed
  (was 53 failed before the fix: new routes 404, stacked markup).
- Reruns, 0 failed each:
  - gearlaunch_flow_test.py: 58 (+ byte-identical = 59 reported)
  - fix3_test.py: 89 (incl. byte-identical)
  - rebuild_test.py: 45
  - rebuild2_test.py: 50 (incl. byte-identical, 49 + 1)
  - fix_test.py: 24
  - mockup_test.py: OK
  Total automated: 71 + 58 + 89 + 45 + 50 + 24 = 337, plus mockup OK.
  Real data/sets.json byte-identical in every suite.

## Older-suite updates (only where the old page / draft publish was assumed)
- fix3_test.py: /publish-draft -> /publish, create_draft_product ->
  create_live_product, mock statuses draft -> active, inverted the
  old "draft status rejected" section to "non-active status
  rejected", published_draft -> published, UI markers now read the
  three new templates + app.js, script check now node --check on
  static/app.js.
- rebuild_test.py: same endpoint/function/status renames; mock
  payload check renamed (title only, status is set inside the
  Shopify function, not in the app call).
- rebuild2_test.py: published_draft -> published in the remove
  guard test; /publish-draft -> /publish; JS check now node --check
  on static/app.js, markers from designer.html.
- gearlaunch_flow_test.py: /publish-draft -> /publish; UI markers
  now read the three new templates + app.js (campaignsTbody, not
  campaignsList), plus a "no draft publish wording" check.
- fix_test.py: Mockup-order block check now reads static/app.js
  (the block is JS-rendered in renderProducts), not GET / (which
  now redirects to /campaigns / login).

## Local verification (temp copy of the real Oregon set)
Walk run against a temp data root seeded from the real Oregon set
(local seed id oregon-ducks-set; Render disk id 02153fb78d77 is the
same set with the same 3 product ids, and lives on Render's disk,
not in this file):
- /campaigns 200: table + Create campaign + Designer link present;
  no campaignSettingsCard, centreImg, pickColorsModal.
- /campaigns/<id> 200: settings cards only; no table, centreImg,
  pickColorsModal.
- /campaigns/<id>/designer 200: FRONT, centreImg, PRODUCTS,
  pickColorsModal, Publish to Shopify (live); no
  campaignSettingsCard, no table.
- Settings save 200, round-trip fudge_factor 30, upsell_discount 2.00.
- Pick colors save 200 on tee 15469998538906: colours narrowed to
  Black, Cardinal Red, Gold.
- Reload from disk: settings 30 / 2.00 and tee colours persisted.
- Real data/sets.json sha256 cfe1882ff2a230135aa35c26dc255896b1f1685bc8f9f8ac32e4f33e352d3ad2, unchanged.

## Review
Independent review subagent, verdict DO NOT SHIP at first pass, with
two blockers, both fixed and retested (no second review round was
run; the fixes below are verified by the new execution test):
1. BLOCKER, designer JS init broke: designer.html called
   fillCampaignSettings(), which dereferenced unguarded camp*
   elements absent on the designer page, throwing at
   campStorefrontHomepage and aborting variant counts, publish
   status, centre mockup, layers and catalog rendering. FIX:
   fillCampaignSettings now early-returns when
   campStorefrontHomepage is absent; saveCampaignSettings and
   useHowToOrder are also guarded; renderProducts is guarded for a
   missing box. New pages-test section 8 executes
   fillCampaignSettings in node with a stub DOM, both with camp
   fields absent (designer) and present (settings), and passes.
2. BLOCKER, stale draft wording: designer topbar note said
   "Publish creates DRAFT products only, never live", directly
   contradicting live publish. FIX: replaced with live wording;
   pages-test section 5 now also rejects "DRAFT products only"
   and "never live" (the old exact-string check missed it).
3. LOW, login return-to-page broken: page routes passed next to
   login.html, but login.html read a ?next= query param that was
   never present. FIX: login script now uses the server-rendered
   next value (tojson) with the query param as fallback.
4. TRIVIAL, dead .campaignRow stacked-row CSS removed from app.css.
After fixes, all suites rerun green (see counts below, updated):
pages 74, flow 58, fix3 89, rebuild 45, rebuild2 49, fix 24, mockup
OK, 0 failed, real sets.json byte-identical in every suite.
Honest remaining gap: the designer JS fix was verified by the node
stub-DOM execution test and by server page checks, not by a real
browser click-through (subagents cannot run a live browser); that
click-through is Ovi's check after deploy.

## Not deployed, not published live
Local copy only. Live Render app is still on commit 7913ccd.
No Shopify product was created by this build or its tests.
