# Regression and acceptance tests

Run `python -m unittest discover -s Tests -v` from the complete project root with server dependencies installed. The suite uses temporary SQLite databases and does not touch the configured MySQL database. It needs the full Client asset tree for data/reference checks. See Docs/TEST_REPORT.md for the recorded 51-test result and platform boundaries.

`ui_acceptance.py` is an optional Playwright DOM/rendering acceptance fixture. Set NXT_BROWSER_PATH to installed Chromium/Edge and install Playwright in a test environment. It starts an isolated world service on a temporary port, uses a disposable SQLite database, drives two clients and writes screenshots under ui_artifacts. A local DOM/asset/WebSocket bridge is used; this is explicitly not native Windows launch or native browser WebSocket coverage. A no-sandbox Chromium flag is used only by the test fixture for the container environment; the shipped client launcher does not use that flag.

`check_launcher.py PATH_TO_COMPILED_LAUNCHER` tests static-serving/HTTP controls using the actual Go shell in headless mode, without opening a browser. Source-level Go tests are in Client/launcher. A Linux build was tested; Windows PE files were cross-built but not executed.

No automated MySQL deployment, 1,000-socket benchmark or original-ROM story parity test is implied. Complete the manual Windows/MySQL acceptance checklist in the documentation.

## Build-tool additions

`test_build_tools.py` adds isolated tests for source selection, clean config templates, credential/live-data exclusions, manifests, ZIPs, lock release, path handling, snapshot preservation and PE header validation. `BUILD_ALL.bat` runs these together with the existing regression/network suite. The original 51-test record is historical; the build records the actual total it runs. Symlink creation tests may be skipped on Windows hosts without the necessary user privileges.

`Build/smoke_launcher.py` is the bounded headless fixture used by the build pipeline. It is separate from the original `Tests/check_launcher.py` and writes its report outside the source tree. Refer to `Docs/BUILD_FROM_SOURCE.md` for toolchain, output and platform boundaries.

## Automatic prerequisite bootstrap

`test_auto_bootstrap.py` checks official download declarations, hash/signature guards, bootstrap retention, Windows line endings and automatic build-venv recovery. It invokes the actual `check_bootstrap_windows.ps1` helper suite on Windows; other hosts explicitly skip it. The native helper suite checks PowerShell parsing, native argument quoting, versions, URLs, hashes and ZIP traversal without downloading/installing tools. These helper tests are not an end-to-end installation test. See `Docs/AUTO_BUILD_TEST_REPORT.md`.

Build tools 1.1.1 also check reserved PowerShell variable assignments on every host, build-version consistency, and native Go SDK acceptance/discovery, explicit overrides, offline handling and staged/cache paths using disposable SDK fixtures. The native cases stub external processes and downloads; they do not install a real compiler. See `Docs/AUTO_BUILD_1.1.1_TEST_REPORT.md`.

## World startup fix 1.1.2

`test_world_lease.py` checks ownership, expiry boundaries, future clocks, old-owner fencing and idempotent shutdown with real temporary SQLite stores. `test_server_startup.py` checks the startup lifecycle, lease recovery and persistent failure logs. `test_world_startup_patch.py` checks the small scripts-only patch installer. See `Docs/WORLD_STARTUP_FIX_TEST_REPORT.md`; SQLite/mocked checks do not imply a live Windows/MySQL acceptance run.

`test_online_setup.py` verifies certificate generation/import, preservation of database settings and public-only export. `test_tls_network.py` verifies real HTTPS/WSS with certificate and hostname validation, plus TLS configuration failures. `Docs/ONLINE_HOSTING_TEST_REPORT.md` records the current execution results.
