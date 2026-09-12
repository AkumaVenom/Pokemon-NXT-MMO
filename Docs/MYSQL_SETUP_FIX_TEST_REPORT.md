# MySQL setup hotfix 1.1.0 — test report

Date: 2026-09-12. Gameplay/protocol/schema: **0.1.0-alpha**. Build tooling: **1.0.0**. Content pack: **0a8cdb1a321bac58cdfce7e6**.

## Executed

| Check | Result and boundary |
|---|---|
| Full Python regression suite | **119 passed**: 75 existing gameplay/network/build contracts, 37 setup/input tests and 7 hotfix-installer tests. Gameplay/network persistence fixtures are temporary SQLite databases. Setup uses an injected fake MySQL connector. |
| Real Tk password form | **8 passed** on Linux/Xvfb: editable masked values, Show toggle, exact spaces/punctuation, native clipboard paste/selection, blank administrator login test without mutations, wrong-password correction in the same window, worker-thread success flow and secret clearing, confirmation validation, close protection during work and small-window footer access. Database responses were simulated. No Tcl callback errors remained in the final run. |
| Complete build driver | **Passed end-to-end** using `python Build/build.py --existing-environment --no-open` on Linux. |
| Go/Windows build | 3 Go client tests passed; both modules passed Windows-target vet; client GUI/server console x64 executables compiled and PE headers verified. |
| Headless client HTTP fixture | **13 passed** using the Linux shell built from the same Go source. No native Edge launch is implied. |
| JavaScript syntax | Both unchanged modules passed Node syntax checks. |
| Original delivered archive patching | Standalone patch driver applied successfully to extracted Server folders from both the actual original Complete and Source ZIPs; repeat application was a no-op. All unrelated original Server files, including configuration, retained their hashes. Tested via Python on Linux, not BAT on Windows. |
| Release packaging | Driver created and CRC-verified separate client, server and complete ZIPs. Setup hotfix files were included in the staged Server folder. |

The final suite log, Tk log, cross-build log and metadata are under `Docs/evidence/mysql_setup_fix_*`. Existing `Docs/TEST_REPORT.md` and `Docs/BUILD_TEST_REPORT.md` describe earlier historical alpha/source-build checks, not additional MySQL acceptance.

## Setup regression details

Tests preserve an empty administrator value, exact non-empty passwords including punctuation/spaces, distinguish rejected blank/nonblank credentials from service/port failure, and ensure read-only tests execute no provisioning commands. First-install application generation, custom password round-trip, configured-password reuse, different-host/username isolation, pre-DDL existing-account authentication, failed final-login preservation and database-scoped grant structure are covered.

No root password is saved in configuration or provisioning SQL. Tests check redacted errors, environment override mismatch/match, protected administrator/system names, wildcard approval, password policy, missing keys/CA, preservation of other sections/comments, CRLF/BOM handling, concurrent INI edits and atomic-write failure cleanup. Masked-input tests cover visible asterisks, blank, backspace, clear, Windows extended keys, cancellation/EOF, Unicode/punctuation and UTF-16 surrogate normalization.

Hotfix tests check allowed payload paths/hashes, wrong-project rejection, scripts-only backups, configuration/save/store preservation, repeat-apply no-op behavior, partial-write rollback and linked-payload rejection. The standalone patch requires no PyMySQL/Go or database connection.

## Not verified

**No Windows CMD/BAT or Windows executable was run. No real MySQL/MariaDB daemon was used. The exact pinned production pip dependencies were not installed/tested here.** The available runtime lacks PyMySQL and uses aiohttp 3.13.3; the explicit developer cross-build records `production_dependency_pins_enforced: false`. The shipped production dependency requirements are unchanged. No Windows password/clipboard acceptance, OS-specific Tk rendering, user root-password verification, actual privilege/plugin/password-policy behavior, TLS deployment or public-network test is claimed.

An empty password is accepted as input, not guaranteed to authenticate. MySQL root still needs its existing password when one is set. Provisioning remains create-only for users; it never resets or bypasses an existing administrator password. MySQL creation/grant statements can commit before a later failure, so config preservation is not a claim that DDL was fully rolled back.

Gameplay, world assets, network protocol, database schema, client rendering and capacity promises are unchanged. The 1,000 admission cap still does not establish tested 1,000-client runtime capacity.

## Reproduce

From the source root after the normal prerequisites:

```text
python -m unittest discover -s Tests -v
python Tests/check_mysql_setup_gui.py
BUILD_ALL.bat
```

The GUI check needs Tcl/Tk and a graphical display; it is separate from automatic build tests. Linux headless execution used `xvfb-run -a python Tests/check_mysql_setup_gui.py`.

On Windows, apply the scripts-only hotfix to the actual Server folder you launch, start MySQL and run `2 - Configure MySQL.cmd`. Test the existing administrator login before provisioning. Verify the world starts with `Database: mysql`; then perform the original two-player persistence/trading acceptance checklist. No user-specific MySQL credentials are assumed by these tests.
