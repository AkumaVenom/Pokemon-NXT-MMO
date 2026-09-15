# Changelog

## 0.6.2-alpha · Autonomous Off-Screen Field Simulation · 2026-09-16

- Fix autonomous wild progression so it is completely independent of human presence. Bots now have a dedicated persistent background field clock separate from ranked `next_action_at`; wild battles, captures, EXP/levels, party development and level-aware regional travel continue when zero humans are logged in and when no player is observing the bot's map.
- Keep presentation and simulation separate. Only the stable materialized cohort on an observed map is excluded from background field work because those exact bots are already eligible for visible walking/wild actions; non-materialized residents on the same map continue progressing off-screen.
- Remove the probabilistic wild-training branch from the competitive queue. Ranked matchmaking can no longer starve field progression, and field progression can no longer consume a ranked action slot.
- Add a persistent staggered `nextBackgroundFieldAt` schedule in autonomous personality JSON, with bounded catch-up after server downtime. Long outages can recover a limited number of missed field actions without causing an unbounded restart spike.
- Background actions use the same authoritative party UIDs, real encounter tables and shared Battle engine as visible field battles. Captures, EXP, levels, HP/PP/items, travel metadata and AI Activity are committed transactionally to the existing autonomous trainer records.
- Add regression coverage proving a bot gains persistent wild-battle progression with no connected humans, still progresses when a human observes a different map, non-materialized residents progress on an observed map, and a materialized bot is not double-simulated by the background scheduler.

## 0.6.1-alpha · Autonomous Trainer Population Stability · 2026-09-15

- Fix the 0.6.0 crowding regression by separating persistent map residency from live materialization. Observed maps now replicate/move a stable bounded cohort instead of repeatedly choosing the nearest residents from a much larger logical population.
- Scatter newly materialized cohorts across real walkable encounter terrain with deterministic farthest-spacing and persistent authoritative coordinates. Give each materialized trainer a local roam anchor/radius so normal grass seeking and random walking do not reconverge the whole cohort onto one patch.
- Fix rapid remove/re-add flicker: cohort membership survives snapshot refreshes, a single legitimate departure preserves every unaffected visible trainer, and the destination cohort is not reshuffled merely because a new resident arrives.
- Add travel hysteresis. Routine/progression travel requires a minimum map dwell; loss retreat uses a shorter dwell; invalid or genuinely unsafe placements may still escape immediately. Observed maps allow at most one visible departure per configured cadence.
- Add a persistent resident floor for ordinary travel so an occupied training map cannot be drained to zero by regional simulation. Ordinary elapsed-time travel is deferred while humans observe that map, preventing the background scheduler from racing the field controller.
- Make destination safety a hard constraint before population balancing. Resident pressure now spreads equivalent safe destinations without ever pushing a low-level trainer into a stronger field solely to reduce crowding.
- Add one-time `WORLD_LIFE_VERSION=3` / `REGIONAL_TRAVEL_VERSION=2` autonomous rebalance so existing 0.6.0 databases recover from overcrowded/drained placement without resetting human accounts, bot identities, ratings, Pokémon, parties, captures or histories.
- Add regressions for stable cohort identity, authoritative spatial scatter, one-at-a-time observed departures, map-floor preservation, safe destination selection and continued party/follower identity.

## 0.6.0-alpha · Autonomous Trainer Regional Travel · 2026-09-15

- Replace permanent autonomous-map residency with persistent, region-bound travel. All 2,000 trainers can teleport between legitimate encounter-capable routes, forests, caves and wilderness areas in their home region instead of remaining trapped on their original map forever. Interior/building maps, towns/cities and maps without usable non-Surf training tiles are excluded from the travel catalog.
- Build destination difficulty directly from the published encounter tables across morning/day/night. Select destinations against the bot's real authoritative party level using weighted encounter pressure, recent-map avoidance, light population spreading and deterministic variation; Kanto bots remain in Kanto and Johto bots remain in Johto/Sigma.
- Add automatic safety recovery. A bot already on an invalid/wrong-region map or a field whose upper encounter pressure exceeds its current party capability relocates before further autonomous wild training. Repeated wild losses schedule a retreat to an easier map, preventing level-5 trainers from repeatedly feeding into Victory Road/Cerulean Cave encounters.
- Add progression travel. Bots that have outgrown a field and accumulated successful wild training advance toward harder but still level-safe maps. Routine travel rotates bots through comparable training areas so the overworld population remains dynamic even when no human players are online.
- Persist travel region, destination history, travel count/timestamps, per-map wild wins/losses and pending retreat/progression in existing bot personality JSON. Field and elapsed-time simulation both execute travel, and AI Activity records the relocation. No SQL schema bump is required.
- Preserve the 0.5.1 authoritative party-identity contract: destination selection reads the real party, the overworld follower remains `party[0]`, wild and ranked battles use the exact same owned party UIDs, and all additional Pokémon still have to be genuinely captured.
- Add focused regression coverage for 2,000-bot regional integrity, safe fresh-level placement, prohibited-interior exclusion, routine rotation, forced retreat from endgame maps, persistent loss-triggered retreat metadata, and level-35 advancement from an outgrown starter route into a harder level-safe Kanto field.
- Validate the complete tree with 604 Python tests (603 passed, one platform skip), Go tests/vet, Windows x64 client/server cross-compilation, launcher security smoke checks and 103/103 Node client/UI tests. Exact Python dependency-pin installation could not be repeated in the offline container; the builder's explicit existing-environment mode was used and that boundary is recorded in the travel test report.

## 0.5.1-alpha · Authoritative Bot Party Identity Fix · 2026-09-15

- Make the persistent ordered autonomous `state.party` UID list the single source of truth for overworld followers, autonomous wild battles and human-vs-bot ranked battles. Ranked challenge rosters now preserve exact UID order instead of scanning collection/storage order, so the Pokémon visibly following a bot is the same individual sent out first in battle.
- Add fail-closed autonomous party ownership validation and replicate follower UID/level alongside species/variety for identity-level regression coverage. No battle path is allowed to generate or substitute a presentation-only Pokémon.
- Stop giving newly seeded bots arbitrary extra Pokémon. Fresh bots now start with exactly one level-5 starter, matching normal player creation; every additional Pokémon must come from a real persistent wild capture.
- Add a one-time, non-guessing legacy cleanup for the deterministic synthetic bootstrap extras from 0.4.0/0.5.0. Only the known positions/species created by that old seed algorithm are removed; genuine later captures and their relative party order are preserved. The migration is versioned in existing personality JSON and requires no schema bump.
- Add regressions that deliberately make collection order disagree with party order, prove map follower UID/species/level equals the ranked battle lead, prove the complete battle roster matches party UID order, and prove legacy cleanup preserves a genuine captured Pokémon while removing only the old synthetic records.

## 0.5.0-alpha · Autonomous Trainer World Life · 2026-09-15

- Promote the accepted persistent 2,000-trainer competitive population into real server-owned overworld actors. Guarantee at least one resident autonomous trainer on every playable Kanto and Johto/Sigma map, then distribute the remaining population into encounter-capable routes/caves for denser training activity. Preserve existing bot identities, ratings, histories and Pokémon through a one-time world-life placement migration.
- Restrict autonomous overworld presentation to the supported Red/Leaf trainer sprites with an even deterministic split. Replicate each bot's real first-party Pokémon as its follower and persist field position/direction across sessions.
- Add authoritative GBA-style field movement using the existing map collision/elevation rules and player tile cadence. Training-oriented bots path toward real encounter terrain, avoid occupied human/bot cells, keep their followers on the previous tile, and use the existing client interpolation/walk-frame renderer for smooth presentation.
- Replace cosmetic autonomous capture/training progression with genuine local wild encounters driven through the shared Battle engine. Persist HP/PP/item use, captures, EXP/levels, collection growth, bounded supply purchases and automatic party optimisation; expose visible field-battle busy state and record wild development in AI Activity.
- Extend elapsed-time simulation so encounter-map bots continue genuine wild development while no humans are online, alongside the existing rating-aware AI-v-AI ladder activity. Keep both paths bounded per pass rather than creating 2,000 browser sessions or permanently ticking 2,000 world actors.
- Keep schema 3: field state and placement metadata fit the existing bot state/personality records. Add batch field-state persistence, save/shutdown flushes, engagement cleanup on challenge failure/disconnect and focused coverage/movement/wild-development regressions. Preserve the BuildFix1 Windows source-build contracts.

## 0.4.0-alpha · Autonomous Trainers source BuildFix1 · 2026-09-15

- Correct the 0.4.0 source-release contract so the all-in-one build completes instead of stopping in the regression stage: align the local-admin audit gameplay version with `0.4.0-alpha`, make schema-upgrade assertions follow the authoritative schema constant, and retain explicit live-lease protection for the schema-2 to schema-3 migration.
- Restore required Windows CRLF bytes in `BUILD_ALL.bat` without weakening any bootstrap behavior or prerequisite checks.
- Add a dedicated schema-3 live-lease regression and update the SQLite fixture-lifetime source guard so every managed test connection remains explicitly closed.
- Republish the bundled client/server content metadata after the gameplay-version advance so both sides identify `0.4.0-alpha` and content pack `7c70a87caf1495540f4c8e1c`. No map, sprite, audio, encounter, battle or save data is changed by this correction.
- Validate the corrected staged-clean source through the complete seven-stage release builder: 97 Python files compile, 601 Python tests pass (one Windows-only PowerShell execution test skipped on Linux), Go tests/vet and Windows x64 cross-compilation pass, 103 Node client tests pass, launcher smoke passes, and all generated release ZIPs verify.

## 0.4.0-alpha · Persistent Autonomous Trainer Network

- Added 2,000 persistent server-authoritative autonomous trainers.
- Added autonomous rating-aware battles, Elo movement, tiers, W/L histories, recent-opponent suppression and elapsed-time catch-up simulation.
- Added persistent bot Pokemon collections, captures, training growth, storage and automatic party optimization.
- Added player-initiated ranked human-vs-bot battles, persistent human ratings and persistent rival histories.
- Added bounded shared-world bot materialization with each bot's first party Pokemon replicated as its follower.
- Added AI Activity, a combined human + autonomous Ranking Ladder, and Rivals Hub screens to the right gameplay panel; AI rows expose direct ranked battle actions.
- Advanced storage schema to 3 with indexed AI trainer, activity, competitive profile and rivalry tables plus 45-day activity retention.
- Kept autonomous catch-up outside the gameplay actor lock while preserving database lease/transaction authority.
- Preserved existing adventure, human trading, friendly human duels, spatial replication, save revisions and admin-console behavior.


## Build tools 1.4.1 · Windows console-build database-handle correction · 2026-09-14

- Fix the single reported v0.3.6 Windows build blocker: raw SQLite probe connections in the schema/lease test were committed but not explicitly closed, leaving the temporary database locked during cleanup (`WinError 32`). Close all four unit-fixture connection sites and all three supplementary process-fixture sites with `contextlib.closing`, retaining the inner transaction context.
- Keep the recent/future old-world lease rejection, unchanged schema/state assertions and expired-lease migration test fully enabled. Do not ignore cleanup failures, depend on garbage collection, require elevation or weaken production migration protection.
- Add mandatory regressions that retain real connections until inspection, exercise the exact reported fixture, inject read and transaction-exit failures, and enforce explicit closure in both unit and process probes. Include these regressions in clean source publication.
- Advance only the build revision to 1.4.1 across the BAT, bootstrap metadata, driver and current documentation. Keep gameplay 0.3.6-alpha, pack `6d5c55ab09dc9ab7d17928b7`, schema 2, dependency/toolchain pins and every client/server/content-tool byte unchanged.
- Provide a small merge repair for the complete original v0.3.6 source and four complete corrected source archives. Preserve private configuration, databases, certificates, existing build environments and outputs. See `Docs/WINDOWS_BUILD_FIX_1.4.1_TEST_REPORT.md` for this repair's executed verification and remaining platform boundaries.

## 0.3.6-alpha · Local administrator console (build tools 1.4.0)

- Adapt the supplied command proposal to NXT: 81 canonical commands, 21 aliases, dynamic help, exact account/owned-Pokémon targeting and searchable native catalogs. Exclude all chat commands and explicitly defer unsupported mechanics.
- Accept input only from the interactive world-server terminal. No network administration route, player rank, remote-console listener or client command dispatcher is added. Bound both stdin backlog and line/token sizes; EOF leaves the world online.
- Add serial, world-locked detached command plans; short-lived confirmation tokens; stale-session/state/config guards; fenced atomic character/control writes with successful database audit in the same transaction; private publication after commit.
- Add persistent timed/permanent bans, independent account locks, gameplay freezes, trading restrictions, warnings and local account password reset. Recheck controls and the verified credential hash immediately before publishing a session, including races with a ban, lock or reset.
- Administer all six cosmetic varieties without changing wild odds or native stats. Preserve selected moves, ownership IDs, PC/party rules, native growth/evolution conditions and personal Cut collision. Do not invent EV, ability, gender, nickname, weather or event systems.
- Keep ten developer commands disabled by default. Isolated AI test duels use cloned rosters and cannot generate real captures, items, EXP, currency or badge victories. Do not permit forced wins/losses of ordinary battles.
- Add confirmed clean shutdown/restart scheduling and cancellation. Supplied launchers restart only after exit 75 from a completed clean shutdown, never after failed saves or crashes. Reload only console policy and registration admission.
- Add schema-2 account controls and indexed transactional audits without resetting accounts; retain schema downgrade protection and refuse upgrades while an old world retains a recent lease. Preserve build-tools 1.3.4 link-free Windows variety fixtures, asset bytes, bootstrap toolchain pins and private deployment exclusions.
- Document every proposal row, command syntax, supported scope, trust boundary, audit/password handling, upgrade/rollback and platform-specific acceptance. See Docs/LOCAL_ADMIN_TEST_REPORT.md for executed results rather than assuming Windows or MySQL coverage.

## Build tools 1.3.4 · Windows variety-build portability correction · 2026-09-14

- Correct the two `test_varieties` publisher fixtures that used directory symlinks and failed with WinError 1314 in an ordinary Windows account. Copy only the supplied variety-front subtree into each disposable fixture; do not require elevation, Developer Mode, hard links, junctions or a permissive filesystem.
- Keep both idempotence/combat-data-preservation and unsafe-path/checksum-corruption checks enabled. Tighten negative assertions to the expected error, test the actual publisher with both link APIs denied, and verify source-asset isolation, temporary cleanup and missing-file rejection.
- Align the BAT, Python driver, bootstrap manifest and download user-agent on build revision 1.3.4. Correct the stale BAT gameplay label to 0.3.5-alpha. Preserve dependency/toolchain pins, normal prerequisite discovery, staged builds and stop-on-failure behavior.
- No gameplay version, content-pack, networking protocol, encounter/variety rate, sprite, audio, configuration, credential, database or saved-progress change. This is a source/build maintenance release of gameplay 0.3.5-alpha, not a new gameplay update.
- Add a correction to the original variety validation report, refresh build instructions, and provide a small source repair plus four complete source ZIPs with regenerated manifests.

## 0.3.5-alpha · Pokémon varieties and mirrored front sprites · Build tools 1.3.3 · 2026-09-14

- Import 3,697 supplied Ancient/Metallic/Shiny/Mystic/Shadow front sprites with stable catalog bindings and exact source/output checksums; guarantee all five fronts for every Kanto/Johto species. Trim transparent padding and centre original visible pixels without resampling or recolouring. Preserve every original PNG and audio file.
- Use horizontally flipped front sprites for every player-side battle Pokémon, including Normal; retain that orientation through attack/hit/faint/switch animations. Correct event-time identity handling for different varieties of the same species and owner-side capture events.
- Roll a cosmetic variety only after the authoritative wild species/level selection: Normal 90%; Ancient/Metallic/Mystic 2.5% each; Shiny/Shadow 1.25% each. Do not alter encounter tables, stats, moves, catch difficulty or trainer/starter generation. Unsupported extra-form art tickets fall back to Normal without redistributing rarity.
- Persist canonical identity through captures, PC transfers, supported evolutions, trade and relogging. Migrate legacy Shiny flags additively; keep save-before-success and rollback boundaries, ownership, Cut state and selected moves intact.
- Display full variety names and fronts in collection, summaries, battle, evolution, move reminders and trade. Add collection filtering and private seen/caught variety records. Explain regular-front fallback for an inherited extra-form identity lacking supplied art.
- Retain native regular follower icons and replicate their variety for five distinct bounded animated sparkle colours, with static reduced-motion markers and no particle accumulation or frame-by-frame network traffic.
- Add server, UI, rendering, failure-injection and two-account browser regressions; preserve accepted regional encounter/Cut, battle timing, audio and account isolation behavior. Ship complete editable source and supplied assets in four mergeable ZIPs; keep ordinary builds independent of RAR/Pillow/ROM inputs.

## 0.3.4-alpha · Regional encounters and personal HM Cut · Build tools 1.3.3 · 2026-09-13

- Replace invented starter-area fallback pools with exhaustive, stable-ID FireRed/Crystal bindings across all 959 maps; 248 maps contain ordinary pools. Preserve original ordered slot weights and levels, including Crystal day periods and Surf level probabilities.
- Resolve separate terrain/method/floor pools on the server. Zone merged Sigma caves/towers explicitly; do not spawn fallback Pokémon in encounter-free floors, labs or unsupported extra regions. Retain documented MMO encounter cadence and special-event limits.
- Auto-grant regional Cut field licenses at Misty/Cascade and Bugsy/Hive victories. Recognize already-earned badges without resetting accounts or replacing combat moves.
- Make all 120 small HM trees clickable, with accessible enabled/locked actions, authoritative nearby/map/badge validation and save-before-success. Persist private tree clearing across relog/map changes; remove only the owner's sprite/hit target/collision and leave shared maps/other accounts unchanged.
- Restore the missing Nidoran♂ catalog identity, native learning/cry binding, six male encounter slots, eight source trainer entries and separate Nidoran evolution identities. Do not rewrite previously captured Pokémon.
- Add encounter/Cut, all-tree isolation, failure injection, publisher/build sidecar and client stale-state regressions. Run two-account Chromium DOM/real-service acceptance through the optional documented QA transport bridge.
- Keep the 0.3.3 battle-screen/timer fixes, audio assets, native maps, hosting/configuration behavior, account ownership and existing progress. Update source-data selection, docs, audit and checksums; ship full source in two mergeable ZIPs.

## 0.3.3-alpha · Battle screen correction · Build tools 1.3.3 · 2026-09-13

- Invoke native browser timers with the proper global context instead of the animation controller receiver.
- Open the populated battle dialog before starting effects; recover usable battle controls after synchronous or scheduled effect failures. Cancel outstanding effects and suppress replay loops after failure.
- Add initial-sendout, timer-context and failure-recovery regression coverage. Keep authoritative turn locking, damage, saving and previous sound cancellation.
- Deliver the complete updated source and every bundled asset in two mergeable full-source ZIPs.

## 0.3.2-alpha · Battle feedback · Build tools 1.3.2 · 2026-09-13

- Add short attack lunges for both combatants, hit reactions, floating damage, critical-hit and effectiveness feedback from authoritative battle events.
- Bound presentation timing, deduplicate repeated snapshots and cancel obsolete effects on newer turns, battle changes or disconnect. Respect reduced motion.
- Retire earlier battle sound queues, delayed decodes and transient voices when a new turn or move supersedes them, preserving background music and the low-HP loop.
- Preserve native ROM assets, move learning, account progress, combat rules and earlier online/build fixes. Add focused presentation/audio lifecycle regressions to the all-in-one build.


## 0.3.1-alpha · Native learnsets · Build tools 1.3.1 · 2026-09-13

- Audit all 876 published profiles against both supplied ROMs; replace the 28 remaining fabricated Sigma lists. Preserve native row order and repeated levels; two missing terminators have bounded, byte-identical native recovery witnesses.
- Separate seven renamed Sigma move identities and bind them to native Sigma move sounds. Preserve canonical FireRed shared-species profiles.
- Correct initial move assignment, remove fabricated Tackle, reconcile stale learning queues and expose the next move plus complete native level-up list.
- Add owner-validated, durably saved Move Reminder choices with explicit replacement confirmation and stale-client guards. Existing accounts and progress remain intact.
- Separate combat accuracy and Special Defense stages. Retain documented alpha move-effect limits.
- Keep accepted starter/login/replication/persistence, Nurse Joy/interior, online TLS and automatic build fixes. Deliver complete source in seven smaller mergeable ZIPs.


## 0.3.0-alpha · Adventure update · Build tools 1.3.0

- Add server-saved native trainer victories, sixteen ordered Gym badges, journal goals and one-time rewards, regional Surf licenses and discovered-location travel.
- Replace remote menu healing with nearby Nurse Joy services; persist HP/status/PP restoration and Center return positions. Add owner-checked PC deposit/withdraw at Centers.
- Add seen/caught Pokédex history, supported evolution choices and explicit queued move learning; preserve UID, individual traits and existing progress.
- Recover 100 referenced Sigma rooms and 463 native Sigma learnsets. Normalize visible NPC identities before binding trainers and nurses.
- Repair tile-qualified doorway activation, native destinations and per-account dynamic returns, including Leaf’s Johto home; retain regional ROM art and extend music coverage to all 959 maps.
- Award trainer EXP once per defeated opponent, preserve it across ongoing turns, and prevent trainer battles from using wild run/capture rules.
- Add two-account network/restart, service, progression, content and interface regressions. Keep prior build, TLS, startup, starter and progressive-saving fixes.
- Bundle all content sidecars in clean source/build snapshots; publishing remains ROM-free and rejects incomplete content/audio.

## Build tools 1.2.3 · Starter selection, replication and persistent sessions

- Preserve the chosen starter independently of home region and snapshot registration choices before connecting.
- Validate complete starter selections and harden authentication retries, session ownership and reconnect loading.
- Freeze queued nested packets and retain incoming multiplayer deltas during local map loads.
- Add real multi-client starter, ownership, login and server persistence regression tests.
- Preserve the complete audio implementation and earlier build, startup and online setup fixes. No character repair or database reset is included.


## Build tools 1.2.2 · Online TLS setup and startup preflight

- Adds a numbered hosting setup window and console workflow to generate a private world certificate or import a matching certificate chain/private key. It preserves database credentials and exports a public-only player connection kit.
- Validates TLS files, key pairing, dates and the configured join hostname before opening a database. Reports the exact paths and the corrective setup command. TLS remains required for internet peers.
- Includes real encrypted HTTP/WebSocket regression coverage and retains the Windows launcher rejection fix 1.2.1, PowerShell HOME fix and world ownership/logging fix 1.1.2.
- Source arrives as two complete parts with all existing audio. Deployment certificates, generated player kits and live configuration are excluded from source builds.

## Build tools 1.2.1 · Windows rejected-request connection fix · 2026-09-13

- Fixed `WinError 10054` in the all-in-one build's audio settings rejection check: launcher error responses now consume small rejected request bodies before closing the connection.
- The discard has a one-second read deadline and a 4 KiB limit plus the overflow probe. Origin, nonce, method, content-type and settings validation remain enforced; rejected input is not applied.
- Added real TCP regression cases that split request headers and JSON over a closing connection, plus bounded upload checks.
- Smoke failures now identify the request route, launcher process state and recent launcher output, and write a failure report. Network errors remain failed checks.
- Gameplay remains 0.2.0-alpha. All 2,366 audio assets, content pack and world startup fix 1.1.2 are preserved; Audio Part 2 is reusable.


## 0.2.0-alpha · ROM audio integration · Build tools 1.2.0 · 2026-09-12

Added the supplied FireRed and Ultra Shiny Gold Sigma music/effect banks and lossless species cries to the client. All 859 imported map headers have original music bindings, including silence and inherited music. Exported native move sound-script metadata for IDs 1–354 from each ROM and connected the primary presentation paths, effect repeats, panning and applicable cry callbacks to the alpha's move events. Visual-task completion timings remain approximations because the client does not emulate the original GBA battle-animation system.

Added title/region, area, surfing, battle and result music; battle, capture, status, experience, party, healing, purchase, item, save, trade, movement and interface cues. Persistent success cues are emitted after accepted server operations commit. Stable event IDs prevent duplicate playback from repeated snapshots. Playback uses separate music/effects/cries levels beneath a master control, native loop boundaries, crossfades, bounded loading/voice queues and cancellation when leaving a battle or disconnecting.

Added Sound controls on login and in-game, available during battles, with user-gesture startup, mute, background muting, low-HP warning and chat options. Launcher-backed preferences persist for the Windows user across sessions. The build verifies and packages the supplied audio without requiring ROMs, FFmpeg or a C++ renderer; ordinary automatic Go/Python setup remains the build entry point.

Preserved Sigma's actual source cry aliases rather than inventing unique expanded-species voices: 486 of its 491 catalog entries use Bulbasaur's cry and 5 form entries use Unown's. Four damaged unused cry entries are explicitly unavailable: normal IDs 251/287 and reverse IDs 119/287. Extraction repairs for damaged Sigma audio retain source-byte provenance and leave the supplied ROM files untouched. See `Docs/AUDIO_GUIDE.md` and `Docs/AUDIO_TEST_REPORT.md` for exact coverage, repair records and executed checks.

World startup fix **1.1.2**, the PowerShell **HOME** correction and MySQL setup **1.1.0** are retained. Existing database/configuration preservation still applies; this release requires matching updated Client and Server packs. Gameplay remains an exploration alpha with the previously documented campaign and mechanics limits. Native Windows/Edge listening and live MySQL acceptance are not implied by automated audio validation.

## World startup recovery and logs · Fix/build tools 1.1.2 · 2026-09-13

Corrected a startup cleanup gap: errors after claiming the world database (including extension, TLS and listener failures) could leave a recent lease behind, then a retry reported only that another server owned it. Startup failure diagnostics previously went only to the console, allowing world.log to remain empty. Added early persistent logging with the actual absolute path, safe failure details, complete startup/shutdown cleanup, idempotent store closure and bounded asynchronous retry for an abandoned lease. A refreshed foreign lease and future timestamp still block takeover; no force-unlock or database reset is introduced.

Added a small scripts-only installer for configured servers, with payload hashes, previous-script backups, idempotency and rollback. It updates server.py, nxt/store.py and the world startup CMD only; preserves config.ini, .venv, saved data, client assets and launchers; and needs no EXE rebuild or MySQL setup rerun. Included lease/lifecycle/logging/patch regressions and a reproduced failure record.

Gameplay/protocol/schema remain **0.1.0-alpha**. MySQL setup remains **1.1.0**; the prior Go/HOME correction remains present. See `Docs/WORLD_STARTUP_FIX_TEST_REPORT.md` for actual tests and native Windows/MySQL limits.

## Go prerequisite correction · Build tools 1.1.1 · 2026-09-13

Fixed the reported `Cannot overwrite variable HOME because it is read-only or constant` failure. Renamed the Go cache directory in `Get-NxtGo` and the SDK directory in `Test-NxtGo`: PowerShell treats `$home` as its read-only `$HOME`. The first collision stopped all Go discovery paths; the second was caught and silently rejected usable installed or freshly extracted compilers.

Added a host-independent reserved-variable regression guard, build-version consistency checks and native Windows Go discovery/validation regression cases. Updated the BAT banner, build metadata, setup guides and current validation report. Existing official download pins, automatic Python/Go provisioning, isolated packages and staged publication behavior are retained.

Gameplay/assets/protocol/schema remain **0.1.0-alpha** and MySQL setup remains **1.1.0**. See `Docs/AUTO_BUILD_1.1.1_TEST_REPORT.md` for executed checks and the remaining native Windows validation boundary.

## Automatic source build · Build tools 1.1.0 · 2026-09-13

Fixed the root BAT's dependency gap: it now starts with built-in Windows PowerShell 5.1 and automatically finds or downloads/installs missing full Python x64 and Go, then continues through the existing dependency/test/build/package pipeline. Added pinned official downloads, SHA-256 checks, Python publisher-signature checks, retried transfers, cache reuse, safe staged Go extraction, per-user locking and installer/bootstrap logs. No winget/Chocolatey dependency, administrator elevation, permanent PATH edit, persisted execution-policy change or database mutation is added.

Added automatic preservation/recreation of broken or incompatible build virtual environments; retained exact project package pins. Source packaging includes bootstrap scripts/manifest and excludes downloaded runtimes, caches and private settings. Passed/skipped Python test totals are now reported separately. The server dependency BAT recognizes the Python provisioned on the build PC. Added automated source/recovery contracts and Windows-only native PowerShell helper tests, and updated README/setup/build guides.

Gameplay, assets, protocol and schema remain **0.1.0-alpha**. The MySQL password GUI/setup code remains **1.1.0**, unchanged. See `Docs/AUTO_BUILD_TEST_REPORT.md` for checks actually executed and Windows/dependency-install limitations.


## MySQL setup hotfix 1.1.0 · 2026-09-12

Replaced the ambiguous invisible-password setup with a native Tk form: editable masked password fields, paste/selection, optional Show passwords, custom application-password confirmation, a read-only administrator login test, editable retries and a responsive worker/queue interface. The existing root password and the separate NXT application password are now explicitly distinguished. An empty admin password is preserved as empty; acceptance still depends on the existing MySQL account.

Added a masked console fallback compatible with Python 3.11+ and an explicitly opted-in visible fallback. Error messages distinguish authentication, server/port, privilege, policy, dependency and TLS failures without printing credential-bearing SQL or exceptions. Existing application credentials are checked before any provisioning DDL; no existing user password is silently changed. Configuration writes preserve world settings, verify the application login first, reject stale environment overrides and detect concurrent INI edits.

Added a scripts-only hotfix installer with payload hashes, script backups, idempotency and rollback tests. It never replaces config.ini, databases, assets, launchers or gameplay code. Added setup, native Tk widget and patch-installer tests and updated setup/build guides. The source BAT retains the same build entry point and includes these corrected scripts in future releases.

Gameplay/protocol/schema remain **0.1.0-alpha**; build tooling remains **1.0.0**. Setup version is **1.1.0**. Live MySQL/MariaDB and native Windows acceptance are not claimed; see `Docs/MYSQL_SETUP_FIX_TEST_REPORT.md`.


## Source distribution · Build tools 1.0.0 · 2026-09-12

Added `BUILD_ALL.bat`, an isolated Python build driver, clean release config templates, prerequisite discovery, private build dependency environment, serialized build locking, ROM-free snapshot content publication, regression/Go checks, Windows x64 GUI/console compilation and PE inspection, bounded headless launcher HTTP checks, ZIP integrity verification, SHA-256 manifests, build metadata, timestamped output directories and failure-visible logs.

Added build-tool regression coverage and source/build documentation. Source packaging excludes prebuilt executables, live configurations, virtual environments, caches, ROMs, runtime databases/backups, TLS material and logs. Rebuilds do not modify source gameplay files, configured deployments or MySQL.

This is a build/source distribution update only. Gameplay, protocol, database schema and accepted alpha limitations remain 0.1.0-alpha. Native Windows/Edge execution, production dependency installation and MySQL acceptance remain separate validation tasks; see `Docs/BUILD_TEST_REPORT.md`.

## 0.1.0-alpha · 2026-09-12

First independent Pokemon NXT MMO code/content baseline. Separate client/server configurations and Windows x64 launchers; Edge app-window client, dedicated Python console world service, MySQL store and explicit developer SQLite option. ROM-independent extracted map layers, collision/elevation data, native connection records, trainer sheets, battle sprites, shiny front/back sprites and two-frame follower icons.

Added account login/registration, six starter choices, region homes, nameplates, map-local entity/follower replication, global General/Trade chat, clicked-player challenge/trade actions, invitation expiry, alpha singles battles, capture/experience/party/collection, supplies and exploration conveniences. Added two-owner trade revisions, lock/confirm digest, audit uniqueness, atomic commit and inventory validation. Added autosave revisions, single-writer database lease/fencing, bounded queues, auth/chat limits and orderly shutdown.

During pre-delivery testing corrected FireRed level-up pointer alignment, object-palette registry selection, invitation packet kind collision, login-tab state on logout, missing land-encounter fallback handling, immediate duel forfeit, follower spawn overlap, walkable-map admission, movement single-key response, local unsent trade edit confirmation and retired map-layer caching. Added ROM-free content publishing with PNG digest, modular extension hooks, regression/network tests and explicit limitations documentation.

This baseline does not claim complete original campaigns, complete battle effects/audio, autonomous trainer bots, Windows/MySQL runtime acceptance or a proven 1,000-concurrent-player capacity. Refer to Docs/TEST_REPORT.md for executed checks.
