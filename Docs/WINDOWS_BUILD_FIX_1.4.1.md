# Pokémon NXT MMO — Windows console-build repair 1.4.1

Gameplay **0.3.6-alpha** · Build tools **1.4.1** · Schema **2** · Content pack **`6d5c55ab09dc9ab7d17928b7`**

This corrects the complete v0.3.6 Local Administrator Console source (build tools 1.4.0). It is not a Pokémon Vortex update and is not a replacement for an incomplete source download.

## Cause and correction

The supplied `build-20260914-122114-117629Z.log` shows successful prerequisites, dependency checks, content publishing and Python syntax validation, then one test error: `test_schema_upgrade_refuses_recent_or_future_old_world_lease`. Windows refuses to remove its temporary `development.sqlite3` during teardown because fixture probe connections remain open (`WinError 32`). The earlier injected disk/transaction failures are expected negative tests marked `ok`, not additional build errors.

A SQLite connection's `with` block manages commit/rollback, not connection closure. Four connection sites in the test create six probe connections over its two heartbeat cases. They now use an outer `contextlib.closing` around the existing transaction context. Three similar sites in the optional real-process console fixture receive the same correction. Closing occurs even when the body or transaction exit fails; no cleanup error is suppressed and no garbage-collection workaround is used.

The actual schema/lease test remains active. It still refuses a live or future-clock old-world lease, verifies schema/data preservation and permits normal migration after an abandoned lease expires. The production Store already explicitly closes failed constructors and normal shutdown; its bytes and behavior are unchanged.

## Small repair — recommended for your existing complete source

Download `Pokemon_NXT_MMO_v0.3.6-alpha_ConsoleBuildFix_Repair.zip`. Close the failed build window and back up your source folder. Extract the ZIP, open its contained `Pokemon_NXT_MMO_v0.3.6-alpha_Source_LocalAdminConsole` folder, and copy **everything inside** into your existing source root: the folder that already contains `BUILD_ALL.bat`, `Build`, `Client`, `Server` and `Tests`. Merge the subfolders and replace the supplied files. Do not nest another project folder inside the existing one.

Run `BUILD_ALL.bat` normally. The opening banner must show **SOURCE BUILD 1.4.1** and **Gameplay 0.3.6-alpha**. This is a plain file-overlay repair, not a script that writes to a database. It replaces only the listed source/documentation/manifest files. Local edits to those same files should be reconciled from your backup rather than overwritten blindly.

The repair does not contain operator configurations, game assets, databases, certificates, compiled executables, `.build` environments or `dist` outputs. You do not need to reinstall Python/Go, reset permissions, enable Developer Mode, delete saves or run MySQL setup for this error. Do not apply old 1.3.4 repairs over this v0.3.6 release.

## Complete corrected source — alternative to the repair

Download all four ordinary ZIPs, with the common filename prefix `Pokemon_NXT_MMO_v0.3.6-alpha_Source_ConsoleBuildFix_`: `Part1.zip`, `Part2.zip`, `Part3.zip` and `Part4.zip`. Extract every part into the same **new** destination, merging their identically named project folders. The resulting root is `Pokemon_NXT_MMO_v0.3.6-alpha_Source_LocalAdminConsole`. Do not concatenate the ZIP files. Run `BUILD_ALL.bat` only after all four parts are extracted.

Use the complete corrected source **or** the small repair, not both. The full source includes all earlier assets and source; no original ROM, images.rar, previous patch or separate asset download is required.

## Preserved behavior and deployment

All client, server, content-tool, image and audio files remain byte-identical to the original v0.3.6 release. The 81 local-console commands, 21 aliases, developer gates, confirmations, transaction audits, bans/locks and graceful lifecycle remain. No chat administration is added. Varieties, rarity, mirrored fronts, follower effects, FireRed/Crystal encounters and personal Cut are untouched.

This correction does not add another migration. The existing v0.3.6 schema-2 upgrade still requires backing up your configured server/database and stopping the old world before deployment. Build and deploy matching v0.3.6 Client/Server while retaining existing configurations, database, certificates and connection settings. The build does not perform MySQL setup. Rollback from schema 2 to the older v0.3.5 server still requires the matching pre-upgrade database backup; never manually lower the schema version.

## Verification and boundaries

See `WINDOWS_BUILD_FIX_1.4.1_TEST_REPORT.md` for executed results. The mandatory new lifetime regressions hold real SQLite connections alive until inspection and fail on an unclosed handle on either platform; read and transaction-exit failures are also injected. The original failed test is not skipped or removed. Native Windows/Edge and live MySQL must still be verified on your deployment; a Linux developer build or Windows cross-compilation is not native Windows acceptance.

Python's official connection-context documentation explains the lifetime distinction: https://docs.python.org/3/library/sqlite3.html#how-to-use-the-connection-context-manager
