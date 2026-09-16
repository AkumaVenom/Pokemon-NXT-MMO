# Route 36 Sudowoodo test report

Release: **0.6.5-alpha · Route 36 Sudowoodo Story Gate**  
Baseline: **0.6.4-alpha · Autonomous Trainer Performance Hardening**  
Validation date: **2026-09-17**

## Release-critical server and persistence checks

The dedicated `Tests.test_route36_sudowoodo` suite completed **13/13 PASS**. It verifies:

- the real Route 36 object binding (`johto_2_23`, object 3, tile 24/11) and unchanged shared collision value;
- authored Lv. 20 Sudowoodo identity, Rock typing and Rock Throw / Mimic / Flail / Low Kick move set;
- Whitney / Plain Badge prerequisite and non-buyable/non-tradable SquirtBottle properties;
- owner-only blocking when the underlying extracted tile itself is passable;
- additive SquirtBottle grant for both a new Whitney victory and an existing Plain Badge save;
- locked pre-badge UI plus server rejection of forged pre-badge use;
- non-consumption of the SquirtBottle;
- defeat and capture completion, owner isolation and relog persistence;
- run/loss behavior, which keeps the obstacle blocked;
- database failure rollback, which cannot publish a cleared path;
- forged Key Item purchase/trade rejection;
- stale-map, remote-proximity and post-clear replay rejection;
- migration cleanup of invalid/forged story flags.

The expected save-failure test deliberately injects `OSError: disk unavailable`; the server logs the rejected transaction and the test passes only when the owner state remains uncleared.

## Preserved adventure, Cut, replication and autonomous behavior

The following existing regression modules were executed against the finished 0.6.5 source after the story-gate implementation:

| Scope | Result |
| --- | ---: |
| Existing adventure regressions (`Tests.test_adventure`) | **25/25 PASS** |
| Regional encounters + personal Cut (`Tests.test_regional_encounters_cut`) | **24/24 PASS** |
| Progress persistence + replication state | **29/29 PASS** |
| Adventure network + replication network | **14/14 PASS** |
| Accepted 0.6.4 autonomous performance regressions | **5/5 PASS** |
| Autonomous world-life + evolution regressions | **7/7 PASS** |
| Adventure ROM + build tools + SQLite lifecycle | **45/45 PASS** |

Together with the dedicated story suite, these release-critical Python runs cover **162 passing tests**. No failing assertion occurred in these completed modules. Injected database-failure traces are intentional negative-path tests.

## Client/UI checks

The exact JavaScript set used by the normal source builder completed **107/107 PASS**:

- `check_registration.mjs`
- `check_renderer_replication.mjs`
- `check_adventure_ui.mjs`
- `check_learnsets.mjs`
- `check_battle_fx.mjs`
- `check_varieties.mjs`

This includes new checks for SquirtBottle Key Item presentation, locked/readied Route 36 dialog behavior, server-bound action payloads, journal state, owner-only story visibility and session reset. Existing renderer mocks were updated for the new `setStoryEvents()` interface so unrelated registration/learnset tests continue exercising the complete current client contract.

An additional `node --test Tests/*.mjs` sweep reported **116 passed / 1 module load failure**. The sole failure was `check_battle_browser.mjs` because the validation container does not have the optional `playwright` package installed (`ERR_MODULE_NOT_FOUND`); no browser assertion from that module executed. The normal source builder does not include this Playwright-only check in its required Node set.

## Syntax, launcher and content publication

- Python syntax compilation: **102/102 source/test `.py` files PASS**.
- Client launcher: `go test ./...` **PASS**.
- Server launcher: `go test ./...` **PASS**.
- Final content republish: **PASS** — pack `126860e80fe42e079fcca6c5`, **959 maps**, **877 catalog entries**, **14,807 PNG assets**, **2,366 verified audio clips**.
- Published runtime/client metadata reports **0.6.5-alpha** and the Route 36 client map retains the `johto_sudowoodo` object binding.

## Full builder attempt boundary

A clean `Build/build.py --existing-environment --no-open` run was also attempted. It successfully snapshotted **18,494** allow-listed source/content files, republished the same content pack and passed syntax parsing for **102 Python files** before beginning the complete Python discovery suite. The external execution session reached its **15-minute limit** while that large historical suite was still running, so this report does **not** claim a complete seven-stage builder pass from this environment.

The source package is therefore released on the completed release-critical suites above, not on an invented or partial full-build result. The Windows `BUILD_ALL.bat` remains the final native-machine build/packaging acceptance path for the user's deployment PC.

## Runtime acceptance still recommended

For production acceptance, use two separate accounts on Route 36:

1. Confirm neither can walk through the odd tree initially.
2. Defeat Whitney on account A and verify only A receives the SquirtBottle.
3. Confirm account B remains blocked.
4. Use the bottle on A, then run once and verify the tree still blocks A.
5. Re-engage and defeat/capture Sudowoodo; verify A can cross and B still cannot.
6. Relog both accounts and restart the server; verify the same per-character state persists.
7. Repeat with a capture to confirm Sudowoodo is saved while the personal route clear commits in the same result.
8. Continue a long-uptime autonomous-bot soak to confirm the accepted 0.6.4 performance behavior remains unchanged on the deployment hardware.
