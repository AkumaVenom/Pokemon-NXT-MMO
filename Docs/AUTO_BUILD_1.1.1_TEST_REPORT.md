# Automatic build 1.1.1 — Go prerequisite correction

Gameplay **0.1.0-alpha** · Build tools **1.1.1** · MySQL setup **1.1.0**

## Reported failure and correction

The recipient's Windows run reached Go prerequisite setup, then stopped with `Cannot overwrite variable HOME because it is read-only or constant`.

PowerShell variable names are case-insensitive. `Get-NxtGo` assigned a cache path to `$home`, which is the built-in read-only `$HOME`; this failed before existing-tool or download discovery. `Test-NxtGo` used the same name for the SDK root and caught the error, silently rejecting valid compilers. Both assignments and their dependent path uses have been renamed to `$goCacheRoot` and `$goInstallRoot` respectively. The Windows user-profile variable is untouched.

Version labels in the BAT, Python build metadata, download user-agent and bootstrap manifest now agree on **1.1.1**. The Python/Go versions, URLs, hashes, signature checks and Python package requirements retain the uploaded baseline's values. This update does not independently revalidate their availability.

## Checks executed for this correction

| Check | Result and actual scope |
|---|---|
| Full Python regression suite | **144 discovered: 143 passed, 1 skipped**, in 12.051 seconds. Includes source/build contracts, venv recovery, gameplay/persistence contracts and real local TCP/WebSocket tests with disposable SQLite state. |
| Original-source regression | The new reserved-variable assignment guard **fails as expected** against the unmodified attached 1.1.0 scripts and passes against the corrected scripts. This is a source check, not PowerShell execution. |
| Version consistency | Entry-point banner, bootstrap manifest, build metadata constant and user-agent agree on 1.1.1. |
| Existing Windows BAT formatting | Windows CRLF line endings preserved and checked. |
| Source preservation | **11,810 Client, Server and Tools files** match the supplied ZIP byte-for-byte, including assets, gameplay, configuration, requirements and MySQL setup. |
| Source distribution | Full source ZIP retained; new validation evidence added; source SHA-256 manifest regenerated and archive CRC/file hashes verified. No local test caches are included. |
| Independent script review | Both corrected Go paths and new native test scopes/fixtures reviewed for Windows PowerShell 5.1 compatibility; this is static review. |

The validation host was **Linux x86_64, Python 3.12.14**, with **aiohttp 3.13.5** and **cryptography 46.0.0**. PyMySQL, Go and PowerShell were unavailable. Tests used the available Python environment; the shipped production dependency pins were not installed or changed.

## Included Windows regressions and execution limits

The Windows-only helper group was **skipped**, not counted as passed. It now adds 25 assertions for complete/incomplete SDKs, version rejection, installed/PATH/explicit-override discovery, offline refusal, rejected staged extraction preserving the existing cache, successful staging/publication, cache reuse and unchanged `HOME`. Fake SDK files and mocked native/download/extraction calls exercise the real discovery functions without installing anything. Existing native process-quoting tests remain outside the mock scope.

These helper cases execute automatically during the Python test phase of `BUILD_ALL.bat` on Windows. They have not been executed in this Linux environment. Neither the actual Windows BAT, real Python/Go download/install flow, default pinned pip installation, nor Windows EXE compilation/execution was run for this correction. Historical 1.1.0 cross-build evidence remains historical; it is not a new 1.1.1 Windows build result.

## Evidence and recipient run

- `evidence/auto_build_1.1.1_unit_tests.txt`: actual complete Python test output.
- `evidence/auto_build_1.1.1_original_regression.txt`: expected failure on the original scripts.
- `evidence/auto_build_1.1.1_preservation.json`: original archive hash and byte-comparison results before manifest regeneration.

Extract the entire corrected source ZIP into a fresh writable Windows folder and double-click **BUILD_ALL.bat**. Confirm the **1.1.1** banner. Existing compatible Python and verified shared tool downloads are reusable. Go discovery should now progress into reuse or automatic download/extraction, then continue to isolated dependencies, tests, compilation and packaging. A successful run publishes `dist/build-<timestamp>` and records it in `dist/LATEST_BUILD.txt`.
