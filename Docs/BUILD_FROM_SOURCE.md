# Building Pokemon NXT MMO from source

Gameplay baseline **0.1.0-alpha** · Build tooling **1.1.2** · MySQL setup **1.1.0** · 2026-09-13

## Required tools and responsibilities

The root `BUILD_ALL.bat` is the Windows entry point. Its orchestration is implemented in readable, standard-library Python under `Build/build.py`; it invokes tools directly without shell-interpreting project paths. The batch wrapper uses normal CMD and built-in Windows PowerShell; its policy flag is child-process-only, not a permanent policy change.

**Extract the full source ZIP and double-click `BUILD_ALL.bat` on Windows 10/11 x64 with internet access. Go and Python no longer need to be installed manually.** Built-in Windows PowerShell 5.1 finds compatible tools or downloads/installs the pinned official replacements, then invokes the Python driver automatically. See **`AUTOMATIC_BUILD.md`** for exact versions, SHA-256/signature checks, cache paths, per-user Python installation, logs and safe reruns.

Official references (new download pins and checks are in `AUTOMATIC_BUILD.md`):

- Python Windows downloads: https://www.python.org/downloads/windows/
- Go downloads: https://go.dev/dl/
- Python virtual environments: https://docs.python.org/3/library/venv.html
- Go build/test/vet and build flags: https://pkg.go.dev/cmd/go
- Preserved alpha dependency pins: https://pypi.org/project/aiohttp/3.14.3/ and https://pypi.org/project/PyMySQL/1.2.0/

Missing tools are now installed automatically: Go into the user cache and full Python through its normal registered per-user installer, with pip and Tcl/Tk. No tool installers are bundled in the source ZIP, so internet is needed. There is no elevation, permanent PATH edit, persisted execution-policy change or firewall/database change. Normal Windows 10/11 x64 is the supported bootstrap host.


The normal build needs no MySQL daemon, Edge, Node.js, Git, Visual Studio, C++ SDK, Pillow, numpy or original ROM. MySQL and Edge are runtime prerequisites, not compiler prerequisites. The original extraction tools are preserved for development, but are never invoked by `BUILD_ALL.bat`; re-extraction is a separate optional task with additional dependencies and original inputs.

Extract into a short, writable local folder. Allow several GB of disk space for the source, Go compilation cache, Python environment, isolated build snapshot, release files and ZIPs. The Windows bootstrap checks at least 2 GiB free on the source drive and 1 GiB on the user-cache drive. Keep several GiB available; these minimum guards do not guarantee capacity for all future content expansions. Very deep folders may encounter Windows/toolchain path-length limits. Spaces and parentheses in paths are handled by quoted CMD paths and subprocess argument lists. Avoid building directly inside cloud-synchronized or protected system folders.

## Exactly what the default build does

`BUILD_ALL.bat` locates or installs compatible Python and Go, then calls `Build/build.py` automatically. A filesystem lock prevents two builds from modifying the same build cache concurrently. Locks are owned by the operating system, so a leftover small lock file after a crash does not itself block the next build.

The driver creates `.build/venv`, installs **the unchanged exact top-level requirements in `Server/requirements.txt`**, and checks installed requirements. It does not install pip packages into your global Python or an existing world-server environment. First installation needs internet access. Transitive package versions are resolved by pip and recorded where relevant; there is not a complete transitive hash lockfile or offline wheel bundle. Do not call this a byte-for-byte reproducible toolchain supply chain.

Source and content are copied to an isolated build snapshot. Selection excludes deployed configs, existing EXEs, virtual environments, caches, ROMs, databases/backups, private TLS material and runtime logs. Clean configs are copied from `Build/config_templates`. The server release template is checked for the literal `CHANGE_ME_WITH_SETUP` password placeholder and the MySQL backend. A real password there stops the build. These guards do not detect arbitrary credentials that a developer hardcodes into source or documentation: review your own modifications before distribution.

The snapshot's native content is published by `Tools/repack_content.py`. This validates references and regenerates matching client/server data and asset digests from the included PNG/JSON resources. It does not read a ROM or modify the source copy of `Server/data/world.json`. Content edits must be made to canonical source data and assets before building. Stable species/map/item identifiers remain persistence contracts; do not rename live IDs casually. Regression expectations such as baseline map counts must be deliberately updated when expanding the game; do not bypass failed tests to force a release.

The driver then performs Python syntax parsing and the regression/real-network tests, native-host Go tests, and Windows-target `go vet`. It compiles a Windows x64 GUI-subsystem client launcher and a Windows x64 console-subsystem server launcher with CGO disabled, path trimming and VCS stamping disabled. It checks actual PE header signatures, x64 architecture and GUI/console subsystem values.

A bounded headless HTTP fixture starts the actual compiled client shell and checks local serving, headers, bootstrap, traversal rejection and heartbeat rules. On Windows it uses the rebuilt Windows executable; on Linux cross-build verification it creates and runs a separate Linux helper from the same source. It never claims that a headless test opens Edge or accepts a real player's Windows UI. An installed Node.js adds a syntax-only check of JavaScript modules; absence is explicitly recorded, not treated as a passed JavaScript test.

Finally the driver writes build metadata, hashes, separate client/server ZIPs and a complete ZIP; it checks each ZIP's CRC integrity. Only a successful package is renamed into `dist/build-<UTC timestamp>`. It updates `dist/LATEST_BUILD.txt` and opens the new folder in Explorer. A failed attempt does not overwrite source or old builds. Each successful build consumes additional space; remove unwanted old output folders manually only after confirming they contain no deployment saves/settings you need.

## Outputs and source locations

`Client/launcher/*.go` implements the Windows/loopback app shell. `Client/app/index.html`, `styles.css`, `app.js` and `renderer.js` are the editable UI and renderer. `Client/app/assets` contains extracted content and generated client-facing data.

`Server/launcher/*.go` implements the Windows console launcher. `Server/server.py` and `Server/nxt/*.py` implement the service, server authority, combat, accounts, persistence and exchange logic. The MySQL schema creation/transaction code is in the Python store; an unrelated SQL export is not required. `Server/setup_mysql.py` is the explicitly invoked provisioning workflow.

`Server/data/world.json` is the canonical native world catalog for ordinary content authoring. `Tools` includes the original extraction/preparation pipeline and ROM-free content publisher. `Tests` contains the original gameplay/network tests plus build-tool regression tests. `Build` contains the new build driver, bounded launcher fixture and clean configuration templates. No original gameplay source is minified or obfuscated by this packaging update. PowerShell bootstrap/test files (`.ps1`) and the toolchain manifest are included. New file types outside the existing source/content allowlist require a deliberate update to `TREE_EXTENSIONS` / `is_source_file` and matching regression tests; unapproved file types are intentionally not copied.

Under a completed `dist/build-...`, the runnable `Client` and `Server` folders remain separate. The `Packages` folder contains separate client/server ZIPs plus a complete developer package. The complete ZIP contains source and rebuilt binaries. `BUILD_INFO.json` describes the actual compiler, dependencies, content pack, tests and platform boundary. Root `SHA256SUMS.txt` covers unpacked release files at publication time; `Packages/SHA256SUMS.txt` separately covers the ZIPs. Editing output configs changes their hashes, as expected.

Build tools 1.1.2 also include the world startup cleanup/logging correction in `WORLD_STARTUP_FIX_TEST_REPORT.md`. Build tools 1.1.1 correct both reserved `$HOME` assignments in Go discovery/validation; see `AUTO_BUILD_1.1.1_TEST_REPORT.md`. The source ZIP you received deliberately excludes prebuilt binaries. It contains its own `SOURCE_SHA256SUMS.txt` for the unmodified source delivery. Local build caches and `dist` output are excluded from that source package.

## Private configuration and future rebuilds

Edit these only for distribution-safe defaults:

```text
Build/config_templates/Client/config.ini
Build/config_templates/Server/config.ini
```

The client template may contain the intended join IP/hostname and public connection port. Never put database credentials in it. Keep `edge_path` blank in the release template; each installation may set its own browser path afterward.

The server template must retain `password = CHANGE_ME_WITH_SETUP` and the MySQL backend. Configure real credentials only in the chosen output/deployment folder, using the documented server setup. Your source-folder `Client/config.ini` and `Server/config.ini` are not included in subsequent builds. This is deliberate: rebuilding must not leak live configuration or overwrite a running deployment.

After building, follow the output's `Docs/QUICK_START.md`. A build does not provision MySQL, install the output Server's `.venv`, start a world or log in clients. Those are deployment actions with real credentials and are intentionally separate. The server executable remains a launcher for Python, not a PyInstaller-style bundled Python service. The player app remains an Edge app-window application, not Unreal/Unity or an emulator.

## Optional command-line modes

Ordinary use needs none of these; double-click `BUILD_ALL.bat`.

Once the build virtual environment already contains the exact pinned requirements, reuse it without contacting pip indexes:

```bat
BUILD_ALL.bat --no-install
```

This still validates package pins, runs tests and rebuilds outputs. It is not a fresh offline installer. The current Go modules use the standard library only; future added Go dependencies would need their own offline/module caching plan.

Suppress the Explorer window:

```bat
BUILD_ALL.bat --no-open
```

The server dependency BAT recognizes the managed Python on this build PC even without PATH or `py.exe`. A server-only deployment on another PC still needs Python.

For a terminal/automation run without the final keypress, set `NXT_BUILD_NO_PAUSE=1` before invoking the BAT. Failure propagates a nonzero exit code. The default keeps the console open so a double-click user can read errors.

Custom interpreter paths can be supplied as environment variables. Store the path as the variable value without embedded quote characters:

```bat
set "NXT_PYTHON=C:\Tools\Python313\python.exe"
set "NXT_GO=C:\Tools\Go\bin\go.exe"
BUILD_ALL.bat
```

Developer-only verification on a host that already has suitable test dependencies can run:

```text
python Build/build.py --existing-environment --no-open
```

That mode neither installs nor asserts the production dependency pins. It writes `production_dependency_pins_enforced: false` and the actual installed versions to `BUILD_INFO.json`. It is intended for transparent cross-build testing, not as a workaround for a failing release dependency installation. It does not establish MySQL runtime correctness merely because SQLite tests pass.

## Failures and safety boundaries

Read the console and `.build/logs/build-....log`. Missing/old Go or Python triggers automatic prerequisite provisioning; blocked downloads, invalid overrides or installation failures produce explicit diagnostics. A pip version/wheel/download error stops the build; the driver never silently downgrades the pinned requirements. An unusable build venv is now preserved as `.build/venv.previous-<timestamp>` and recreated automatically. Never delete a deployed `Server/.venv` as part of build troubleshooting.

A mismatched content reference, syntax error, failing test, Go compilation failure or ZIP check failure stops publication. The source and older outputs are preserved. Do not run unreviewed source from others merely because it has a build script: tests, code compilation and dependency installation execute code. This package does not disable Windows security protections or sign executables.

Read `Docs/AUTO_BUILD_TEST_REPORT.md` and the historical `Docs/BUILD_TEST_REPORT.md` for checks actually performed on this source update. Windows BAT execution, Edge launch, MySQL deployment, TLS, multi-monitor DPI and real 1,000-connection capacity are distinct acceptance tasks; a successful compiler/package build alone does not prove them.

## MySQL setup hotfix in this source edition

Future `BUILD_ALL.bat` outputs include `Server/setup_mysql.py`, `setup_mysql_gui.py`, `setup_password_input.py`, the updated configure CMD and `MYSQL_SETUP_FIX.md`. There is no gameplay/protocol/schema or launcher change. Tk is an optional setup interface, not a new Go/build dependency; a masked interactive console fallback works without it. The normal 119-test Python suite includes 44 setup/patch tests using a fake database connector. The separate eight-test GUI check needs Tcl/Tk plus a display and is not automatically part of the default build. See `Docs/MYSQL_SETUP_FIX_TEST_REPORT.md`.

To repair an already built/deployed folder, use the separate scripts-only hotfix package or copy only those five setup files into its Server folder. Do not replace a live config.ini with a distribution template. Patching the source alone does not retroactively change an older `dist` output; apply the hotfix to the Server folder you actually launch as well.
