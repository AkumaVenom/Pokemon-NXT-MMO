# Autonomous Trainers 0.5.0-alpha — World Life Validation Report

## Scope

This report records validation of the `0.5.0-alpha` Autonomous Trainer World Life release. It builds directly on the accepted `0.4.0-alpha` BuildFix1 persistent competitive population and keeps schema 3, existing autonomous trainer IDs, ratings, battle histories, teams, collections, rivalry data and human competitive state intact.

The release adds a persistent overworld life layer for the same population of exactly 2,000 autonomous trainers. Trainers now have authoritative map positions, Red/Leaf overworld presentation, first-party followers, server-driven walking, real wild encounters, capture/training progression and visible world activity while preserving the bounded ranked/offline simulation from 0.4.0-alpha.

## Persistent population and map coverage

A fresh schema-3 validation store was initialized and the world-life placement migration was exercised against the published content pack.

- Persistent autonomous trainers: **2,000 / 2,000**.
- Playable maps discovered from authoritative content: **951**.
- Playable maps with at least one persistent autonomous resident: **951 / 951**.
- Encounter-capable maps: **248**.
- All 248 encounter-capable maps receive additional population after the one-resident-per-map coverage guarantee.
- Minimum persistent residents on a playable map: **1**.
- Maximum persistent residents on the shipped content: **6**.
- Red trainer presentation: **1,000**.
- Leaf trainer presentation: **1,000**.
- Invalid or obstructed assigned world positions in the coverage validation: **0**.
- Both Kanto and Johto / Sigma contain persistent autonomous residents.

Placement is deterministic for an immutable content pack and is cached by content-pack identity so ordinary service construction/restarts do not repeatedly rescan all map cells. The one-time migration only assigns world-life data where it is absent or invalid; it does not reset established competitive or Pokémon progression.

## Overworld movement and replication

The field simulation was exercised on Route 30 and through the automated world-life regression.

- Autonomous movement is server-authoritative and advances on legal walkable tiles only.
- Movement observes collision, elevations, map objects and warps rather than teleporting through world geometry.
- Trainer direction is replicated with each step.
- The first-party follower uses the bot's real owned Pokémon and follows the trainer's previous tile.
- Movement state is revisioned and batched to persistent storage on the configured field-persistence cadence.
- Nearby materialization uses the existing spatial-interest scene channel instead of publishing all 2,000 entities to every client.
- Autonomous entity deltas use the same client interpolation / walking-frame renderer contract as ordinary players.
- Red/Leaf bots remain selectable in the map UI and can be challenged through the existing player-initiated ranked-battle contract.
- A visible GBA-style `!` field cue is published while an autonomous trainer is resolving a visible wild battle.

A concrete Route 30 movement check observed a resident move from `(15, 31)` to `(15, 30)` while its follower correctly occupied `(15, 31)` and the trainer direction updated to `up`.

## Real wild battles, captures and training

Wild activity is not cosmetic. Encounter-map autonomous trainers use the existing authoritative `Battle` engine and the shipped regional encounter tables.

Validated behaviour includes:

- Local wild species and levels are selected from the bot's current map/terrain encounter data.
- Bots choose legal attacks, switches, healing/capture actions and consume their own field supplies.
- Damage, status, PP and party state produced by wild battles are committed to the bot's persistent state.
- Defeated wild Pokémon award real battle experience through the same growth pipeline used by player-owned Pokémon.
- Captures add real owned Pokémon to the autonomous trainer collection and party/storage model.
- Autonomous teams can be re-evaluated from their owned collection after progression.
- Wild capture / win / loss / training outcomes are recorded in AI Activity.
- Failed or interrupted human-vs-bot challenges release field engagement rather than leaving a bot permanently reserved.
- Disconnecting a player from a human-vs-bot battle immediately releases that bot back to field simulation.

Manual Route 30 integration produced local wild encounters including Hoothoot, Spinarak and Zubat, persisted captures into the autonomous collection, and raised the tested lead Pokémon from level 5 to level 6 through actual battle experience.

## Offline and scalability model

All 2,000 trainers remain persistent competitors, but only trainers relevant to currently observed maps receive high-frequency field movement. This prevents 2,000 continuously animated entities from being broadcast to every client.

- Connected-player maps receive high-frequency field movement and bounded visible wild activity.
- Dirty movement state is batch-flushed instead of synchronously writing every individual step.
- At most the configured number of new field wild battles is admitted per field tick.
- Elapsed-time catch-up remains batch-bounded.
- Encounter-map trainers can spend a configurable share of elapsed-time actions on the same real wild-battle/capture/training path; the remaining due actions retain autonomous ranked competition.
- Existing AI-v-AI Elo/tier/rival activity remains intact.
- Human-vs-autonomous competitive battles remain player initiated; bots do not issue unsolicited human challenges.

## Dedicated world-life regression

`Tests/test_autonomous_world_life.py` validates the release-specific contracts on an isolated fresh SQLite store, including:

- exact 2,000-trainer population;
- full 951-map coverage;
- Red/Leaf population split;
- denser distribution on encounter-capable maps;
- legal safe positions and reachable training locations;
- real server-side field stepping;
- first-party follower anchoring;
- real wild Battle-engine resolution;
- capture / experience / revision changes;
- persistent field-state writes; and
- nearby autonomous materialization.

`Tests/check_autonomous_trainers.py` also verifies release wiring across the world tick, configuration, schema-3 persistence, challenge UI/dashboard integration and renderer field-action support.

## Complete staged release-build validation

The project's real seven-stage `Build/build.py` workflow was executed against a clean staged snapshot of this `0.5.0-alpha` source and completed successfully.

- Clean source snapshot: **18,477 source/content files staged**; live configs, saves, TLS material, generated build outputs and logs excluded.
- Content publication: **PASS** — 959 maps, 877 catalog entries, 14,807 PNG assets and 2,366 verified audio clips; pack `b8887cfaeab25ace9d1bde1e`.
- Python syntax: **98 files PASS**.
- Python regression / real-network suite: **602 / 602 PASS**; one Windows-only PowerShell execution test skipped because this validation run was hosted on Linux.
- Go client tests: **PASS**.
- Go world-launcher tests: **PASS**.
- `go vet` for both Go modules: **PASS**.
- Windows x64 client/server cross-compilation: **PASS**.
- PE validation: **PASS** — client GUI subsystem and server console subsystem verified as Windows x64 outputs.
- Headless launcher HTTP/security smoke validation: **PASS**.
- Node client/UI regressions: **103 / 103 PASS**.
- Generated Windows client archive: **PASS** — 18,157 files, 546.0 MiB uncompressed content verified by the builder.
- Generated Windows server archive: **PASS** — 62 files, 2.7 MiB uncompressed content verified by the builder.
- Generated complete runtime archive: **PASS** — 18,481 files, 553.9 MiB uncompressed content verified by the builder.
- Complete staged builder: **BUILD SUCCEEDED** in 234.7 seconds after staging began.

The validation build used the builder's explicit `--existing-environment` development mode on Linux; it therefore exercised the complete source/build/test/cross-compile/package workflow without claiming that production Python dependency pins were freshly installed in that run. The normal Windows `BUILD_ALL.bat` bootstrap remains the target-machine path for discovering/installing the pinned build environment.

## Persistence / upgrade boundary

This release intentionally remains on database **schema 3**. Existing BuildFix1 schema-3 databases do not require destructive migration or reseeding. The world-life upgrade is stored additively in autonomous trainer state/personality data and preserves established bot ratings, wins/losses, parties, collections and rivalry history.

Production MySQL setup is intentionally outside the build workflow. Before replacing a live deployment, retain the normal database backup and target-machine acceptance process.

## Recommended target-machine acceptance

Extract all four `0.5.0-alpha` source parts into one clean folder and run `BUILD_ALL.bat`. Against a backed-up test database, connect at least two real clients and verify the same nearby Red/Leaf bots and first-party followers are visible to both clients, watch several bots walk, observe visible field wild activity, challenge a world bot, then allow autonomous wild captures/training to occur. Restart the world and confirm bot map position, collection, party/levels, rating, W/L history and rivalry state remain persistent. Also inspect AI Activity / Ranking Ladder / Rivals Hub after the restart to confirm the world-life layer and competitive layer continue to share the same autonomous identities.
