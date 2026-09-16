# Johto / Sigma NPC dialogue restoration — executed test report

Release: **0.6.6-alpha · Johto Sigma NPC Dialogue Restoration**  
Date: **2026-09-17**

This report records checks actually executed against the release source. It does not claim native Windows/Edge/MySQL acceptance that was not run in this environment.

## ROM provenance and deterministic extraction

Development input was the user-supplied `Pokemon Ultra Shiny Gold Sigma Completo 1.5.0` GBA image. The extractor verified the reviewed source contract before reading content:

- size: **17,632,785 bytes**
- SHA-256: `62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64`

A second extraction was written to an independent temporary file and compared byte-for-byte with `Server/data/johto_dialogue.json`.

Result: **identical** (`cmp = 0`), both files SHA-256 `329472a89a805ea7a73c340cf222dd85c7eb276baf7a24e412df6c7d0b8f0c86`.

Published extraction audit:

- 534 Johto / Sigma maps
- 4,429 visible objects audited
- 3,124 eligible nontrainer/nonstory/non-Cut objects
- 2,158 validated dialogue entries
- 166 eligible objects without a readable script pointer
- 800 eligible scripted objects without a safely validated literal
- 881 resolved trainer bindings excluded
- 139 additional trainer-type objects excluded
- 284 Cut objects excluded
- 1 authored Route 36 story object excluded

## Dedicated dialogue regression

Command:

```text
python -m unittest Tests.test_johto_dialogue -v
```

Result: **12/12 passed**.

Coverage includes reviewed source provenance, release version, complete object accounting, source-object identity, static token safety, owner-context rendering, Kanto isolation, exact Route 36 source offsets, ordinary Johto NPC click output, Nurse Joy service preservation, Poké Mart service preservation, ordinary trainer party-preview preservation, and Gym Leader party-preview preservation.

## Preserved Route 36 and autonomous systems

Executed independently:

```text
python -m unittest Tests.test_route36_sudowoodo
python -m unittest Tests.test_autonomous_performance
python -m unittest Tests.test_autonomous_evolution
python -m unittest Tests.test_autonomous_world_life
```

Results:

- Route 36 Sudowoodo: **13/13 passed**
- Autonomous performance: **5/5 passed**
- Autonomous evolution: **2/2 passed**
- Autonomous world life: **5/5 passed**

The intentionally injected persistence-failure tests log expected exceptions while still passing their rollback assertions.

## Adventure/content regression

Executed independently:

```text
python -m unittest Tests.test_centers
python -m unittest Tests.test_adventure_rom
python -m unittest Tests.test_regional_encounters_cut
```

Results:

- Pokémon Centers: **12/12 passed**
- Adventure ROM publication/audit: **16/16 passed**
- Regional encounters and personal Cut: **24/24 passed**

A broader combined adventure run was also attempted but exceeded the execution session's time limit before completion; no full-suite pass is claimed from that attempt.

## Client JavaScript regression

Executed:

```text
node Tests/check_adventure_ui.mjs
node Tests/check_renderer_replication.mjs
node Tests/check_registration.mjs
```

Results:

- adventure UI: **32/32 passed**
- renderer replication: **12/12 passed**
- registration/session UI: **18/18 passed**

Total for these Node suites: **62/62 passed**.

`Tests/check_cut_browser.py` was attempted. Its local HTTP fixture started, but Playwright navigation to `127.0.0.1` was blocked by the execution environment with `ERR_BLOCKED_BY_ADMINISTRATOR`; therefore no browser-fixture result is claimed from that check.

## Build/source and syntax checks

Executed:

```text
python -m unittest Tests.test_build_tools
python -m compileall -q Server Tools Tests Build
```

Results:

- build/source tooling: **25/25 passed**
- Python compilation: **passed**
- source allowlist validation: **0 missing required files**, `johto_dialogue.json` included, **0 forbidden file extensions** in the source tree
- allowlisted source snapshot before the top-level checksum manifest: **18,499 files**, **650,210,943 bytes**

The release builder explicitly requires the new dialogue sidecar, runtime module, extractor, publisher, tests and documentation. `.gba`/ROM images remain forbidden source-package extensions.

## Go launcher checks

Executed:

```text
cd Client/launcher && go test ./...
cd Server/launcher && go test ./...
```

Both launcher suites passed.

## Final content publication

Executed:

```text
python Tools/repack_content.py --root .
python -m unittest Tests.test_johto_dialogue
```

Result: publication succeeded with **959 maps, 877 catalog entries, 14,807 PNG assets and 2,366 verified audio clips**. Server and client both publish **0.6.6-alpha** and matching pack identity `359d396b997ab4a5ccbc36c7`. The final dedicated dialogue suite again passed **12/12** after republishing.

Final source ZIP integrity is additionally verified after archive creation by extracting all four parts into a fresh directory and checking the bundled `SOURCE_SHA256SUMS.txt`.
## Native Windows source-build metadata correction

A native Windows `BUILD_ALL.bat` run supplied after the first 0.6.6 source package completed bootstrap, dependency installation, content publication and Python syntax validation, then ran all **638** Python tests. It reached the end with **one failure**: `ConsoleParsingTests.test_release_versions_and_manual_catalog_stay_aligned` found `Docs/LOCAL_ADMIN_PROPOSAL_AUDIT.json` still declaring gameplay `0.6.5-alpha` while runtime `VERSION` was `0.6.6-alpha`. The build correctly stopped before publishing an incomplete release.

The corrected source changes only release/build metadata and its guard: the audit gameplay field is now `0.6.6-alpha`, the `BUILD_ALL.bat` banner now identifies the 0.6.6 Johto/Sigma dialogue release, and the existing release-alignment test also asserts the build banner contains the runtime version. The BAT remains CRLF-encoded.

Post-correction checks executed in the repair environment:

- exact previously failing release-alignment regression: **passed**
- Windows BAT line-ending contract: **passed**
- focused admin parsing + bootstrap/build-source + Johto dialogue + Route 36 + autonomous performance/evolution set: **80/80 passed**

The original native Windows log had no second Python failure after the stale-version assertion; because the builder stops on any failed test, the corrected package should be rebuilt with `BUILD_ALL.bat` on Windows to complete the remaining packaging stages. No database, save, content-pack or gameplay migration is introduced by this correction.

