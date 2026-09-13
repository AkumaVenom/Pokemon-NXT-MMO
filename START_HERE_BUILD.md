# Pokemon NXT MMO — automatic all-in-one source build


**Download both ZIPs:** `Pokemon_NXT_v0.3.3_Full_Source_Part1.zip` and `Pokemon_NXT_v0.3.3_Full_Source_Part2.zip`. Extract both into the same destination so their project folders merge. Together they contain the complete source and all assets. Run `BUILD_ALL.bat` after both parts are extracted. No earlier pack, audio conversion or ROM is needed.

Gameplay **0.3.3-alpha** · Build tools **1.3.3** · Online setup **1.2.2** · MySQL setup **1.1.0** · World startup fix **1.1.2**

The full source includes the extracted FireRed and Sigma music, sound effects and cries. `BUILD_ALL.bat` verifies and packages these files; it does not extract them again. **No ROM, FFmpeg or C++ audio-renderer build is needed for a normal build.**

## Battle screen correction

Version 0.3.3 corrects browser timer context and opens the battle dialog before animations start. An animation failure returns control to the normal battle UI. Attack motion, damage/effectiveness text and cancellation of stale sounds are retained. See `Docs/BATTLE_SCREEN_FIX.md` and `Docs/BATTLE_FEEDBACK.md`. Build and deploy matching Client and Server, retaining your existing database, configuration and certificates.

## Native learnsets update

Read `Docs/LEARNSET_GUIDE.md` for native move levels and the Move Reminder. Cyndaquil learns Ember at level 12 in both supplied ROMs. Existing characters keep progress and chosen moves; invalid queued choices are reconciled on login. Deploy matching new Client and Server packs.

## Adventure update

Read `Docs/ADVENTURE_GUIDE.md` for trainer/badge progression, Nurse Joy healing, PC storage, evolution and move learning. Interior destinations and recovered Sigma rooms use audited ROM metadata. Older configured worlds should set `[world] allow_alpha_atlas = false` and `allow_alpha_surf = false` for progression gates; fresh templates already do. Keep your working database, config and TLS files.

## Starter, login and progress fixes

This release keeps starter choice independent of starting region, fixes account/session retry races and saves progress on the server automatically. Fresh server configurations use a five-second movement checkpoint interval; important gameplay changes commit before success. Read `Docs/REPLICATION_FIX_1.2.3.md` before upgrading a configured world. No account reset or character-specific repair is included.

## Correction for the Go prerequisite error

Build tools **1.3.3** retain the correction for `Cannot overwrite variable HOME because it is read-only or constant`. Two Go helper functions used a directory variable named `$home`, which collides with PowerShell's built-in `$HOME`. Both directory variables have been renamed, including the SDK check that previously rejected valid Go installations.

Extract both complete ZIPs into the same new destination and run its `BUILD_ALL.bat`. The banner should say **1.3.3**. Your existing compatible Python and verified tool downloads can be reused; reinstalling Python, changing Windows HOME, or changing MySQL settings is unnecessary. See `Docs/AUTO_BUILD_1.1.1_TEST_REPORT.md` for the original correction's validation scope and `Docs/AUDIO_TEST_REPORT.md` for the audio validation and `Docs/REPLICATION_TEST_REPORT.md` for this release.

## Online server fails because TLS files are missing?

In the built Server folder, run **`2b - Configure Online Hosting.cmd`**. Enter the public IP/domain players will use and create a certificate/key pair, or import your existing pair. This preserves MySQL settings. Give players the generated public connection kit and follow **`Docs/ONLINE_HOSTING.md`** for trust, client settings and TCP port forwarding. A certificate alone cannot configure your router.

## Already built and configured the server?

World startup fix **1.1.2** is already incorporated in this source. It releases this server's lease on failed startup, records early failures at the absolute log path printed in the console, and waits briefly for a recent abandoned lease. It still protects a running world that owns the database. See `Server/WORLD_STARTUP_FIX.md`.

For the adventure upgrade, build a fresh output and deploy its **matching Client and Server**. Back up the configured server before replacing program files; carry forward its existing `config.ini`, database and required private deployment files. Preserve the client's connection settings too. Do not copy release config templates over your working settings or run MySQL setup again just to install this release. The old scripts-only startup hotfix is not an audio updater. Detailed steps are in `Docs/AUDIO_GUIDE.md`.

## Build it

Extract **both entire** source ZIPs to a short writable local folder, such as `C:\Dev\PokemonNXT`, connect to the internet and double-click **`BUILD_ALL.bat`**. Do not launch the BAT from inside the ZIP. Use a normal Windows 10/11 x64 user session; Run as administrator is not needed.

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
