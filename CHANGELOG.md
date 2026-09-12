# Changelog

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
