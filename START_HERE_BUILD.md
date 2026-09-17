# Pokemon NXT MMO — automatic all-in-one source build


**Download all FOUR source ZIPs:** `Pokemon_NXT_MMO_v0.6.8-alpha_Source_GbaBattleSystemCompletion_AutonomousBattleHotfix_Part1.zip`, `Part2.zip`, `Part3.zip` and `Part4.zip` (all share the same prefix). Extract each ordinary ZIP into the same destination, merging the identically named `Pokemon_NXT_MMO_v0.6.8-alpha_Source_GbaBattleSystemCompletion` folders. Do not concatenate the ZIP files. Run `BUILD_ALL.bat` only after all four parts are extracted. The four parts contain the complete source and assets; no earlier source pack or optional patch is required.

Gameplay **0.6.8-alpha** · Build tools **1.4.1** · Online setup **1.2.2** · MySQL setup **1.1.0** · World startup fix **1.1.2**

The full source includes the extracted FireRed and Sigma music, sound effects and cries. `BUILD_ALL.bat` verifies and packages these files; it does not extract them again. **No ROM, FFmpeg or C++ audio-renderer build is needed for a normal build.**

## GBA battle system completion · 0.6.8-alpha

The authoritative singles battle runtime now consumes the bundled ROM-audited battle metadata for all **354 canonical FireRed moves plus 7 reviewed Sigma aliases**. All 361 published moves are executable through the same server turn resolver; the active effect corpus covers 198 source effect IDs. The release adds exact reviewed handling for important Gen-III edge cases such as Psywave, Present, OHKO thresholds, lower-level wild Roar/Whirlwind, copy/call restrictions, Protect/Endure chaining and terrain-driven Nature Power/Secret Power/Camouflage.

The supplied FireRed/Sigma ROMs are **not required for a normal build and are not included**. `Server/data/battle_mechanics.json` contains the reviewed generated metadata and provenance. This remains a server-authoritative single-battle MMO rather than a cycle-perfect cartridge emulator; explicit limitations are documented in `Docs/GBA_BATTLE_SYSTEM.md`, with executed validation in `Docs/GBA_BATTLE_SYSTEM_TEST_REPORT.md`. No SQL schema bump, player reset or bot reset is required.

## Kanto / FireRed NPC dialogue restoration · 0.6.7-alpha

Ordinary Kanto NPC clicks now use **642 validated static talk literals** recovered from the exact reviewed FireRed Rev 1 ROM. The extraction audit covers all 1,620 visible FireRed object events and limits publication to 669 ordinary person-NPC objects, excluding trainers/Gym Leaders and non-regular item/Pokémon/field actors. Trainer/Gym interactions still show their existing NXT party preview; Pokémon Center nurses and Poké Mart clerks keep their authoritative service actions.

The FireRed ROM is **not required for a normal build and is not included in these ZIPs**. The bundled `Server/data/kanto_dialogue.json` is provenance-checked and merged with the preserved Johto/Sigma dialogue sidecar during content publication. No database schema or save migration is added by 0.6.7. See `Docs/KANTO_FIRERED_NPC_DIALOGUE.md` and its test report.

## Johto / Sigma NPC dialogue restoration · 0.6.6-alpha

**Corrected source bundle:** native Windows build validation found one stale 0.6.5 release-audit value in the first 0.6.6 source package. This corrected bundle aligns the admin proposal audit and `BUILD_ALL.bat` banner with 0.6.6 and adds a regression for the banner. No gameplay/content/save/schema behavior changed.

Ordinary Johto / Sigma NPC clicks now display **2,158 validated static talk literals** recovered from the exact reviewed Sigma ROM, covering all safe bindings discovered across the 534-map source set. Trainers and Gym Leaders remain on NXT's existing party-preview/challenge UI; Nurse Joy and Poké Mart services keep their authoritative actions; Cut and the Route 36 Sudowoodo story object remain dedicated interactions. The extractor never executes ROM code and objects without a safely established literal keep the existing fallback.

The ROM is **not required for a normal build and is not included in these ZIPs**. The bundled `Server/data/johto_dialogue.json` is verified and published into the world pack automatically. No database schema or save migration is added by 0.6.6. See `Docs/JOHTO_SIGMA_NPC_DIALOGUE.md` and its test report.

## Route 36 Sudowoodo story gate · 0.6.5-alpha

Johto Route 36 now has an authoritative personal story blocker on the existing odd-tree object. The tile remains blocked for each character until that character has earned Whitney's Plain Badge, received the saved SquirtBottle Key Item, used it on the nearby odd tree, and then defeated or captured the resulting Lv. 20 Sudowoodo. A successful battle persists `johto_sudowoodo` before the client is told the path is clear; running, losing or a failed database commit leaves the blocker intact. Another account's completion never changes your collision or sprite visibility.

NXT grants the SquirtBottle immediately when the Plain Badge is first recorded, because the MMO does not execute the original games' full Flower Shop/Floria event-script chain. Existing characters that already own the Plain Badge receive the Key Item additively on their next validated login. The SquirtBottle is unique, non-buyable, non-tradable and not consumed by the encounter. No database reset or schema change is required.

This release is built directly on the accepted 0.6.4 long-uptime autonomous-performance baseline. No bot count, bot behavior, battles, captures, evolution, travel, ranking or persistence feature has been removed or slowed. See `Docs/ROUTE36_SUDOWOODO.md` and its executed test report.

## Windows build repair · 1.4.1

**Windows build correction (1.4.1):** Explicitly close temporary SQLite probe connections; this fixes the reported `WinError 32` in the schema/lease regression without disabling it or changing the server. See `Docs/WINDOWS_BUILD_FIX_1.4.1.md` and its test report. That historical repair remains preserved; current gameplay uses schema 3 and the current 0.6.8 content pack.

## Autonomous trainer performance hardening · 0.6.4-alpha

This release keeps the full 2,000-trainer feature set but removes the database amplification that could make every bot appear to freeze together after sustained uptime. The single leased world now treats its in-memory autonomous population as authoritative between explicit recovery/reconciliation operations. Normal 10 Hz world ticks no longer reload and JSON-decode all bot rows, off-screen field outcomes are committed as one bounded batch, ranked due/candidate selection runs against the authoritative memory image with one recent-opponent query and one batched commit, and visible field outcomes share a single transaction per world tick. AI Activity retention cleanup is throttled to once per hour instead of running a delete on every recorded bot action.

No bots, battles, captures, evolutions, regional travel, ranking, rivals, activity feeds or materialized-map behavior were removed or reduced. The existing 0.6.3 level-evolution contract is preserved. Schema 3 remains authoritative; startup adds the supporting activity index idempotently and requires no reset. See `Docs/AUTONOMOUS_PERFORMANCE.md`, `Docs/AUTONOMOUS_PERFORMANCE_TEST_REPORT.md`, `Docs/AUTONOMOUS_TRAINERS.md` and the preserved evolution/travel documentation.

Start the built world server as usual, then type `help` in its interactive terminal. All administration stays on the host; player chat and game packets cannot invoke commands. **No new port or administrator password is needed.** Administrative writes and their audits are transactional, destructive previews need confirmation, and developer commands are disabled by default. See `Docs/LOCAL_ADMIN_CONSOLE.md`.

Back up the existing database before this update. Schema 3 remains authoritative and this gameplay update requires no new schema bump. Existing human accounts, autonomous identities, Pokémon, ratings, rivalries and histories are upgraded in place.

The earlier **build-tools 1.3.4 Windows symlink-privilege correction remains included**. Its isolated sprite-copy tests stay active. Current gameplay is **0.6.8-alpha**, build tools **1.4.1**, with a newly published matching content pack. Historical repair instructions are in `Docs/WINDOWS_BUILD_FIX_1.3.4.md`; do not apply that old repair over this complete release.

## Varieties and regional encounter/Cut updates

Version 0.3.5 adds five persistent cosmetic varieties, server-controlled rarity, collection/dex presentation and replicated follower sparkles. All player-side battle Pokémon use horizontally flipped front sprites. Read `Docs/POKEMON_VARIETIES.md` and its test report for the full 251-species coverage and additional-form limits. The supplied converted fronts are already included; no images.rar, Pillow, image converter, new art download or back-sprite collection is needed for a normal build.

The accepted 0.3.4 FireRed/Crystal encounter resolver and independent regional Cut licenses remain: Misty/Cascade for Kanto and Bugsy/Hive for Johto. Personal tree clearing remains saved per character. See `Docs/REGIONAL_ENCOUNTERS_AND_CUT.md`. Old release guides describe their historical package counts; this 0.6.8 source is supplied in **four** parts.

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
