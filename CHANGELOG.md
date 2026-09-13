# Changelog

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
