# Starter, replication, login and saving validation — 1.2.3

This report covers the corrected full source, including the existing audio and online setup fixes. Verification ran on Linux with Python 3.12.14 and Node.js. Runtime source files were compared byte-for-byte with the clean validation snapshot before packaging.

## Results

| Check | Result |
| --- | --- |
| Python regression and integration coverage | **303 unique tests passed; 1 Windows-only PowerShell check skipped** |
| Complete initial Python run | 303 discovered: 302 passed, 1 skipped, 37.489 seconds |
| Final persistence module, including one additional scheduler test | 11 passed, 5.265 seconds; 10 overlap the initial run |
| Python syntax | 54 files passed |
| Client registration, session, renderer and audio integration | 34 tests passed |
| Audio engine lifecycle | 29 checks passed |
| Included audio catalog and file hashes | 2,366 clips verified: 818 OGGs and 1,548 WAVs |
| Windows script line endings | BAT/CMD CRLF retained |

There are **304 unique Python cases** in the final source. The two Python runs are recorded separately above rather than adding overlapping cases to the total. Evidence is in `Docs/evidence/replication_1.2.3_*`.

## Starter and account regression coverage

The actual client handlers reproduced the reported failure: Charmander followed by Johto submitted Chikorita. Corrected handlers retain each of the six starters in either region. Tests cover default selection, rapid edits, Enter/click submission paths, connection delays, rejected authentication, retry, missing responses, logout and login.

The real TCP/WebSocket suite creates all **12 starter/region combinations concurrently**, verifies separate account IDs and creature UIDs, checks each owner's private party and public follower, then logs every account out and back in. Deliberately different home/starter values on login do not change saved characters. Missing or malformed selections, duplicate/case-duplicate names, concurrent same-name registration, forged saves and foreign creature IDs are rejected without replacing another account's progress.

Login lifecycle tests use the production password hashing and verification path, including case-insensitive usernames and passwords containing Unicode/spaces. They verify account progress after a new Service/Store instance, explicit cooldown messages, idle connections not exhausting login attempts, invalid stored hashes failing verification, active duplicate-session rejection and overlapping logout/relogin ordering. The stale-load test failed when the old pre-admission load was reintroduced in an isolated test process.

## Replication and saving coverage

Owner state, packet snapshots, movement, stationary follower changes, map/radius departures, logout, party order, trades and duel privacy are exercised with independent accounts. The renderer tests delay and reorder local map fetch completion while applying incoming scene updates. No shared private state or stale player scene may survive a session reset.

Persistence tests exercise purchases, item use, healing, captured creatures, party order, XP, level gains, money, HP/PP, Surf, travel/home and an actual extracted-map warp. A fresh Store and World load these committed changes **without calling logout or manual save first**. The production periodic save loop also runs at the configured five-second interval and saves later movement automatically before a cold restart.

Injected database failures verify that failed durable actions do not publish success or change committed progress. Cancellation during a blocked SQL purchase cannot separate its committed state from live publication. Older in-flight autosaves cannot overwrite a newer committed revision or mark a replacement session as saved.

## Build and platform limits

The all-in-one build now includes the new Python tests and, when Node is installed, the registration/renderer tests. Source selection, clean configuration staging, manifests, archive helpers and existing build regressions passed. The previous Go download and PowerShell HOME corrections remain in the source.

**Native Windows/PowerShell execution and Go compilation were not available in this environment.** The full Windows `BUILD_ALL.bat` run is therefore not claimed as executed here. Neither are native Edge UI acceptance, a live MySQL/MariaDB service, public-router deployment or 1,000 concurrent sessions. SQLite and loopback/TLS tests exercise production application paths but do not establish those deployment results.

The release includes no character-specific repair and performs no account/database reset. It retains the existing alpha scope and extracted audio; it does not add unimplemented original campaign systems or promise that software is free of every possible defect.
