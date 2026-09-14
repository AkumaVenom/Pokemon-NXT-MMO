# Windows variety build fix · Validation report

Date: **2026-09-14**. Gameplay **0.3.5-alpha**; build tools **1.3.4**.
Baseline: all four supplied v0.3.5 source ZIPs. This is a source/build correction,
not a claim of a completed native Windows deployment acceptance test.

## Reported failure and reproduction

The user's `bootstrap-20260914-030738-128.log` shows successful tool discovery.
`build-20260913-170739-083745Z.log` shows successful dependency installation and
pack publication, followed by **523 tests: two errors and ten skips**. Both errors
are `Path.symlink_to` in the variety publisher fixtures, raising **WinError 1314**.

Before editing, the two original tests were run with `os.symlink` made to raise
that privilege-denial error. **Both reported errors reproduced**. This is an
explicit failure simulation on Linux, not execution of Windows itself.

## Executed corrected checks

| Check | Result |
|---|---|
| Corrected variety test module | **32 passed; zero errors/failures/skips** |
| Complete clean-source Python suite in full build | **526 run: 525 passed, one native-Windows test skipped** |
| Separate complete clean-source suite with both link APIs denied | **526 run: 515 passed, 11 expected skips; zero errors/failures** |
| Variety tests in link-denial full-suite run | **All 32 passed**, including both originally failing tests |
| JavaScript UI/regression groups in full build | **103 + 8 tests passed**, plus **34 internal audio-engine checks** |
| Go client launcher suite | **12 passed**; server launcher has no Go test files |
| Windows-target Go static analysis and x64 cross-compilation | **Passed** for both launchers |
| PE subsystem inspection | **Passed**: x64 GUI client and x64 console server |
| Actual Linux-built launcher HTTP smoke checks | **26 passed** |
| Full clean developer-mode build | **Succeeded** through snapshot, republish, tests, compilation, checksum/ZIP verification and output publication |
| Republished content | **Unchanged pack `76fad1c40143e106528d0c53`** |

The one normal-suite skip is the native Windows PowerShell helper. With link
creation deliberately unavailable, ten additional existing link-security tests
skip because they cannot construct their attack fixtures. These ten are not
the two repaired publisher tests. The new privilege-denial regression runs those
publisher tests with both `os.symlink` and `os.link` forbidden and asserts that
neither API was called.

The extra fixture checks verify all 3,697 copied fronts, private file identity,
actual checksum failure after corrupting a copied sprite, unchanged original
sprite bytes, no audit publication on failure, missing-file rejection and
cleanup. The original idempotence/combat-data-preservation checks and path/hash
rejections continue to invoke the real, unmodified publisher.

## Preservation

**18,286 original files under Client, Server and Tools are byte-for-byte
unchanged**, including gameplay, configuration templates, published world packs,
encounter/variety data and asset import/publishing code. **17,179 original
PNG/OGG/WAV files are unchanged**, including every supplied variety front.
No dependency or automatic-download version/checksum was changed; only the
bootstrap revision marker and user-agent were advanced. The root BAT retains
Windows CRLF line endings and now displays the correct gameplay version.

Source metadata, tests and build documentation are the only changed files. No
account database was read from the user's machine. The repair package excludes
runtime configs, certificates, saves, credentials, assets, `.build` and `dist`.
The four complete-source parts retain clean configuration templates, not live
operator credentials; preserve your actual settings when deploying.

## Environment and limits

Execution host: **Linux, Python 3.13.5, Node v22.16.0, Go 1.23.2**. The full build
command was `python Build/build.py --existing-environment --no-open`.
It used **aiohttp 3.13.3 and cryptography 46.0.4**; PyMySQL is not installed here.
That developer flag explicitly records that production dependency pins were
**not installed or enforced** in this environment. The ordinary Windows build
still installs/verifies its existing exact pins; the supplied Windows log shows
that step already succeeded before the fixture failure.

Windows executables were cross-compiled and inspected, **not run on Windows**.
The Windows privilege error was reproduced through targeted failure injection.
The PowerShell bootstrap, native Edge launcher/UI, Windows filesystem behavior
outside this fixture correction, live MySQL and deployment on the user's PC
still need their native build/runtime check. No new browser visual acceptance
run is claimed for this build-only change; the client files are identical and
their automated UI/rendering/audio regressions were rerun successfully.

## Reproducibility and evidence

- `evidence/windows_link_error_reproduction_1.3.4.json` records the original two-error reproduction.
- `evidence/windows_build_1.3.4.json` is the actual completed build's machine-readable record.
- `evidence/windows_links_denied_1.3.4.json` records the separate complete-suite result and every expected skip.
- `SOURCE_SHA256SUMS.txt` describes the final source. The download verification report records four-part integrity and small-repair equivalence.

The full build tested the final code and build revisions. This report and the
captured JSON evidence were added after execution; final source/download
checksums were then regenerated and archives independently verified.
