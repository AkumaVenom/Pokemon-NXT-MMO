# Native learnsets release validation · 0.3.1-alpha

Validated on 2026-09-13. Build tools 1.3.1 preserve the accepted adventure,
starter/account replication, progressive saving, online setup and startup fixes.

## Completed release build

The normal `python Build/build.py --no-open` pipeline succeeded using a fresh
isolated Python 3.12.14 environment with production dependency pins enforced.
The host was Linux x64 with Go 1.27.1. Both Windows x64 launchers compiled and
passed executable architecture/subsystem checks. Build ID:
`build-20260913-060934-718602Z`; content pack:
`48b614f4eb0c035bc6fab073`. The build completed in 303.8 seconds after staging.

| Executed gate | Result |
| --- | --- |
| Python syntax | 75 files passed |
| Python regression and real-network suite | 469 run: 468 passed, one native PowerShell platform skip |
| Go tests and Windows static checks | Passed |
| Windows client GUI / server console compilation | Both x64 executables verified |
| Real HTTP launcher checks | 26 passed |
| Audio engine checks | 29 passed |
| JavaScript integration tests | 67 passed: 8 audio integration plus 59 registration, replication, adventure and learnset tests |
| JavaScript module syntax | Passed |
| Client, server and complete build ZIPs | Created, decompressed and verified by the build |

## Native data and learning coverage

The two exact supplied ROMs were re-read with `Tools/extract_learnsets.py --check`.
The result matches the bundled sidecar: all 876 published profiles are covered,
874 have intact lists and two have independently bounded native-prefix recoveries.
All 28 previous Sigma fallback lists are replaced. The audit also covers all
1,776 source manifest indices without treating invalid or unpublished slots as
new supported species. Cyndaquil's Ember is level 12 in both sources.

New checks exercise native order, repeated levels, absent level-one entries,
bounded malformed data, the two recovery witnesses, exact source identities,
seven separate Sigma move IDs, matching client/server publication, explicit
trainer move mappings and native Sigma sound bindings in both regional banks.

Runtime and real TCP tests cover:

- Cyndaquil progressing through level 12 via battle EXP, with Ember and spent
  PP surviving database restart and login.
- Initial four-slot selection, duplicate native rows and empty native lists
  using the existing Struggle path instead of invented Tackle.
- Multiple earned choices, stale-queue reconciliation, evolution, decline,
  trade and durable login migration without recreating declined choices.
- Move Reminder ownership, level/species eligibility, slot bounds, sparse IDs,
  duplicate attempts and explicit replacement.
- Failed database saves leaving both live and stored moves/PP unchanged, with
  no success notice/audio; a later successful retry persists through login.
- One-time, source-proven Sigma identity conversion preserving slots and spent
  PP; source-specific queues, ambiguous moves and repeated login are covered.
- Stale client sessions, changed Pokémon state, pending-choice priority,
  duplicate submits and modal invalidation during map changes.
- Source-parameter Sigma move behavior and independent accuracy/Special Defense
  stages, alongside existing combat and audio event regressions.

## Asset and deployment preservation

Every PNG, OGG and WAV was compared by SHA-256 with the accepted 0.3.0 source:
all 11,110 PNGs, 818 OGGs and 1,548 WAVs are unchanged. The catalog gains bindings
for the seven move identities; no art or sound is regenerated. The published
pack retains 959 maps and 2,366 verified audio clips.

Source staging excludes live configuration, database files, certificates,
private keys and build caches. The full-source download is split into seven
mergeable ZIPs, each below 100 MiB. Packaging decompresses every member and
checks it against the complete `SOURCE_SHA256SUMS.txt` manifest, including a
union check for missing or duplicated files.

## Limits of this validation

The tests ran on Linux, including real local TCP, TLS and SQLite persistence.
Native Windows PowerShell execution is explicitly skipped, and native Edge UI,
a live MySQL/MariaDB deployment, public internet routing and 1,000 concurrent
players were not exercised. Windows compilation is not a substitute for those
checks. Deploy matching Client/Server output while preserving working database,
configuration and TLS files.

This release corrects native learnset data and learning flow; it does not claim
complete original-ROM battle-script compatibility. Shared FireRed profiles
remain canonical in either region. Sigma's source type 9 remains unchanged;
modern Fairy, Terastal and other unverified move mechanics are not inferred
from move names. See `LEARNSET_ROM_AUDIT.md` and `ALPHA_SCOPE.md` for the exact
source and combat boundaries.
