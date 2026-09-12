# Pokemon NXT MMO — automatic all-in-one source build

Gameplay **0.1.0-alpha** · Build tools **1.1.1** · MySQL setup **1.1.0**

## Correction for the Go prerequisite error

Build tools **1.1.1** fix `Cannot overwrite variable HOME because it is read-only or constant`. Two Go helper functions used a directory variable named `$home`, which collides with PowerShell's built-in `$HOME`. Both directory variables have been renamed, including the SDK check that previously rejected valid Go installations.

Extract this complete corrected ZIP into a new folder and run its `BUILD_ALL.bat`. The banner should say **1.1.1**. Your existing compatible Python and verified tool downloads can be reused; reinstalling Python, changing Windows HOME, or changing MySQL settings is unnecessary. See `Docs/AUTO_BUILD_1.1.1_TEST_REPORT.md` for validation scope.

## Build it

Extract the **entire** source ZIP to a short writable local folder, such as `C:\Dev\PokemonNXT`, connect to the internet and double-click **`BUILD_ALL.bat`**. Do not launch the BAT from inside the ZIP. Use a normal Windows 10/11 x64 user session; Run as administrator is not needed.

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

See `Docs/AUTOMATIC_BUILD.md` for cache locations, official download pins and safe reruns, `Docs/BUILD_FROM_SOURCE.md` for the complete workflow, and `Docs/AUTO_BUILD_TEST_REPORT.md` for actual test scope.
