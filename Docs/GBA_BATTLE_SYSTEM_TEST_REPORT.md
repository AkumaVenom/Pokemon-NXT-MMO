# GBA Battle System Completion — executed validation report

Release: **0.6.8-alpha · GBA Battle System Completion**  
Date: **2026-09-17**

This report records validation actually executed against the release source. It deliberately separates ROM-backed metadata coverage from emulator-equivalence claims: Pokemon NXT implements the reviewed move corpus in its server-authoritative MMO singles runtime; it is not a cycle-perfect GBA emulator.

## Source provenance and publication gates

The battle sidecar is hash-pinned to the two reviewed development inputs:

- FireRed USA/Europe Rev 1 — 16,777,216 bytes — SHA-256 `729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059`
- Ultra Shiny Gold Sigma Completo 1.5.0 — 17,632,785 bytes — SHA-256 `62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64`

`Tools/extract_battle_mechanics.py` statically publishes 361 move records (354 canonical FireRed moves plus 7 separately identified Sigma aliases) and 877 species battle records. The sidecar reports 198 active move-effect IDs. `Tools/publish_battle_mechanics.py` validates the source hashes and complete runtime identity sets before reapplying the reviewed battle fields after other content publishers rebuild the world data. Normal builds consume the generated sidecar and do not need either ROM.

## Executed Python validation

The following suites completed successfully:

| Scope | Result |
| --- | ---: |
| Battle ROM mechanics + Sigma moves + adventure combat + battle/audio events + core world/security/content | **99/99 passed** |
| Autonomous performance/evolution/world life + Route 36 Sudowoodo + Johto/Kanto dialogue | **47/47 passed** |
| Interior portal/access + Pokémon Center coverage | **31/31 passed** |
| Adventure progression/persistence interactions | **25/25 passed** |
| Regional encounters + owner-only Cut | **24/24 passed** |
| Growth + durable learnset runtime | **43/43 passed** |
| Varieties data/runtime | **32/32 passed** |
| Progress persistence + replication state/network + network + adventure network + async transaction + learnset network | **59/59 passed** |
| Learnset publication + ROM audit | **29/29 passed** |

The battle-focused suite includes a release gate that iterates all **361 published move records** and requires each one to be selectable and to resolve a complete server turn without raising an exception. Dedicated regression cases additionally cover reviewed edge semantics such as Psywave distribution, Present byte thresholds, OHKO level/strict threshold behavior, lower-level wild Roar, terrain-driven Nature Power/Secret Power/Camouflage, copy/call exclusions, Protect/Endure chaining, Charge duration, Thunder paralysis, Substitute trapping cleanup, Role Play/Skill Swap/Imprison/Wish failure guards, Hidden Power type propagation and Pressure PP consumption.

### Autonomous temporary-move regression

A dedicated regression reproduces the reported world-server failure state exactly: a level-30 Ditto has one persistent move (`Transform`), transforms into a level-30 four-move opponent, and therefore exposes four legal battle move slots while the saved Ditto record still has one slot. The autonomous selector must choose one of the four legal temporary slots without indexing the persistent list or raising `IndexError`.

The focused post-hotfix compatibility run completed **31/31 tests** across `test_battle_rom_mechanics`, `test_autonomous_performance`, `test_autonomous_world_life` and `test_autonomous_evolution`. This specifically verifies the fix alongside the long-uptime batching, background scheduler, real wild-battle simulation and bot evolution contracts. A further **52/52 build/bootstrap tests** passed with one Windows-only PowerShell execution test explicitly skipped on this non-Windows host, and **41/41 core content/security/world tests** passed. In total, the post-hotfix focused release gate completed **124 passing tests** plus the one environment-only skip.

Python syntax compilation completed successfully for **111 Python source/test/build files**.

## Browser/client validation

Eight non-Playwright JavaScript suites completed successfully for **149/149 checks** covering adventure UI, audio integration/engine, battle effects, learnset UI/data contracts, registration/session ownership, renderer replication and varieties.

`Tests/check_battle_browser.mjs` was also invoked, but this execution environment does not have the `playwright` package installed, so that optional browser fixture stopped before launching a browser with `ERR_MODULE_NOT_FOUND`. It is **not counted as a pass** and did not indicate a gameplay assertion failure.

## Launcher validation

Both native Go launcher suites completed successfully:

- `Client/launcher`: `go test ./...` — passed
- `Server/launcher`: `go test ./...` — passed

## Compatibility gates

The completed preservation suites verify that the battle changes do not remove or bypass the accepted MMO contracts: v0.6.4 autonomous batching/evolution, v0.6.5 Route 36 Sudowoodo, v0.6.6 Johto dialogue and portal repairs, v0.6.7 Kanto dialogue, regional Cut, PC/trade ownership, progression, varieties, replication and durable learnsets remain active.

Existing Pokémon without the new additive personality/friendship/held-item fields continue through deterministic/default fallbacks. No database schema bump or save wipe is required.

## Explicit fidelity boundaries

Passing the 361-move execution gate means every published move has a functional server execution path; it does **not** imply cycle-perfect cartridge emulation. In particular:

- Follow Me and Helping Hand are doubles-only mechanics; NXT is currently a singles runtime, so they fail cleanly instead of fabricating an ally topology.
- 491 Sigma hack-expanded identities have no safely reviewed exact Pokédex-weight mapping; they retain the documented explicit fallback for Low Kick weight rather than guessed values.
- Full GBA instruction/RNG ordering, every ability/held-item edge interaction, double-battle targeting, animation scripts and capture/presentation internals are outside the equivalence claim for this release.

These boundaries are intentional release documentation, not silent omissions.
