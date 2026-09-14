# Automatic build prerequisites — build tools 1.3.4

Date: 2026-09-14. Gameplay **0.3.5-alpha**; MySQL setup **1.1.0**. Build tools **1.3.4** remove the Windows symlink-privilege requirement from variety publisher test fixtures. All gameplay and content bytes remain unchanged. See `WINDOWS_BUILD_FIX_1.3.4.md`.

The original prerequisite fixes below remain included: 1.1.0 added automatic tool installation; 1.1.1 corrected the Go setup reserved-variable error. These historical versions are not the current build banner.

## Go setup correction in 1.1.1

The `Get-NxtGo` cache-directory variable and `Test-NxtGo` SDK-directory variable now have distinct project-specific names. Neither assigns PowerShell's read-only `$HOME` (variable names are case-insensitive). This fixes the immediate prerequisite failure and the hidden rejection of complete installed/extracted Go SDKs. Download versions, checksums and verification rules remain the same.

After a 1.1.0 failure, extract the corrected complete source ZIP into a new folder and double-click its `BUILD_ALL.bat`; check the **1.3.4** banner. Compatible Python and verified shared downloads remain reusable. Native Go-discovery regressions are included in the Windows helper suite; actual validation and platform limits are recorded in `AUTO_BUILD_1.1.1_TEST_REPORT.md`.

Build tools **1.1.2** retain the Go correction and include the server startup recovery/logging fix. The runtime change is documented in `WORLD_STARTUP_FIX_TEST_REPORT.md`; configured servers may use the small hotfix instead of rebuilding.

## Normal operation

Extract the entire source ZIP and double-click `BUILD_ALL.bat` on Windows 10/11 x64 with internet access. Built-in Windows PowerShell 5.1 runs `Build/bootstrap_windows.ps1`; no Python or Go is needed to begin. The bootstrap validates the source layout, checks available space, acquires a per-user build lock and finds or installs the required tools. Then it invokes the existing Python build driver automatically.

The first build needs internet for tool downloads and Python package installation. This is an automatic online build package, not a fully offline toolchain bundle. Node.js is optional for JavaScript syntax checks; not installing it does not block compilation. MySQL and Edge are runtime prerequisites, not build dependencies.

## Tool versions, discovery and locations

`Build/toolchains.json` pins Python **3.13.15 x64** and Go **1.27.1 Windows amd64** with SHA-256 values from their official release records. These pins apply to automatic downloads; compatible existing tools are reused rather than forcibly replaced.

Python discovery checks the managed runtime, PATH, standard registry installation records and common folders. It requires standard x64 CPython 3.11–3.14 with SSL, SQLite, ensurepip, venv and Tk support. Store aliases, prereleases, free-threaded builds and 32-bit runtimes are not selected. A specified but unusable `NXT_PYTHON` produces an explicit error; clear it to allow automatic installation.

Missing Python is downloaded from python.org and installed under `%LOCALAPPDATA%\Programs\PokemonNXT\Python313` for the current user. The full installer includes pip and Tcl/Tk, preserving the MySQL setup GUI; the reduced embeddable ZIP is deliberately not used. This is a normal registered Python installation, not just a portable folder. No Python launcher, shortcuts, file associations or persistent PATH entries are added. Use Windows Installed apps to remove it when no deployed server venv depends on it; do not delete its runtime folder underneath a server environment.

Go discovery checks `NXT_GO`, the managed cache, PATH and standard locations. A complete stable Windows amd64 installation at least Go 1.23 can be reused. Missing Go is extracted to `%LOCALAPPDATA%\PokemonNXT\Toolchains\go1.27.1\go`. There is no MSI, elevation request or global Go PATH edit. Both selected executable paths are passed directly to the build driver; temporary PATH additions affect only this build and its child processes.

Verified downloads are cached under `%LOCALAPPDATA%\PokemonNXT\Downloads`. The user-wide bootstrap lock also serializes separate source copies sharing that cache. Source code, database credentials and saved gameplay are never put in this cache by the bootstrap.

## Verification and safe failures

Both tool downloads must match their pinned SHA-256. The Python installer must also pass Windows Authenticode verification for **Python Software Foundation** before it is executed. Normal HTTPS and certificate validation remain active. Downloads have bounded sizes/timeouts, visible progress, three retries and partial-file cleanup. Redirects are restricted to approved official HTTPS hosts. Go ZIP paths, symlinks, duplicate case-insensitive entries and size limits are checked, and extraction occurs in a staging folder before the completed tool is published.

Invalid/blocked downloads are not executed and do not produce a successful build. Logs are saved under the source `.build/logs`: `bootstrap-*.log` for prerequisites, `python-install-*.log` for the installer, and `build-*.log` for compilation. Correct the reported network/proxy/installation problem, then rerun the same BAT. Verified cache files remain reusable.

The BAT uses a child-process-only PowerShell execution-policy flag. It does not persist a user/machine policy change, change Defender/firewall settings, bypass organisation application control or elevate to administrator. Normal Windows x64 user sessions are supported; managed/locked-down PCs may still require their administrator's approval. A Python-requested restart is reported and the interpreter still has to pass validation.

The bootstrap checks 2 GiB free on the source drive and 1 GiB on the user-cache drive. Keep several GiB available; these are minimum guards, not guarantees for every future content expansion. Prefer short local paths rather than protected or cloud-synchronised folders.

## Python packages and recovery

`Build/build.py` creates `.build/venv` and installs the unchanged exact top-level project requirements using binary wheels from the PyPI index. It does not install packages globally or into a live `Server/.venv`. An unusable or incompatible build venv is preserved as `.build/venv.previous-<timestamp>` before a replacement is created. Failure to install dependencies or to run tests stops release publication; requirements are not silently downgraded.

Go/Python downloads are pinned by hash, but transitive Python dependencies still resolve through pip. This is not a full transitive hash lock or a byte-for-byte reproducible offline supply chain.

## Optional flags

`BUILD_ALL.bat --no-open` suppresses Explorer. `BUILD_ALL.bat --no-install` makes no prerequisite downloads or installations: compatible tools and a healthy venv with the exact package pins must already exist. It is not a fresh offline installer. Set `NXT_BUILD_NO_PAUSE=1` only for terminal/automation runs that should not pause afterward. Failure exit codes propagate.

`NXT_PYTHON` and `NXT_GO` may specify full executable paths without embedded quote characters. Clear obsolete overrides to return to automatic discovery. The BAT accepts `--no-open`, `--no-install`, `--existing-environment` and help flags. Custom `--root` is a direct `Build/build.py` developer option, not a bootstrap option.

The explicit `--existing-environment` developer mode runs with already installed packages and records that production pins were not asserted. It is not a substitute for a successful default Windows build.

## Runtime boundary and previous fixes

The corrected MySQL password GUI and provisioning scripts are unchanged. The server dependency BAT now recognises the managed Python automatically on the build PC. A server-only distribution on another PC still requires a full Python installation. The server executable remains a launcher, not a bundled Python runtime.

The build never installs/provisions MySQL, creates a root password, changes another game's database, adds firewall rules or starts a world. Configure those deployment settings separately using the existing quick-start. Native Windows installer/Edge/MySQL acceptance and real 1,000-connection capacity are separate from cross-compilation and source tests.

## Official references for the pinned tools

- Python release and SHA-256: https://www.python.org/downloads/release/python-31315/
- Python installer options: https://docs.python.org/3.13/using/windows.html#installing-without-ui
- Go release metadata and SHA-256: https://go.dev/dl/?mode=json
- Go downloads: https://go.dev/dl/
- Python venv: https://docs.python.org/3/library/venv.html
- Preserved requirements: https://pypi.org/project/aiohttp/3.14.3/ and https://pypi.org/project/PyMySQL/1.2.0/

## 0.3.5 source and variety assets

The full 0.3.5 source is supplied in **four mergeable ZIPs**. Extract all four into the same destination before invoking the unchanged `BUILD_ALL.bat` workflow. The source allowlist retains `Server/data/varieties.json`, the publisher/importer, runtime helpers and tests. Converted fronts are supplied; ordinary builds require no RAR, Pillow, original ROM or new art download. The shared pack includes the policy/art bindings and requires a matching Client/Server deployment.
