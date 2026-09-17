# Johto / Sigma Field Item Ball Test Report

Release: **0.6.9-alpha · Johto / Sigma Field Item Ball Completion**  
Date: **2026-09-17**

## Automated coverage added

`Tests/test_adventure_rom.py` now verifies the bounded item-script reader, including direct and prefixed standard item-give scripts, and proves it stops at script termination/control flow rather than scanning adjacent bytes. Shipped-content checks assert the 386/361/25/125 audit invariants, exact object/source-index bindings, published `itemPickup` tags, multi-quantity presence, and preservation of existing Poké Ball/healing mechanics.

`Tests/test_item_pickups.py` exercises the real published content against a temporary authoritative database. It verifies an actual quantity-16 Sigma placement, durable one-time collection, owner isolation, replay rejection, map/proximity enforcement, 999-stack rejection and atomic rollback on an injected persistence failure.

## UI/content checks

The renderer has a private collected-item set parallel to Cut/story state. State replacement prunes stale clickable hitboxes as soon as a pickup becomes hidden. The Bag shows field-only items only after acquisition, distinguishes field pickups from Key Items, and Trade only renders owned tradable items so the expanded ROM catalog does not flood either interface.

## Executed validation

Final release validation completed on 2026-09-17:

- **83 focused Python regressions passed** across ROM extraction/publication, field-item runtime behavior, adventure networking, replication privacy, persistence and source-build selection.
- **25 Windows bootstrap contract tests passed with 1 platform-only skip**; this caught and corrected an accidental LF conversion in `BUILD_ALL.bat`, and the final launcher is CRLF-clean.
- **10 local-admin network authority tests passed** through their normal test discovery path.
- **151 dependency-free Node/client checks passed**, including 33 adventure-UI checks and 13 renderer/replication checks.
- `node --check` passed for both `Client/app/app.js` and `Client/app/renderer.js`.
- The optional Playwright real-browser harness could not execute in the packaging environment because the `playwright` package is not installed; this is recorded as an environment limitation, not counted as a pass.
- Broader Python regression batches were also exercised; they progressed without a field-item failure but exceeded the sandbox command time limit, so no full-suite pass claim is made here.

The machine-readable source-placement audit is `Docs/JOHTO_SIGMA_FIELD_ITEM_AUDIT.json`.

## Native acceptance still recommended

On a real client/server deployment, collect representative Johto/Sigma balls from an outdoor route, cave/interior and a placement with quantity greater than one. Confirm the exact item/quantity, relog persistence and per-account visibility with two clients. Also revisit a deliberately excluded look-alike ball (for example a starter display/custom event) and confirm it has not been converted into generic loot.
