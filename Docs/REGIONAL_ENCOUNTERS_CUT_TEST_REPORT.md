# 0.3.4 regional encounters / Cut validation

Date: **2026-09-13**. Baseline: uploaded **0.3.3-alpha Source BattleScreenFix** split archive. This records source/build checks, not a claim of completed Windows multiplayer acceptance or original cartridge story parity.

## Executed checks

| Check | Result |
|---|---|
| Complete Python suite on updated source | **494 discovered: 493 passed, 1 skipped** |
| Same suite in a clean build-selected source snapshot | **494 discovered: 493 passed, 1 skipped** |
| All seven non-browser Node test scripts | **93 reported test units passed, 0 failed** |
| Added regional encounter / Cut Python module | **24 tests passed**, including all 120 real tree cells |
| Go launcher tests | Client passed; server launcher has no Go test files |
| Windows-target Go static checks and cross-compilation | Both passed; client GUI/server console x64 PE headers verified |
| Headless launcher HTTP smoke checks | All 26 passed against the actual Linux-built launcher |
| Two-account Chromium DOM / real-service Cut acceptance | Both regions, keyboard movement, account isolation and fresh-page relog passed; no page errors |
| Optional source-patch safety fixture | 7 passed: readonly, backup, idempotence, conflicts, corruption, rollback, path protection |
| ROM-free content republish | Matching pack **`3b8454ab8f1971ba1efe451d`** |
| Existing source/assets preservation | No original source file removed; all original PNG/OGG/WAV bytes unchanged |

The one skipped Python test is the native Windows PowerShell bootstrap helper on a Linux host. The combined Node run reports 93 test units: 84 core/UI/effects tests, eight audio-application tests and one audio-engine script. The latter also reports its 34 internal audio checks passing. The build runs these groups separately; its final 84-test group is not the whole JavaScript total.

During development, clean-source fixtures that depended on an operator config were corrected to use the build template. Older renderer mocks were updated for the new private Cut-state interface, and the shared-species audit count was updated for restored Nidoran♂. The complete suite above was rerun after those corrections. The browser fixture now explicitly brings each page forward and waits for rendering to settle before measuring a canvas hit target.

## Runtime and content cases

The new checks exercise exhaustive stable-ID bindings, no fallback on missing pools, all 24 clock-hour classifications, strict land/Surf separation, original slot and level weights, representative early/late tables, merged-floor/empty laboratory boundaries, publisher idempotence and rejection of missing bindings or malformed data. Nidoran♂ identity, both evolution targets, trainer source-ID mapping and existing cry references are checked.

Cut tests use the production gym victory/save path for both starting regions. They check correct regional badges, legacy migration, no automatic combat-move replacement, visible locked action, stale-map/missing-map/busy/out-of-range/other-object rejection, idempotent repeated requests and failure injection. Every one of the **120 actual trees** is blocked before clearing, walkable only for the cleared owner afterwards, and still blocked for the other account. Shared collision grids remain identical. Invalid saved flags do not clear arbitrary walls, rocks or another map's tree.

The browser fixture runs actual shipped client code, its canvas click/menu/key handlers, the production aiohttp service and a temporary SQLite database. It registers two independent accounts, stages the relevant saved badge prerequisites at a real Route 2 tree and a real Ilex Forest tree, and verifies enabled/disabled menus, a real Cut request, database commit, owner-only sprite/hit removal, owner movement into the tile, blocked peer movement and fresh-page reauthentication. Staging prerequisites is not presented as clicking through entire gym battles in the browser; the production victory path is covered separately by Python tests.

`evidence/regional_cut_browser.json` records these results. Chromium **144.0.7559.96** was used at 1440×1000. The six locked/unlocked/cleared screenshots were inspected for readable controls, proper tree removal and layout. No new art was generated.

## Environment and boundaries

- Python **3.13.5**, Node **v22.16.0**, **go version go1.23.2 linux/amd64**, Linux; aiohttp **3.13.3**, cryptography **46.0.4**.
- Full build validation used `python Build/build.py --existing-environment --no-open`. This developer option records that production dependency pins were **not installed or asserted**. PyMySQL is not installed in this test environment; SQLite fixtures do not imply live MySQL coverage. The unchanged normal Windows `BUILD_ALL.bat` workflow still manages its pinned build environment.
- This container blocks native loopback browser navigation by administrator policy. Browser QA used the explicit `NXT_QA_BRIDGE=1` local DOM/asset/aiohttp-WebSocket bridge without changing that policy. It is **not native browser WebSocket, Edge launcher, Windows input/audio hardware, TLS-device or live MySQL acceptance**. Existing real native socket/TLS Python tests and headless launcher HTTP checks are separate.
- Windows executables were cross-compiled and inspected, not executed on Windows. The PowerShell prerequisite installer was not executed here. The optional native battle-browser test remains separate; existing battle/timer/audio Node regressions pass.
- Full cartridge campaign, story gates, fishing/headbutt/contest/swarm/roamer/fixed legendary systems, original step RNG and every tile's human traversal are not implied. See `REGIONAL_ENCOUNTERS_AND_CUT.md` for the exact supported slice.

The full developer-mode build completed successfully, including clean source selection, republishing, both suites, cross-compilation, launcher checks, archive verification and publication to a new output folder. `evidence/regional_cut_build.json` preserves its machine-readable result. The release archives supplied here are source-only rather than those generated executable distributions.

## Pack and source reproducibility

The audit covers **959 maps**, **248 maps with pools**, **124 FireRed records**, **78 Crystal location/floor tables**, **120 Cut trees**, **877 species profiles**, **11,110 original game PNGs** and **2,366 verified audio clips**.

Catalog SHA-256 values:

```text
encounters_firered  dd07ca2d75362e9c47c624634dc55c70ac3d7294d728392fd5faccb2f2617855
encounters_crystal  7b2a103e5fc8dbcd3c58561cb4506e6f1ac78f626923ea2c794131669887194b
encounter_bindings  465de7f9f6898dd3c849d257798d818df58a168800c4d3b30787819691b5cda6
```

The release contains a regenerated `SOURCE_SHA256SUMS.txt`. Both mergeable source ZIPs are required; together their entries reconstruct the complete source, not two alternate builds. The small hash-checked patch is only an alternative for the supplied baseline and does not contain the unchanged art/audio library.

## Native acceptance still required

Back up the working deployment. Build and deploy matching Client/Server without replacing working configurations, TLS keys or the database. On two Windows PCs, repeat locked/correct-gym-unlocked Cut in both starting regions, owner/peer visibility and movement, map return, relog and server restart. Check an already-badged account too. Sample FireRed grass/cave/Surf and Crystal early/late/day/night encounters; also retain the accepted battle-screen, audio, Center, inventory, trade and account checks. This session establishes the deployment result that automated source checks alone cannot promise.
