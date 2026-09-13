# Online hosting setup 1.2.2 — validation report

## Failure and correction

The supplied screenshot shows MySQL opening successfully, followed by a missing TLS certificate/private-key failure. This source adds `2b - Configure Online Hosting.cmd`, a Tk setup window and console/CLI alternatives to create those files locally for the entered join hostname/IP or import an existing matching PEM chain/key. No shared deployment key is shipped.

TLS preflight now happens before loading world content, constructing the database store or acquiring a world lease. Missing paths, bad pairs, invalid dates, unsuitable server certificates and SAN mismatches produce actionable errors with the exact paths. The service retains direct TLS 1.2 minimum and normal browser trust requirements. Public plaintext peers remain rejected.

Setup changes only network fields, retains other configuration text and creates an exclusive original-config backup. It validates a staged pair before saving. New certificate/key folders never overwrite old ones, failed precommit saves roll back only newly created material, concurrent config edits are rejected, and postcommit cleanup failures retain the now-active files. Generated player kits contain only a public certificate, instructions and optional trust commands. The private key stays server-only.

## Executed checks

| Check | Result |
|---|---|
| Full Python regression suite in a clean build snapshot | 255 discovered; **254 passed, 1 skipped**; 19.353 seconds |
| Certificate setup regressions | 13 passed: generation/import, SAN/key rejection, database/comment/newline preservation, rollback, concurrent edits, renewal, IPv6 and bind adjustment |
| World startup lifecycle regressions | 18 passed, retaining logging, cleanup and safe ownership behavior |
| TLS configuration and real network regressions | 11 passed, including verified HTTPS and authenticated WSS; unknown trust, wrong hostname and plaintext rejected |
| Separate CLI-to-server smoke | CLI generated fresh files, real server started with them, HTTPS health and WSS account registration passed, clean shutdown exit 0 |
| Generated certificate strict validation | OpenSSL strict server-certificate verification passed; smoke client also required trust, hostname matching and strict X.509 checks |
| Native content publisher | Same pack `e05cb982d1fd4137629f86b0`; 859 maps, 876 entries, 10,902 PNGs and all 2,366 audio clips verified |
| Source preservation | Entire Client tree byte-identical to 1.2.1; database Store and world content byte-identical; previous Go rejection fix preserved |
| Python syntax | 48 source files parsed successfully |

The generated certificate used by the smoke test was a disposable local fixture and is not distributed. Tests used temporary explicit SQLite databases and synthetic accounts, with no production database connection or user credentials.

## Platform boundaries

Tests ran with Python 3.12.14, aiohttp 3.13.5 and cryptography 46.0.0. The release's dependency/toolchain pins remain unchanged from 1.2.1. Windows, Microsoft Edge, PowerShell, Go and a live MySQL daemon were unavailable here. The skipped test is the native Windows PowerShell bootstrap check. The Windows trust command and Tk window received code review, but were not executed on Windows; that is not presented as a passing platform test. The user's screenshot independently establishes that their previous compiled world reached its MySQL/TLS startup stages.

`BUILD_ALL.bat` still runs its Python suite, Go tests/vet, Windows compilation and launcher smoke checks on the build PC. The prior Windows connection-reset correction and PowerShell HOME correction are retained. The package contains source and ready-to-use audio, not precompiled Windows executables.

Installing player trust is an explicit operation in the generated kit. Its fixed inline PowerShell command does not change execution policy, displays the host/fingerprint, and adds the exact verified certificate object only after confirmation. It does not bypass TLS validation or carry a private key. Public DNS, Windows Firewall, port forwarding, ISP reachability and trust on the actual player PC still need the deployment checks in `ONLINE_HOSTING.md`.

## Evidence

- `evidence/online_setup_1.2.2_python_tests.txt`
- `evidence/online_setup_1.2.2_generated_tls_smoke.json`
- `evidence/online_setup_1.2.2_content_validation.txt`
- `evidence/online_setup_1.2.2_validation.json`

Historical audio and 1.2.1 build-fix reports remain included. This change does not regenerate or reduce audio coverage.
