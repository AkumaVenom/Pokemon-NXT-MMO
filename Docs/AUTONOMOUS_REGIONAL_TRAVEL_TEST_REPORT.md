# Autonomous Trainer Regional Travel Test Report — 0.6.0-alpha

**Date:** 2026-09-15  
**Gameplay:** 0.6.0-alpha  
**Content pack:** `d82421c661ec1c56bc0cc1d9`  
**Schema:** 3 (unchanged)

## Scope

This report covers the 0.6.0 autonomous regional-travel correction built on the accepted 0.5.1 authoritative-party baseline. The target defect was permanent map residency: low-level autonomous trainers could remain trapped in high-level encounter maps and repeatedly lose, while successful trainers could remain indefinitely on maps they had outgrown.

## Focused autonomous regression

`Tests/test_autonomous_world_life.py` passes all three integration tests. Coverage includes:

- exactly 2,000 persistent trainers;
- exact 1,000 Kanto-home / 1,000 Johto-home split and no autonomous cross-region placement;
- exact 1,000 Red / 1,000 Leaf overworld presentation;
- fresh trainers placed only on approved encounter-capable travel maps;
- no fresh placement in the indoor/building map class;
- zero fresh level-5 placements whose weighted `q90` encounter pressure exceeds the configured safety margin;
- GBA-style field movement and real follower anchoring;
- real Battle-engine wild training/capture persistence;
- routine same-region teleport rotation;
- forced level-5 Cerulean Cave placement classified `unsafe` and relocated to a safe Kanto field;
- repeated wild losses creating a persistent retreat request;
- level-35 trainer on Route 1 classified for progression and moved to a harder but still level-safe Kanto destination;
- authoritative party UID order still shared by follower and human-vs-bot ranked battle;
- accepted legacy synthetic-Pokémon cleanup still preserves genuine captured Pokémon.

The static autonomous contract check also passes and verifies the regional-travel version, party-identity version, travel configuration, wild simulation and AI Activity travel path are present.

## Fresh-population audit

A fresh disposable SQLite world produced:

| Check | Result |
| --- | ---: |
| Persistent autonomous trainers | 2,000 |
| Kanto home/current region | 1,000 / 1,000 |
| Johto home/current Johto/Sigma region | 1,000 / 1,000 |
| Red / Leaf presentation | 1,000 / 1,000 |
| Eligible Kanto travel maps | 93 |
| Eligible Johto/Sigma travel maps | 89 |
| Freshly occupied travel maps | 23 |
| Fresh bot placements on map type 3 | 1,557 |
| Fresh bot placements on cave map type 4 | 236 |
| Fresh bot placements on approved outdoor map type 1 | 207 |
| Unsafe fresh placements | **0** |

Fresh bots are deliberately concentrated on level-appropriate early-game fields; the population expands through the larger 182-map regional travel catalog as party levels develop. This is preferable to forcing a level-5 resident onto every high-level map.

## Full Python regression

Executed directly against the final gameplay tree:

- **604 tests run**
- **603 passed**
- **1 skipped** (platform-specific)
- **0 failures**
- **0 errors**

The suite covers account lifecycle, persistence, migrations, world leases, battle transactions, networking/replication, regional encounters, Cut, interiors, learnsets, varieties, audio, TLS/configuration, build tools and autonomous world life.

## Seven-stage release-builder verification

The project release builder was then executed against a clean staged source using `--existing-environment` because this container cannot resolve PyPI and therefore could not install the exact production Python pins. The staged source repeated the complete test/build workflow successfully:

- clean-source snapshot and release configuration policy: passed;
- content republish: passed — 959 maps, 877 catalog entries, 14,807 PNG assets, 2,366 verified audio clips;
- Python syntax: passed;
- staged Python regression: **604 run / 603 passed / 1 skipped**;
- Go client/server tests: passed;
- Windows-target `go vet`: passed;
- Windows x64 client cross-compilation and PE/subsystem validation: passed;
- Windows x64 server cross-compilation and PE/subsystem validation: passed;
- launcher HTTP/security smoke checks: passed;
- JavaScript/module syntax: passed;
- audio-engine and audio-app integration checks: passed;
- client registration/replication/UI Node suite: **103/103 passed**;
- generated Client, Server and Complete release ZIP verification: passed.

Builder completion time was **248.1 seconds** after staging.

### Dependency-pin boundary

A normal pinned build was attempted first. It stopped safely before staging because this execution environment has no working DNS access to PyPI, so `aiohttp==3.14.3` could not be downloaded. No version was silently downgraded. The successful seven-stage verification therefore used the builder's explicit developer `--existing-environment` mode and records `production_dependency_pins_enforced = false` in `BUILD_INFO.json`.

The distributed Windows `BUILD_ALL.bat` still uses the normal production path and installs/checks the exact `Server/requirements.txt` pins when internet access is available. This report does **not** claim that exact dependency installation was reproduced inside the offline container.

## Not claimed by this report

The automated build does not claim native Edge UI execution, live MySQL/MariaDB persistence, a deployed TLS environment or a 1,000-concurrent-client load test. Those remain target-environment acceptance items. The autonomous travel policy itself was exercised with a fresh 2,000-bot persistent population and the full SQLite/network regression suite.
