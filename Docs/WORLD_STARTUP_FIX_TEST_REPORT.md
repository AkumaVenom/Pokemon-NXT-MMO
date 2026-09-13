# World startup fix 1.1.2 — validation report

Gameplay/protocol **0.1.0-alpha** · Database schema **1** · Startup fix/build tools **1.1.2** · MySQL setup **1.1.0**

## Confirmed defect and scope

The reported message indicates a recent world-database lease. It can mean another world is running; the screenshot alone does not establish that ownership is stale.

The uploaded code had a confirmed failure path: it acquired the lease before extension/TLS/listener initialization, but its cleanup block began only after successful startup. A later error left the lease behind. The outer exception handler printed the error rather than recording it, so world.log could remain empty.

This was reproduced against the delivered 1.1.1 baseline with a real occupied TCP port and a disposable SQLite world: startup raised OSError, the lease remained active, the immediate restart was rejected, and world.log existed with **0 bytes**. MySQL setup does not acquire this lease; rerunning setup or resetting credentials is not the remedy.

## Corrected behavior

- Persistent logging starts before settings/content/database loading, prints the absolute log path and identifies a writable fallback when needed. Startup errors include the stage, safe exception/code hints and code locations, without raw credential-bearing config lines or driver exceptions.
- Extension, TLS and binding errors all clean up resources and release only the failing process's lease. Final-save failure still proceeds through resource/database cleanup and produces an error exit.
- Database construction and lease acquisition finish pending thread work on cancellation before their resulting connection is closed. Store closure is idempotent, serialized with acquisition, and cannot reconnect a closed store to write without ownership.
- A recent foreign lease receives bounded asynchronous retry, at most 65 seconds of retry budget. Once it expires or its owner releases it, startup continues. An advancing heartbeat identifies a still-running world; future timestamps produce clock guidance. No live lease is forcibly removed.
- A small hotfix updates exactly server.py, nxt/store.py and the startup CMD in an existing configured server. Hash checks, script backups, rollback and idempotency are included. No EXE rebuild or MySQL setup rerun is needed.

## Checks actually executed

| Check | Result and scope |
|---|---|
| Complete Python regression/integration suite | **184 discovered: 183 passed, 1 skipped**, in **12.682 seconds**, with RuntimeWarning promoted to error. |
| New lifecycle/logging regressions | **16 passed**: real bind failure and immediate successful restart, extension/TLS errors, final save failure, early logging, safe diagnostics, log fallback, stale/live/future lease handling, bounded wait and cancellation cleanup. |
| New lease regressions | **6 passed** with real temporary SQLite stores: active contender rejection, 59/60-second expiry boundary, superseded owner fencing, own-row release, future timestamps, idempotent closure, closed-store rejection and failed-constructor closure. |
| New updater regressions | **18 passed**: fixed payload/hashes, nested backups, safe reapplication, rollback, external edits, linked paths and replaced directories, preservation of configured data/environment/assets/EXEs. |
| Existing network/game/build contracts | Passed as part of the complete suite, including the prior Go/HOME source guard. |
| Packaged patch application | Extracted the actual hotfix ZIP and ran its Python installer on a disposable configured target. All three scripts matched the source, original scripts were backed up, reapplication was idempotent, and config/environment/save/EXE markers were unchanged. |
| Baseline preservation | **11,877 original files compared before source-manifest regeneration; 11,862 unchanged.** All Client files, server configuration, requirements, world content, world/combat logic and MySQL setup scripts remain byte-identical. Changed files are listed in the evidence JSON. |
| Package integrity | Hotfix and full source ZIP CRC checks passed; payload and full source SHA-256 manifests verified. |

## Environment and limits

Executed on **Linux x86_64, Python 3.12.14**, using available **aiohttp 3.13.5** and **cryptography 46.0.0**. PyMySQL, Go, Windows PowerShell and a native MySQL/MariaDB daemon were unavailable. The production dependency pins were preserved, not installed or revalidated.

The single skipped group is the existing native Windows PowerShell bootstrap test. Windows CMD/EXE execution and live MySQL/MariaDB acceptance were **not performed**. SQLite ownership tests exercise shared lifecycle/lease code but are not evidence of a live MySQL deployment test. No new Windows EXEs were built; both existing launcher methods load the corrected Python files at runtime.

The reproduced occupied-port failure demonstrates the original defect, not proof that the recipient's port was occupied. If the corrected server detects an actively refreshed lease, stop the other NXT world before retrying. If a different startup cause remains, the console and log now identify its stage and safe diagnostics.

## Evidence

- `evidence/world_startup_1.1.2_original_failure.json`
- `evidence/world_startup_1.1.2_unit_tests.txt`
- `evidence/world_startup_1.1.2_preservation.json`
- `evidence/world_startup_1.1.2_packaged_patch.json`

Historical build/test reports remain historical. For application instructions, use the hotfix ZIP's README or `Server/WORLD_STARTUP_FIX.md`.
