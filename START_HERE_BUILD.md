# Pokemon NXT MMO — automatic all-in-one source build


**Download all FOUR source ZIPs:** `Pokemon_NXT_MMO_v0.6.5-alpha_Source_Route36SudowoodoStory_Part1.zip`, `Part2.zip`, `Part3.zip` and `Part4.zip` (all share the same prefix). Extract each ordinary ZIP into the same destination, merging the identically named `Pokemon_NXT_MMO_v0.6.5-alpha_Source_Route36SudowoodoStory` folders. Do not concatenate the ZIP files. Run `BUILD_ALL.bat` only after all four parts are extracted. The four parts contain the complete source and assets; no earlier source pack or optional patch is required.

Gameplay **0.6.5-alpha** · Build tools **1.4.1** · Online setup **1.2.2** · MySQL setup **1.1.0** · World startup fix **1.1.2**

The full source includes the extracted FireRed and Sigma music, sound effects and cries. `BUILD_ALL.bat` verifies and packages these files; it does not extract them again. **No ROM, FFmpeg or C++ audio-renderer build is needed for a normal build.**

## Route 36 Sudowoodo story gate · 0.6.5-alpha

Johto Route 36 now has an authoritative personal story blocker on the existing odd-tree object. The tile remains blocked for each character until that character has earned Whitney's Plain Badge, received the saved SquirtBottle Key Item, used it on the nearby odd tree, and then defeated or captured the resulting Lv. 20 Sudowoodo. A successful battle persists `johto_sudowoodo` before the client is told the path is clear; running, losing or a failed database commit leaves the blocker intact. Another account's completion never changes your collision or sprite visibility.

NXT grants the SquirtBottle immediately when the Plain Badge is first recorded, because the MMO does not execute the original games' full Flower Shop/Floria event-script chain. Existing characters that already own the Plain Badge receive the Key Item additively on their next validated login. The SquirtBottle is unique, non-buyable, non-tradable and not consumed by the encounter. No database reset or schema change is required.

This release is built directly on the accepted 0.6.4 long-uptime autonomous-performance baseline. No bot count, bot behavior, battles, captures, evolution, travel, ranking or persistence feature has been removed or slowed. See `Docs/ROUTE36_SUDOWOODO.md` and its executed test report.

## Windows build repair · 1.4.1

**Windows build correction (1.4.1):** Explicitly close temporary SQLite probe connections; this fixes the reported `WinError 32` in the schema/lease regression without disabling it or changing the server. See `Docs/WINDOWS_BUILD_FIX_1.4.1.md` and its test report. That historical repair remains preserved; current gameplay uses schema 3 and the 0.6.5 content pack.

## Autonomous trainer performance hardening · 0.6.4-alpha

This release keeps the full 2,000-trainer feature set but removes the database amplification that could make every bot appear to freeze together after sustained uptime. The single leased world now treats its in-memory autonomous population as authoritative between explicit recovery/reconciliation operations. Normal 10 Hz world ticks no longer reload and JSON-decode all bot rows, off-screen field outcomes are committed as one bounded batch, ranked due/candidate selection runs against the authoritative memory image with one recent-opponent query and one batched commit, and visible field outcomes share a single transaction per world tick. AI Activity retention cleanup is throttled to once per hour instead of running a delete on every recorded bot action.

No bots, battles, captures, evolutions, regional travel, ranking, rivals, activity feeds or materialized-map behavior were removed or reduced. The existing 0.6.3 level-evolution contract is preserved. Schema 3 remains authoritative; startup adds the supporting activity index idempotently and requires no reset. See `Docs/AUTONOMOUS_PERFORMANCE.md`, `Docs/AUTONOMOUS_PERFORMANCE_TEST_REPORT.md`, `Docs/AUTONOMOUS_TRAINERS.md` and the preserved evolution/travel documentation.

Start the built world server as usual, then type `help` in its interactive terminal. All administration stays on the host; player chat and game packets cannot invoke commands. **No new port or administrator password is needed.** Administrative writes and their audits are transactional, destructive previews need confirmation, and developer commands are disabled by default. See `Docs/LOCAL_ADMIN_CONSOLE.md`.

Back up the existing database before this update. Schema 3 remains authoritative and this gameplay update requires no new schema bump. Existing human accounts, autonomous identities, Pokémon, ratings, rivalries and histories are upgraded in place.

The earlier **build-tools 1.3.4 Windows symlink-privilege correction remains included**. Its isolated sprite-copy tests stay active. Current gameplay is **0.6.5-alpha**, build tools **1.4.1**, with a newly published matching content pack. Historical repair instructions are in `Docs/WINDOWS_BUILD_FIX_1.3.4.md`; do not apply that old repair over this complete release.

## Varieties and regional encounter/Cut updates

Version 0.3.5 adds five persistent cosmetic varieties, server-controlled rarity, collection/dex presentation and replicated follower sparkles. All player-side battle Pokémon use horizontally flipped front sprites. Read `Docs/POKEMON_VARIETIES.md` and its test report for the full 251-species coverage and additional-form limits. The supplied converted fronts are already included; no images.rar, Pillow, image converter, new art download or back-sprite collection is needed for a normal build.

The accepted 0.3.4 FireRed/Crystal encounter resolver and independent regional Cut licenses remain: Misty/Cascade for Kanto and Bugsy/Hive for Johto. Personal tree clearing remains saved per character. See `Docs/REGIONAL_ENCOUNTERS_AND_CUT.md`. Old release guides describe their historical package counts; this 0.3.6 source is supplied in **four** parts.

## Battle screen correction

Version 0.3.3 corrects browser timer context and opens the battle dialog before animations start. An animation failure returns control to the normal battle UI. Attack motion, damage/effectiveness text and cancellation of stale sounds are retained. See `Docs/BATTLE_SCREEN_FIX.md` and `Docs/BATTLE_FEEDBACK.md`. Build and deploy matching Client and Server, retaining your existing database, configuration and certificates.

## Native learnsets update

Read `Docs/LEARNSET_GUIDE.md` for native move levels and the Move Reminder. Cyndaquil learns Ember at level 12 in both supplied ROMs. Existing characters keep progress and chosen moves; invalid queued choices are reconciled on login. Deploy matching new Client and Server packs.

## Adventure update

Read `Docs/ADVENTURE_GUIDE.md` for trainer/badge progression, Nurse Joy healing, PC storage, evolution and move learning. Interior destinations and recovered Sigma rooms use audited ROM metadata. Older configured worlds should set `[world] allow_alpha_atlas = false` and `allow_alpha_surf = false` for progression gates; fresh templates already do. Keep your working database, config and TLS files.

## Starter, login and progress fixes

This release keeps starter choice independent of starting region, fixes account/session retry races and saves progress on the server automatically. Fresh server configurations use a five-second movement checkpoint interval; important gameplay changes commit before success. Read `Docs/REPLICATION_FIX_1.2.3.md` before upgrading a configured world. No account reset or character-specific repair is included.

## Correction for the Go prerequisite error

Build tools **1.4.1** retain the correction for `Cannot overwrite variable HOME because it is read-only or constant`. Two Go helper functions used a directory variable named `$home`, which collides with PowerShell's built-in `$HOME`. Both directory variables have been renamed, including the SDK check that previously rejected valid Go installations.

Extract all four complete ZIPs into the same new destination and run its `BUILD_ALL.bat`. The banner should say **1.4.1**. Your existing compatible Python and verified tool downloads can be reused; reinstalling Python, changing Windows HOME, or changing MySQL settings is unnecessary. See `Docs/AUTO_BUILD_1.1.1_TEST_REPORT.md` for the original correction's validation scope and `Docs/AUDIO_TEST_REPORT.md` for the audio validation and `Docs/REPLICATION_TEST_REPORT.md` for this release.

## Online server fails because TLS files are missing?

In the built Server folder, run **`2b - Configure Online Hosting.cmd`**. Enter the public IP/domain players will use and create a certificate/key pair, or import your existing pair. This preserves MySQL settings. Give players the generated public connection kit and follow **`Docs/ONLINE_HOSTING.md`** for trust, client settings and TCP port forwarding. A certificate alone cannot configure your router.

## Already built and configured the server?

World startup fix **1.1.2** is already incorporated in this source. It releases this server's lease on failed startup, records early failures at the absolute log path printed in the console, and waits briefly for a recent abandoned lease. It still protects a running world that owns the database. See `Server/WORLD_STARTUP_FIX.md`.

For the adventure upgrade, build a fresh output and deploy its **matching Client and Server**. Back up the configured server before replacing program files; carry forward its existing `config.ini`, database and required private deployment files. Preserve the client's connection settings too. Do not copy release config templates over your working settings or run MySQL setup again just to install this release. The old scripts-only startup hotfix is not an audio updater. Detailed steps are in `Docs/AUDIO_GUIDE.md`.

## Build it

Extract **all four entire** source ZIPs to a short writable local folder, such as `C:\Dev\PokemonNXT`, connect to the internet and double-click **`BUILD_ALL.bat`**. Do not launch the BAT from inside the ZIP. Use a normal Windows 10/11 x64 user session; Run as administrator is not needed.

**You do not need to install Go or Python manually.** The BAT starts with built-in Windows PowerShell, finds usable tools and automatically downloads/installs missing tools. It continues through Python package installation, tests, compilation and packaging without another manual build step. No winget, Chocolatey, Git, Node.js, Visual Studio or ROM is required.

## What it installs

Missing Go is downloaded as a verified official Windows x64 ZIP into your private user tool cache. Missing Python uses the verified official full x64 installer for your Windows user, including pip, virtual environments and Tk support for the corrected MySQL password window. Python's normal installer registers the per-user installation, but no permanent PATH changes or file associations are made. Neither tool is bundled as an offline installer in this ZIP.

The build driver creates or repairs `.build/venv` and installs the exact project requirements into it. Compatible installed tools and verified cached downloads are reused. Existing configured deployments, source gameplay files and previous successful builds are not overwritten.

## Your output

A successful run opens `dist/build-<timestamp>`. Its `Client` and `Server` folders are separate; distribution ZIPs are under `Packages`. `dist/LATEST_BUILD.txt` records the latest successful folder. The console stays open on success or failure. Logs are in `.build/logs`, with prerequisite logs named `bootstrap-*.log`.

The first build needs internet. A blocked download, invalid signature/hash or failed test stops safely with a visible error. Correct the reported issue and run the same BAT again; valid cached downloads are retained.

## Start the world afterward

Building does **not** install MySQL, create a database, change root's password, alter another game or launch the world. Follow `Docs/QUICK_START.md` in the new output. Its server dependency BAT recognizes the automatically installed Python on the same PC even without PATH or `py.exe`. A server-only deployment on a different PC still needs its own full Python runtime.

The MySQL password-entry correction is preserved: editable password boxes and a Show passwords option. Its administrator field means the **existing MySQL password**, not a new root password. See `Server/MYSQL_SETUP_FIX.md`.

See `Docs/AUTOMATIC_BUILD.md` for cache locations, official download pins and safe reruns, `Docs/BUILD_FROM_SOURCE.md` for the complete workflow, and `Docs/AUDIO_TEST_REPORT.md` for current test scope. `Docs/AUDIO_GUIDE.md` explains the sound mixer and source-specific audio limitations.
