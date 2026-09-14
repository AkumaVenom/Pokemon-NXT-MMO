# Pokémon NXT MMO 0.3.6 — Local administrator console validation

**Historical report — corrected by build tools 1.4.1.** The subsequent user-supplied native Windows log for build 1.4.0 reports one temporary SQLite cleanup error (`WinError 32`) in the schema/lease regression. The Linux pass recorded below did not expose those open handles. This original evidence is retained, not relabelled as native Windows acceptance. See `WINDOWS_BUILD_FIX_1.4.1_TEST_REPORT.md` for the explicit-closure correction and new validation.

**Executed:** 2026-09-14. **Gameplay:** 0.3.6-alpha. **Build tools:** 1.4.0. **Pack:** `6d5c55ab09dc9ab7d17928b7`. **Storage schema:** 2.

The source basis is Akuma's explicitly accepted **0.3.5-alpha Pokémon Varieties / WindowsBuildFix, build tools 1.3.4**. This is the separate Pokémon NXT MMO client/server project, not Pokémon Vortex NXT. This report records executed checks; it is not native-Windows, live-MySQL or user acceptance of the new release.

## 1. Final executed results

| Check | Actual result |
|---|---|
| Final clean-source full build | **Passed**: `build-20260914-115101-043948Z`; 286.3 seconds after staging began |
| Python suite in the final clean build | **596 run: 595 passed, one native Windows PowerShell check skipped on Linux** |
| New admin-console and real-network modules | **70 passed** in a separate focused run |
| All new admin tests plus the previous variety tests with both link APIs denied | **102 passed, no skips**; includes all 32 variety tests |
| Combined eight JavaScript test scripts | **112 reported test units passed**, zero failures/skips |
| Both Go launcher packages | Host tests passed; both Windows-target static checks passed |
| Windows x64 outputs | Both cross-compiled; client GUI/server console PE headers verified; **not executed on Windows** |
| Actual Linux-built client launcher HTTP smoke checks | **26 passed** |
| Actual server subprocess / terminal lifecycle | **Six recorded checks passed** using POSIX PTY and a separate rejected pipe |
| Two-account Chromium variety regression | **12 recorded checks passed**, no page errors |
| Two-account Chromium Cut regression | **Five recorded checks passed**, no page errors |
| ROM-free content publication | Matching server/client pack `6d5c55ab09dc9ab7d17928b7` |
| Original asset preservation | **17,179 original PNG/audio files byte-identical**; no original source path removed |

The combined JavaScript count includes one audio-engine script which separately reports 34 internal checks. Those 34 are not added again to the 112 count. The ordinary all-in-one build runs the same scripts in separate groups.

The final developer-mode build ran `python Build/build.py --existing-environment --no-open`. It selected a clean source tree, republished the content pack, ran the Python and JavaScript suites, ran both Go package tests and Windows-target checks, cross-compiled and inspected the launchers, completed the real launcher HTTP checks, verified the generated distribution archives and published a fresh output folder. The downloadable four-part release is **source-only**, not those generated executable distributions.

The separately rerun no-link test patched **both `os.symlink` and `os.link` to raise `PermissionError`** while executing all 70 new admin tests and all 32 existing variety tests. All 102 ran and passed in 70.633 seconds. The previously accepted link-free variety fixture remains byte-identical. No elevation, Developer Mode, junction or hard-link requirement was added to these new tests.

## 2. Local authority, parser and policy checks

The new tests exercise exact argument counts and quoting, optional console-only slash syntax, aliases, control-character rejection, invalid numbers, line/token bounds, duplicate command names, dynamic help, developer gating and per-command disable lists. Every alias resolves to its canonical policy, so aliases cannot bypass a disabled command. The registry/manual/version/source-selection consistency checks pass.

Game clients cannot invoke the console via chat text, a fabricated command packet or a forged rank. There is no admin listener, HTTP endpoint or RCON service. Actual network tests run the production aiohttp service rather than only calling command helpers. Player packet handling, existing chat and account/connection privacy remain separately tested.

Redirected stdin is rejected. The bounded reader reserves capacity before scheduling loop callbacks; tests verify burst order, bounded queues/callbacks, overlong-line draining, EOF behavior and cancellation without waiting on a blocking `readline`. The input thread does not mutate world state. Existing World locking and database fencing serialize edits with gameplay.

## 3. Mutations, persistence, rollback and race checks

The 70 new tests cover, among other cases:

- Exact username/account-ID targeting; owned UID/party-slot selection; ambiguous catalogs; collection, inventory and currency bounds; all six variety grants; PC overflow; no duplicate ownership IDs; and last-healthy-party protection.
- Native level/EXP thresholds, IV order, nature/stat changes, preserving damage/fainting, move queues and chosen slots; authored move learning/evolution and required stone use; party healing and atomic healall with explicit busy-session skips.
- Offline edits and cold persistence; unchanged regional badges/personal Cut/variety identity; private owner updates and public follower identity changes; safe teleport rejecting walls, water and warps; and all real HM-tree cells retaining per-player collision.
- Single-use expiring confirmation, cancellation, disabled-policy rechecks, stale character snapshots and replaced sessions. Invalid or stale previews do not write.
- Character changes and successful audit inserts in one transaction; failure-injected character/audit/control/password/account creation writes; pre-commit file-audit denial; post-commit audit/presentation failure reporting without false rollback; newer-revision conflicts and the world lease fence.
- Cancellation during an admitted transaction; serial concurrent commands; a failed grant followed by a successful retry yielding exactly one new Pokémon.
- Durable warnings, timed/permanent bans, independent locks, freeze/unfreeze, trade restrictions and active-offer cancellation. Passwords are generated and displayed once locally only after successful commit, not logged or accepted as command arguments.
- Real authentication races against lock, ban and password reset; admission revalidates controls and the verified hash before publishing a session. Offline edits cannot be overwritten by a stale login snapshot.
- Developer opt-in and cloned test duels. Test win/loss/end cannot finish ordinary battles or create real captures, EXP, money, item use or gym progression.
- Restricted config reload, stale file previews, confirmed shutdown/restart schedules, cancellation and explicit clean-restart exit-code behavior.

The source proposal is audited row by row: **148 proposal rows**, with **85 adapted to the local console, 18 communication rows excluded and 45 unsupported rows deferred**. These are proposal-row counts, not installed-command counts: overloaded rows/aliases converge, and NXT-specific helpers are added. The installed registry contains **81 canonical commands, 21 aliases, ten developer-gated commands and 30 confirmation-gated commands**.

## 4. Schema-2 upgrade checks

SQLite fixtures exercise additive migration from a schema-1 database while preserving existing accounts, password hashes, character snapshots, trades and existing bans. The new indexed control/audit tables are installed without resetting characters. A recent or future-clock old-world lease rejects the upgrade **before** adding those tables or advancing the schema marker. A safe error explains clean shutdown/lease expiry rather than exposing a database driver's raw exception payload.

The MySQL SQL/transaction path and existing setup grants were inspected and share the same store contracts, but **no live MySQL or MariaDB server was exercised in this environment**. MySQL DDL has different transactional behavior from SQLite; a failed upgrade must be inspected and repaired before starting, not treated as proof of a rolled-back schema. The marker is advanced only after required steps complete, and unsupported schema versions still fail closed.

**Back up the configured server and database before deploying.** The old schema-1 server deliberately rejects a schema-2 database. Rollback needs the pre-upgrade database backup and matching old deployment; never manually decrease the schema version or delete control/audit tables to bypass the check.

## 5. Actual console-process checks

`Tests/check_admin_console_process.py` starts real `server.py` subprocesses with a temporary SQLite database. On this Linux host, the terminal path used a POSIX pseudo-terminal, not a direct call to the command executor. It typed a variety grant, confirmed a variety edit, verified the saved offline state and rejected developer/chat commands. A confirmed timed shutdown exited 0 and released its lease while the reader remained blocked. A new startup succeeded immediately; confirmed restart exited **75 only after clean shutdown**. A separate process with piped stdin executed neither its supplied grant nor its supplied shutdown; an OS SIGTERM then shut it down normally.

The fixture verified that only the four actually executed terminal actions entered its transaction audit, with no piped mutation or password leak. This optional test uses `pexpect` on POSIX; `pexpect` is a test dependency, not a new server/build dependency. Windows launcher control flow has Go tests and cross-compilation coverage, but native Windows terminal/console behavior remains a deployment check.

## 6. Browser regressions and boundaries

The two browser fixtures used Chromium **144.0.7559.96**, the actual shipped client, production aiohttp service and disposable SQLite accounts. Because native container loopback browser navigation is restricted, they used the explicit existing **`NXT_QA_BRIDGE=1` DOM/asset/real-service transport bridge**. This is not native Edge, Windows input/audio-device, TLS-client or MySQL acceptance, and no bridge is enabled in the shipped production server by this change.

The variety fixture covers collection filtering, same-species Normal-to-Ancient switching, correct front artwork on both sides for all six identities, mirrored player attack/hit transforms, unmirrored opponents, regular follower icons and peer-replicated variety effects, reduced-motion markers, a real item-selector Shadow capture, UUID/variety persistence and fresh-page account-isolated login.

The Cut fixture covers both Kanto and Johto's real canvas tree interaction, enabled/locked menus, committed owner-only disappearance, keyboard pass-through for the owner versus a blocked peer and fresh-page restoration. Browser errors were empty in both final result files. Representative Shadow-battle and locked-Johto-tree screenshots were visually inspected for readable controls, correct sprite orientation and preserved layout.

A race in the **browser test's observation** was corrected: the fixture previously waited for a tree hit record, then read the renderer's transient hit array in a second browser call. It now captures coordinates in the same successful wait. The game renderer was not altered. The old optional `ui_acceptance.py` fixture was also updated to use the maintained variety/Cut checks instead of relying on obsolete piped admin commands; no production pipe exception was added.

## 7. Preservation and source packaging

The uploaded/accepted baseline's four archives were reconstructed and every one of their **18,455 entries** verified before editing. The completed update preserves every original source path. All **14,813 baseline PNGs** (14,807 game images plus six documentation screenshots) and **2,366 audio files** are byte-identical. The world JSON differs only in its top-level gameplay version and matching pack ID; species, maps, move definitions, encounter tables, variety policy and artwork bindings are unchanged.

The original combat/growth/encounter/variety/personal-Cut modules, player-side front-sprite rendering, client styles, follower effects and the link-free `test_varieties.py` are unchanged. Changes in world/store/server code integrate administration with their existing locking, saving and admission paths; all their prior regression suites ran again. No new artwork is generated.

Runtime dependency pins and the official toolchain download versions/hashes are unchanged. Only the bootstrap revision is advanced. Release source snapshots retain source/assets/docs but omit live configuration files, databases, private keys, audit logs, tool environments, compiled programs and previous build outputs. Their runnable configuration files are hydrated from the clean release templates; preserve deployed private configurations rather than copying those clean templates over them.

`SOURCE_SHA256SUMS.txt` covers the completed clean source, excluding only itself. The separate `Pokemon_NXT_v0.3.6_Download_Verification.json` records the final four ZIP sizes, whole-archive hashes and exhaustive per-entry verification, including the source manifest. All four are required and merge into one project folder; they are ordinary ZIPs, not byte-split parts. Final documentation/evidence/manifest completion after the last full build changes no tested executable source or gameplay data.

## 8. Reproduction and native acceptance

Normal Windows users should run **`BUILD_ALL.bat`**, not copy the developer-mode command below. That standard path manages its pinned build environment.

```sh
python -m unittest discover -s Tests -v
python -m unittest discover -s Tests -p 'test_admin_*.py' -v
node --test Tests/check_audio_engine.mjs Tests/check_audio_app_integration.mjs Tests/check_registration.mjs Tests/check_renderer_replication.mjs Tests/check_adventure_ui.mjs Tests/check_learnsets.mjs Tests/check_battle_fx.mjs Tests/check_varieties.mjs
python Build/build.py --existing-environment --no-open
```

Environment for the reported developer build: **Python 3.13.5, Node v22.16.0, Go 1.23.2 linux/amd64, aiohttp 3.13.3, cryptography 46.0.4**. PyMySQL is not installed here. `--existing-environment` explicitly records that production dependency pins are **not installed or asserted**. This does not change or bypass the normal Windows build's requirement pins/tests.

On a backed-up deployment, stop the old server, build and deploy matching new Client/Server, retaining the working configuration/certificates/database. In a normal Windows terminal verify the `NXT>` help prompt and a disposable account's grant, party/PC listing, confirmed edit, save/relog and clean restart. Test online/offline targeting, expired/reused/stale confirmation, account lock/ban/password-reset behavior and the OS host's audit-file permissions. Check a second game client cannot execute administrative packets or alter another owner's data. Repeat regional Cut, varieties/mirrored battle/followers, trade and persistence checks. Verify live MySQL schema migration and restart separately before treating that backend as accepted. The test suite is not a claim of 1,000-session capacity, a full campaign playthrough or user approval of this release.
