# Test report · 0.1.0-alpha

Date: 2026-09-12. Content pack: `0a8cdb1a321bac58cdfce7e6`.

## Executed checks

| Check | Result | Exact scope |
|---|---|---|
| Python regression and integration suite | **51 passed** | 41 content/security/world/store contracts plus 10 real TCP/WebSocket service tests; temporary SQLite databases |
| Client Go tests | **3 passed** | INI parsing, invalid syntax, finite/bounded numeric configuration |
| Client/Server Go static checks | **Passed** | `go vet` for client and Windows server launcher |
| Windows build output | **Produced and inspected** | Client PE32+ GUI x64; server PE32+ console x64; cross-compiled, not executed on Windows |
| Local HTTP shell checks | **13 passed** | Linux build of the same Go client shell; static assets/bootstrap, no secret exposure, Host/CSP/header checks, traversal/listing rejection and heartbeat |
| Two-client UI acceptance | **Passed** | Registration, click-player invitation, movement, General chat, two-sided Pokemon/items/money trade, duel turn/forfeit, capture, party lead change, save/relogin and Johto travel |
| Native network replication | **Passed** | Real aiohttp clients over TCP/WebSocket, no UI bridge; auth, movement/follower packets, Trade chat and disconnect persistence |
| Server restart persistence | **Passed on explicit SQLite** | Native WebSocket reads compared full owned creature records, party IDs, money/items, lead, map and position before/after clean process restart |
| 3840 × 2160 UI layout | **Passed** | No document overflow or JavaScript errors in rendered two-client scenario |
| High-DPI backing canvas | **Passed** | 1920 × 1080 CSS viewport at DPR 2: backing pixels track 2× CSS dimensions; no page overflow or JavaScript errors |
| Asset/reference audit | **Passed** | 859 map grid dimensions, all playable spawns, all five asset references for every catalog entry, matching client/server pack and hash of 10,902 PNG files |
| Python/JS syntax | **Passed** | compileall and Node syntax checks |

The final full Python suite completed in 9.145 seconds in the recorded run. This is a test duration, not a game-performance measurement. Logs and machine-readable results are in `Docs/evidence`.

## Client UI test method — important

The available Chromium environment disallowed normal URL navigation. The render harness therefore placed the local, unchanged UI HTML/CSS/JavaScript into a page and supplied local assets through a test bridge. UI WebSocket calls were forwarded through aiohttp to a real, isolated world service. Browser policies were not changed. The isolated fixture creates a temporary SQLite database, uses a temporary world port, performs actual UI clicks and shuts that fixture down.

This exercises layout, rendering, interaction and real gameplay messages, but is **not a native Edge app launch or native browser WebSocket acceptance test**. Real network protocol tests are separate and do not use that bridge. The Go static-serving endpoint was also tested separately. The whole Windows chain — EXE to Edge, local HTTP module loading, browser WebSocket, Windows firewall, display monitors and database driver — still needs on-PC acceptance.

Snapshots in `Docs/screenshots` are captures from the running UI scenario, not generated concept art. They show actual parsed map assets and client components. They do not establish that every imported map was manually inspected.

## Runtime/toolchain used here

Linux; Python 3.13.5; aiohttp 3.13.3; Playwright 1.57.0; installed Chromium; Go 1.23.2. Pillow 12.3.0 and numpy 2.3.5 were used for extraction. Those extraction dependencies are not needed by players or by ordinary server gameplay.

The installation requirements pin **aiohttp 3.14.3** and **PyMySQL[rsa] 1.2.0**, verified against their primary package/project documentation for this release. The environment could not install those exact packages or run a MySQL daemon. Therefore the shipped dependency combination is **not the exact combination used in local runtime tests**. Run the test suite again in the Windows server virtual environment after setup. The MySQL branch is implemented, but the MySQL acceptance checklist remains open.

## Specific regression coverage

Tests include strict name/password/number validation, independent password salts, rate-bucket behavior, map dimensions/spawns, corrected FireRed learnsets, type immunities, stable unique ownership, same-name registration rejection, duplicate active login rejection, the hard-cap admission path, movement timing/sequence replay/collision, follower anchoring, region isolation, global chat naming/privacy, invitations, atomic exchange, changed/stale offers, digest checks, quantity and last-Pokemon rules, database-failure rollback, disconnect cancellation, ownership on party changes, purchases, capture/full-collection handling, friendly-duel clone/forfeit behavior, stale autosave rejection, writer lease/fencing and bounded queue closure.

Network tests open real sockets to the service with temporary isolated databases. They cover health metadata, untrusted Origin rejection, unauthenticated gameplay, mismatched content, wrong/unknown credentials, registration and duplicate login, two-client movement/follower replication and Trade chat, malformed/non-finite commands, oversized packets and reconnecting to a saved location.

## Not verified

**No Windows executable was run. No MySQL/MariaDB deployment was runtime-tested. No direct-TLS certificate deployment was tested. No 1,000-socket load test was performed.** No long-duration soak, packet-loss simulation, penetration test, multi-monitor hardware test, database failover, updater/installer/signing or complete map-by-map original story comparison has been completed.

The 1,000-cap regression populates the World admission path with 1,000 in-memory player records and rejects number 1,001. It does not simulate 1,000 actual network sessions, password hashes, database accounts or simultaneous battles/trades. Do not turn this passing limit test into a performance claim.

## Reproduce and accept

From the complete project root after installing server requirements:

```text
Server\.venv\Scripts\python.exe -m unittest discover -s Tests -v
```

On Linux use the corresponding Python interpreter. Tests use temporary SQLite files and do not modify the configured MySQL database. The full Client asset folder is required for content reference tests.

For UI reproduction, install Playwright as a test-only dependency and point `NXT_BROWSER_PATH` at an installed Chromium/Edge executable, then run `python Tests/ui_acceptance.py`. It creates its own temporary world and writes captures under `Tests/ui_artifacts`; its DOM/transport bridge limitation remains the same. It does not test a native Windows app launch. `Tests/check_launcher.py PATH_TO_LAUNCHER` exercises a compiled shell in headless serving mode. Launcher Go tests run from `Client/launcher` with `go test .`.

The remaining on-PC acceptance procedure is in QUICK_START.md and ALPHA_SCOPE.md. Begin with private local/LAN testing, confirm the server console identifies MySQL, and preserve the first working deployment as the next baseline only after real persistence and two-PC checks pass.
