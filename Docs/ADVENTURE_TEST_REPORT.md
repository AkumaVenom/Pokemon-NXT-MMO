# Adventure update validation · 0.3.0-alpha / build tools 1.3.0

The release evidence below concerns the supplied source and disposable local fixtures. No configured customer world or account was edited.

## Inputs and integrity

The replacement five-part 7Z archive extracted successfully. All 14,365 entries in the accepted 1.2.3 source manifest matched their SHA-256 values before changes. The exact supplied FireRed Rev 1 and Sigma 1.5.0 ROM hashes match the prior pack provenance. ROM binaries are not included in the deliverable.

The updated pack contains 959 maps, 876 catalog entries and 2,366 unchanged encoded audio clips. Each build verifies every PNG-derived content digest, audio file SHA-256, encoded duration, loop boundary and all map/species/move audio references. The 100 recovered maps use source music headers. Content publication includes the adventure, regional trainer/evolution, Center and interior registries in the matching client/server pack.

## Gameplay and persistence coverage

- Independent accounts choose Chikorita and Charmander, retain unique ownership and move through replicated scenes without state crossover.
- Real TCP/WebSocket clients defeat the extracted Falkner and Brock teams independently; badges and team progress survive database/service restart.
- Journal rewards are private, commit before success, reject replay and remain unawarded after simulated database failure.
- Two accounts enter a shared Cherrygrove Center through different doors, heal, leave, lose battles and return to their own correct exits after rescue. Missing dynamic return context falls back to a safe home hub.
- Centers and Gym rooms reject incidental and manual wild encounters, including ice tiles previously mistaken for encounter terrain.
- Nurse Joy requires a registered nearby counter, restores HP/status/sleep/PP, persists the result and returns a success cue only after saving. Remote heal commands are rejected.
- PC storage checks proximity, owner UID, six-slot party limits and a healthy remaining party. State survives relog; trades preserve stored Pokémon.
- Evolution and move learning preserve ownership, individual traits, EXP, HP deficit and queued decisions. Unsupported ROM conditions are rejected rather than guessed.
- Trainer battles award per-opponent EXP once, preserve it across subsequent turns, record healthy participants and reject wild run/capture commands.
- Legacy account migration saves before publishing joined state. Cancellation, concurrent logout, stale revisions, failed transactions and relog retain the prior durability contract.

The source includes direct ROM parser tests, source-data checks and client handler/audio regressions. Older replication/audio fixtures explicitly request administrator exploration only where their subject is transport or transaction timing. Separate adventure tests retain default service and progression restrictions.

## Interiors and regional assets

Door triggers require native transition behaviors and valid approach directions before generic collision rejection. Dummy ordinary-floor warp records remain inert. Leaf’s New Bark doorway enters its source house, its stairs reach its source upstairs, and exits return correctly. Shared-room return context is saved per account. Earned atlas travel uses outdoor waypoints, preventing entry into shared rooms without a matching building entrance.

All 60 registered Center exterior doors have actual server-movement and SQLite entry/return regression coverage. Nurse counter geometry, each native regional nurse sprite and deterministic missing-nurse additions are audited separately. See `INTERIOR_ACCESS_AUDIT.md` and `CENTER_ASSET_AUDIT.md` for exact exceptions and adaptations.

## Platform boundaries

The automated host is Linux x64 with Python 3.12.14. Production requirements are installed in an isolated environment with exact top-level pins (`aiohttp==3.14.3`, `PyMySQL==1.2.0`); Go 1.27.1 is downloaded from its official distribution and checksum verified. Windows x64 cross-compilation and PE validation do not substitute for running the native Windows UI.

Native Windows PowerShell helper execution is an explicitly skipped platform test. Native Edge UI acceptance, an actual MySQL/MariaDB daemon, public router/TLS deployment and 1,000 concurrent players remain unverified. Local encrypted HTTP/WebSocket and shared persistence contract tests are included in the suite. The original ROM story/puzzle interpreter and every advanced battle mechanic are outside this implemented update; documented MMO access adaptations do not claim original script execution.

## Release run

**The complete build pipeline succeeded.** Build identity: `build-20260913-051254-803329Z`. Published content pack: `524386fe232fb0ef9dd3e749`.

| Gate | Result |
|---|---|
| Full Python regression suite | 406 run: 405 passed, 1 Windows-only PowerShell test explicitly skipped |
| Go client tests | 49 passed; server launcher package has no standalone Go unit tests |
| Windows Go static checks | Passed for client and server |
| Windows x64 compilation | Both EXEs built; PE architecture and GUI/console subsystems verified |
| Headless launcher HTTP checks | All 26 passed on Linux |
| JavaScript and audio checks | 55 Node tests and 29 audio-engine assertions passed |
| Bundled audio | All 2,366 files verified, covering all 959 maps |
| Source artwork preservation | All 10,902 original PNG files remain byte-identical; 208 derived native map/layer variants added |
| Release packaging | Client, Server and Complete ZIPs generated and CRC-checked successfully |

Final code and assets were compared with the successful build snapshot before source packaging; they match. The two source ZIPs carry a complete per-file SHA-256 manifest and are verified together when assembled. `BUILD_VALIDATION_1.3.0.json` contains the machine-readable build receipt and Windows executable hashes.

Original Gym puzzles use the explicit native-art access adaptations in `INTERIOR_ACCESS_AUDIT.md`; passing these tests does not claim an original-ROM script interpreter or native Windows gameplay validation.
