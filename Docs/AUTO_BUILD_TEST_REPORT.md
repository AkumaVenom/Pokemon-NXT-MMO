# Automatic build fix — validation report

> Historical **1.1.0** validation. For the subsequent Go/HOME correction and checks performed for build tools **1.1.1**, see `AUTO_BUILD_1.1.1_TEST_REPORT.md`.

Date: **2026-09-13** (Australia/Melbourne). Gameplay **0.1.0-alpha**, build tools **1.1.0**, MySQL setup **1.1.0**.

## Implemented correction

The earlier root BAT searched for installed Python and stopped when missing; the Python driver required an installed Go compiler. The new BAT starts with Windows PowerShell 5.1 and automatically discovers or downloads/installs missing full Python x64 and Go, then continues into isolated package installation, tests, compilation and packaging. The verified-download manifest and bootstrap helpers are included in source and complete releases. The corrected MySQL password GUI/backend remains unchanged.

## Checks actually performed

| Check | Result and scope |
|---|---|
| Python regression/integration suite | **142 discovered: 141 passed, 1 skipped.** Includes the existing 119 tests plus 22 new passing automatic-build/source/venv-recovery tests. |
| Windows-only PowerShell helper group | **Skipped on Linux.** Included for native Windows execution; no simulated pass is claimed. |
| Complete Python build orchestrator | **Passed end-to-end on Linux**, using explicitly labelled `--existing-environment --no-open` developer mode. |
| Go tests | **3 client tests passed.** The server launcher has no Go unit tests. |
| Windows-target Go static checks | **Passed** for client and server. |
| Windows x64 executables | Both compiled and PE architecture/subsystem inspected; **not executed on Windows**. |
| Native local HTTP helper | **13 checks passed** using a Linux executable built from the same client source. No Edge UI is launched by this fixture. |
| JavaScript syntax | Both modules passed checks with installed Node.js. |
| Release ZIPs | Client, server and complete ZIPs were produced and each passed CRC integrity checks. |
| Source release contents | Production source selection retains BAT, PowerShell bootstrap/helpers, manifest and tests, and excludes runtime downloads, caches, deployed settings and binaries. |
| Existing project protection | **11,790 protected baseline files compared byte-for-byte and unchanged**: all Client code/assets, world logic/data, game configs, MySQL setup/password GUI and requirements. |
| Build virtual-environment recovery | Tests exercise healthy/invalid probes, architecture/version rejection, timeout/error handling, preservation/recreation, offline refusal and isolation from Server/.venv. |

`Docs/evidence/auto_build_info.json`, `auto_build_log.txt`, `auto_build_unit_tests.txt` and `auto_build_preservation.json` record those executed checks. Timestamps in build logs are UTC. These are evidence from the source-delivery environment, not the recipient's PC. A new build creates its own fresh logs and BUILD_INFO.json.

## Exact environment and limits

The available execution environment was **Linux, Python 3.13.5, Go 1.23.2, aiohttp 3.13.3 and Node.js 22.16.0**. PyMySQL was not installed. The default release dependencies remain **aiohttp 3.14.3** and **PyMySQL[rsa] 1.2.0**; the developer cross-build explicitly records `production_dependency_pins_enforced: false`.

**The Windows BAT/PowerShell bootstrap, actual Python/Go downloads, Authenticode check, installer execution and default exact-pin pip installation were not executed here.** The container did not provide Windows/PowerShell, and external binary downloads could not be completed from it. Official release records were used to confirm the pinned download URLs/versions/SHA-256 values. Source contract checks and Windows PE cross-compilation are not substituted for an end-to-end clean-Windows installation test.

The included native Windows helper suite tests parsing, argument quoting, version checks, URL/hash rejection and ZIP traversal without downloads or installation. On Windows it runs as part of the build's Python suite. Its presence is not evidence that it already passed on Windows.

MySQL/MariaDB runtime acceptance, Edge UI, TLS, multi-monitor DPI, complete campaigns and a real 1,000-concurrent-connection test remain unchanged separate acceptance tasks. This fix changes build/dependency plumbing, not the alpha's gameplay claims.

## Recipient acceptance

Extract the entire source ZIP on a normal Windows 10/11 x64 PC with internet and double-click `BUILD_ALL.bat`. On a PC without Go or Python, confirm prerequisite progress is shown, Python/Go are installed for the user, and the same run proceeds into package installation, tests and compilation. A successful run publishes `dist/build-<timestamp>` and the three distribution ZIPs. Rerun to check compatible tool/cache reuse.

Do not change MySQL credentials to test compilation. Start the world separately via the included quick-start and corrected MySQL setup. For an existing configured source/deployment, confirm configuration and saved data are unchanged after the build. A blocked or mismatched download must fail visibly rather than publish a release.
