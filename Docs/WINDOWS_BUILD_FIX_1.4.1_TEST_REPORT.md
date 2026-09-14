# Pokémon NXT MMO — Windows console-build repair verification

**Date:** 2026-09-14 · **Gameplay:** 0.3.6-alpha · **Build tools:** 1.4.1 · **Schema:** 2 · **Pack:** `6d5c55ab09dc9ab7d17928b7`

## Reported failure and actual reproduction

The user's `build-20260914-122114-117629Z.log` finished dependency installation/checks, published the existing pack and passed syntax validation. Of 596 tests, one errored: temporary-directory cleanup after `test_schema_upgrade_refuses_recent_or_future_old_world_lease` could not delete `development.sqlite3` on Windows (`WinError 32`). Ten privilege-dependent tests were skipped on that Windows host. The bootstrap transcript completed normally.

The test's four raw SQLite connection sites create six probe connections because two sites run once for each heartbeat case. A bare `with sqlite3.connect(...)` transaction context did not close them. Python's documented connection context commits/rolls back but does not close the handle. The production Store's failed-constructor and normal-close paths already close their handles explicitly.

The original actual test was executed here with a real SQLite connection subclass and all handles held by strong references until inspection: **10 opened, four explicitly closed, six left open**. Its Linux test result was misleadingly `OK` because the temporary file could be unlinked there. This is a deterministic reproduction of the handle leak, not a claim that Linux reproduced native WinError 32.

After correction, the same retained-handle check reports **10 opened, ten explicitly closed, zero leaks**. The four unit-fixture and three supplementary process-fixture sites now use `with closing(sqlite3.connect(...)) as conn, conn:`. This retains the original transaction behavior and closes the handle after successful work, failed work or failed transaction exit. No GC workaround, ignored cleanup exception, elevated permission, schema-guard removal or disabled test is involved.

## Executed results

| Check | Result |
|---|---|
| Full clean developer build | **Passed**, `build-20260914-123722-358062Z`; 266.7 seconds after staging began |
| Python suite inside clean build | **600 run: 599 passed, one Windows-specific test skipped on Linux** |
| New mandatory lifetime regressions | **Four passed**, including real fixture, read failure, transaction-exit failure and source/probe contracts |
| Supplementary complete suite with retained SQLite handles and both link APIs denied | **600 run: 589 passed, 11 existing platform/link-dependent tests skipped, zero errors/failures** |
| Explicit handle inspection in that supplementary full suite | **315 real connections inspected; zero open at their test's completion**, with references retained to prevent GC masking |
| JavaScript in full build | **112 reported test units passed**: 103 client/core/variety tests, eight audio-application tests, one audio-engine script (34 internal checks) |
| Go launcher tests and Windows-target static checks | **Passed** for both launcher packages |
| Windows x64 executables | Both cross-compiled; client GUI and server console PE headers verified; **not executed on Windows** |
| Actual Linux-built launcher HTTP checks | **26 passed** |
| Actual server subprocess / terminal / pipe checks | **Six passed**, using POSIX PTY and a separate pipe-rejection process |
| Original source checksum manifest | **18,467 listed entries verified** against the original four-part release before editing |

The corrected schema/lease test and all 32 variety tests remain active in both full-suite runs. The ordinary build's one skip is the native Windows PowerShell helper. The deliberately link-denied supplementary run also skips the ten pre-existing tests that require creating actual filesystem links. None of the four new lifetime regressions is skipped. Real SQLite is used; the inspector retains connections, probes closure before any emergency test cleanup, and records a failure if a handle remains open.

The process test actually starts `server.py`, grants a variety, performs a confirmed change, rejects a developer alias by default, rejects an absent chat command, completes timed shutdown (exit 0) and confirmed restart (exit 75), preserves durable state and releases its lease. Piped stdin does not execute grants/shutdown; ordinary OS termination still closes cleanly. Only the four successful terminal mutations enter the database audit. No operator database is used.

## Supplemental rerun transparency

An initial instrumented/link-denied suite ran while the clean build and optional process QA were also running. It found **no connection leaks**, but the unchanged twelve-account concurrent reconnect test reached its existing six-second `joined`-packet deadline once. That attempt is not counted as a pass. After the clean build finished, the **entire unchanged instrumented suite was rerun sequentially and passed** as shown above. No timeout, assertion, networking implementation or test-selection rule was weakened. This does not establish the reason for the transient timeout; the overlap is recorded as context. The ordinary clean build itself passed that reconnect test.

## Preservation and source packaging

Every original source path remains. All Client, Server and Tools files are byte-identical to the supplied v0.3.6 release, including world/store/console implementations, client rendering, encounter/variety data, imported sprites and audio. Gameplay version, pack, schema, dependency pins and official Python/Go download versions/checksums are unchanged. Only the build revision, two fixture files, new regression module, source requirements and documentation/manifest change.

The four complete corrected source ZIPs contain one combined editable source tree. `SOURCE_SHA256SUMS.txt` covers every source entry except itself. The external `Pokemon_NXT_v0.3.6_ConsoleBuildFix_Download_Verification.json` records per-archive hashes, per-entry checksum verification, exact changes, preserved asset counts and the small repair's actual application to a fresh extraction of the old four-part source. That check also reapplies the repair and verifies that simulated private configuration/database/key/log/environment/output files remain unchanged. The repair is a plain overlay, not a conflict-aware application script; back up locally modified source before merging it.

Build metadata and code tests were completed before the final documentation/evidence and source manifest were assembled. Those final reporting changes do not modify tested executable source or content. Historical v0.3.6 evidence remains identified as historical, not relabelled as native Windows validation. Complete executable distributions produced for verification are not these source downloads.

## Environment and boundaries

Linux x86_64; Python **3.13.5**; Node **v22.16.0**; Go **1.23.2**; aiohttp **3.13.3**; cryptography **46.0.4**; pexpect **4.9.0**. PyMySQL is not installed here. `python Build/build.py --existing-environment --no-open` is the documented developer-mode build: it runs syntax, tests, compilation and packaging, but does **not** install or assert production Python dependency pins. The normal Windows `BUILD_ALL.bat` path still manages its unchanged pinned environment.

Native Windows executables, PowerShell bootstrap execution on Windows, native Edge gameplay and live MySQL were not tested in this repair session. No browser screenshots or fresh browser acceptance are claimed; client/runtime bytes are unchanged and the complete Python/network/JavaScript regressions were rerun. Prior browser reports are historical only. SQLite tests do not establish live MySQL persistence.

Use `BUILD_ALL.bat` on Windows and confirm the banner reads **1.4.1 / 0.3.6-alpha**. For deployment, retain the existing v0.3.6 schema-2 backup/stop-old-world procedure and preserve working settings, credentials, database and certificates. There is no additional schema migration or credential change in this repair. Do not delete the live database to address a disposable test-file error.

## Reproduction

```sh
python -m unittest Tests.test_sqlite_lifecycle -v
python -m unittest discover -s Tests -v
python Tests/check_admin_console_process.py --output console-process.json
python Build/build.py --existing-environment --no-open
```

The process command is POSIX-only supplementary QA with pexpect, not an added Windows runtime prerequisite. Windows users should use the normal BAT rather than the developer build command. The mandatory lifetime regressions run on Windows and Linux without filesystem-link privileges. Machine-readable executed results are in `WINDOWS_BUILD_FIX_1.4.1_EVIDENCE.json`.

Official SQLite connection-context reference: https://docs.python.org/3/library/sqlite3.html#how-to-use-the-connection-context-manager
