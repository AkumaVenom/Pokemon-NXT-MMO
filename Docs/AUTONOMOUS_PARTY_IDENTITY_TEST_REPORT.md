# Autonomous Trainer Party Identity — Executed Validation Report

**Gameplay:** 0.5.1-alpha  
**Correction:** Authoritative bot party identity  
**Content pack:** `94efbf2aab380cbd08baad5e`  
**Release build:** `build-20260915-021909-206213Z`

## Defect reproduced and corrected

0.5.0 rendered an autonomous trainer's overworld follower from the first UID in its persistent `state.party`, but human ranked challenges rebuilt the opponent roster by scanning `state.creatures`. Automatic party optimisation can deliberately reorder `state.party` without reordering storage, so the visible follower and battle lead could disagree. The earlier 0.4.0/0.5.0 bootstrap also inserted up to two deterministic synthetic Pokémon immediately after the starter rather than requiring those Pokémon to be captured.

0.5.1 makes the ordered persistent party UID list the single materialisation source for the follower, team-strength/development calculations, autonomous wild battles, and human-vs-bot ranked battles. Fresh autonomous trainers begin with exactly one starter. A one-time migration recognizes only the deterministic legacy bootstrap entries and removes those entries while preserving genuine later captures and their remaining party order.

## Focused identity regression

Executed `Tests/check_autonomous_trainers.py` and `Tests.test_autonomous_world_life` successfully.

The regression deliberately stores Pokémon in collection order that differs from the bot's party order. It verifies that:

- the replicated map entity's `followerUid`, species, level and variety come from `state.party[0]`;
- the human ranked-battle opponent roster uses the exact UID sequence in `state.party`;
- the ranked-battle lead UID/species/level is the same Pokémon shown as the overworld follower;
- fresh databases seed all 2,000 autonomous trainers with only one owned starter each;
- the known legacy deterministic bootstrap extras are removed on migration;
- a genuine captured Pokémon appended later is retained;
- the remaining persistent party order is retained after migration;
- world population coverage, movement, wild training/capture and persistence continue to pass.

Result: **2/2 autonomous world-life unit tests passed**, plus the autonomous static regression script passed.

## Full Python regression

Executed the complete test discovery suite against the corrected source:

- tests run: **603**
- passed: **602**
- expected platform skip: **1**
- failures: **0**
- errors: **0**
- runtime in the direct full-suite validation: **136.663 seconds**

The expected skip is a platform-specific check and is not a gameplay failure.

## Seven-stage release build

The project's production release builder completed successfully from the corrected source in **209.9 seconds after staging**. Its staged clean-source workflow reported:

- Python syntax validation: passed;
- Python regression suite: 603 run, 602 passed, 1 expected skip;
- Go launcher tests: passed;
- Windows Go vet: passed;
- Windows x64 client executable cross-compilation and PE validation: passed;
- Windows x64 world-server executable cross-compilation and PE validation: passed;
- HTTP/content/security smoke checks: passed;
- JavaScript syntax/client integration tests: passed;
- Node client/UI regression suite: **103/103 passed**;
- extracted audio/content publication: passed;
- generated Client ZIP verification: passed, 18,157 files;
- generated Server ZIP verification: passed, 62 files;
- generated Complete ZIP verification: passed, 18,482 files.

Generated executable SHA-256 values from the build evidence:

- `Pokemon NXT MMO.exe`: `6d12152fbff143096aed0493c71e607fdde5da374ac6384de890a3726425a589`
- `Pokemon NXT World Server.exe`: `b681825795af6c84df37e00b11825d00e79c58048a1ae1cfd07a99c1fe76cd9c`

## Validation boundary

This release build ran on a Linux x86_64 build host and cross-compiled/validated the Windows x64 executables. It did not execute the native Edge application UI, a production MySQL/MariaDB deployment, TLS deployment, or a 1,000-concurrent-session load test. Those remain target-environment acceptance items. The user's normal Windows `BUILD_ALL.bat` path installs and checks its pinned production Python dependencies separately.

## Runtime acceptance to perform on the persistent game database

After backing up the current database and deploying matching 0.5.1 client/server builds, choose a visible autonomous trainer and note the follower species/level. Challenge that exact bot and confirm the first opponent is the same Pokémon. Let the bot capture/train and allow party optimisation, repeat the check, then restart the world server and verify the same authoritative party/follower relationship persists.
