# Source / one-click build validation report

> Historical source/build tooling 1.0.0 report. For automatic prerequisites, see `AUTO_BUILD_TEST_REPORT.md`. For the later MySQL setup hotfix 1.1.0, see `MYSQL_SETUP_FIX_TEST_REPORT.md`.

Date: **2026-09-12**. Gameplay baseline **0.1.0-alpha**. Build tooling **1.0.0**.

## Executed for this source update

| Check | Result and scope |
|---|---|
| Complete build driver | Passed end-to-end on Linux using the explicit `--existing-environment --no-open` developer mode |
| Python regression / integration suite | **75 tests passed**: original 51 content/security/world/store/network tests plus 24 new build-tool tests |
| Go client tests | **3 passed**; the server launcher currently has no Go unit tests |
| Windows-target static checks | `go vet` passed for both launcher modules |
| Windows executables | Both rebuilt from source; PE headers verified as x64, client GUI subsystem 2 and server console subsystem 3 |
| Native headless client shell | **13 HTTP checks passed** on a separately compiled Linux helper from the same source |
| JavaScript syntax | Both client JavaScript modules passed Node.js syntax checking |
| Release packaging | Client, server and complete ZIPs produced by the driver and verified using ZIP CRC checks |
| Configuration / source filtering | Tested private config exclusion, password-template rejection, DB/log/TLS/ROM/binary exclusion, manifests, snapshot preservation, symlink rejection and build-lock release |
| Existing source/content preservation | Original Client, Server and Tools files (excluding prebuilt EXEs) compared by SHA-256 against the supplied complete alpha ZIP; no changes or missing files |
| Dependency guard logic | Executed with controlled package metadata: exact pins accepted; incorrect versions rejected. This is not a pip-install test |

The content pack remains `0a8cdb1a321bac58cdfce7e6`. All **10,902 client asset PNGs** remain included. Source-delivery packaging excludes generated executable files, build workspaces, virtual environments and release ZIPs.

Recorded evidence is in `Docs/evidence/source_build_info.json`, `source_build_log.txt` and `source_preservation.json`. These are historical build-test records, not evidence that the recipient's later Windows build has already run. A new build writes its own `BUILD_INFO.json` and `.build/logs` entry.

## Exact environment and limitations

The executed cross-build used Linux, Python **3.13.5**, Go **1.23.2**, Node.js **22.16.0** and the available **aiohttp 3.13.3**. PyMySQL was not installed in that test environment; SQLite fixtures do not exercise the MySQL driver. The preserved normal-build requirements are **aiohttp 3.14.3** and **PyMySQL[rsa] 1.2.0**. The normal workflow installs and checks those requirements in an isolated build venv; **that exact production dependency installation was not runtime-verified here**. The cross-build records `production_dependency_pins_enforced: false` instead of pretending to validate those pins.

**The BAT has not been executed in native Windows CMD here.** Both Windows EXEs were cross-compiled and inspected, not run. The headless HTTP fixture ran on Linux and does not open Edge, test Windows firewall prompts or establish native Windows graphics/DPI acceptance. The BAT uses CRLF line endings, quoted project paths, Python/Go prerequisite checks, failure exit codes and a final pause; those facts are source inspection, not Windows execution evidence.

MySQL/MariaDB runtime acceptance, direct TLS deployment, multi-monitor DPI behavior, native Edge UI execution and a genuine 1,000-concurrent-connection test remain outstanding. No new gameplay features, campaign parity or scaling guarantee is asserted by this source-build update.

## Reproduction

On Windows, install the documented Python and Go prerequisites, extract the entire source package and run `BUILD_ALL.bat`. A successful default build records that the production top-level dependency pins were enforced. It runs the tests and headless Windows shell checks locally, then writes a new timestamped output folder. Native Edge/MySQL acceptance still follows the separate `Docs/QUICK_START.md` procedure.

For a preinstalled exact build environment, `BUILD_ALL.bat --no-install` omits pip downloads but retains pin verification and all build checks. The developer `--existing-environment` option is not equivalent to that pinned/offline mode.
