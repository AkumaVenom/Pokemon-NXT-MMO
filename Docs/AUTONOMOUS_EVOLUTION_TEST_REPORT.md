# Autonomous Trainer Evolution Validation Report

Release: **0.6.3-alpha · Autonomous Trainer Level Evolution**  
Validation date: **2026-09-16**

## Scope

This release adds autonomous acceptance of authored **level-based** Pokémon evolutions for the persistent 2,000-trainer population. The AI does not rewrite species directly. Eligibility and mutation are delegated to the existing server-authoritative `Growth.options()` / `Growth.evolve()` path used by normal gameplay.

The evolution contract preserves the owned Pokémon UID and persistent identity across species changes. Party order therefore remains UID-based, and overworld followers plus wild/ranked battle rosters automatically resolve the evolved species from the same owned record.

Stone and trade methods are deliberately not fabricated by autonomous code. They still require their real gameplay prerequisites.

## Focused regression coverage

`Tests/test_autonomous_evolution.py` validates two independent progression paths:

- Real autonomous wild-battle EXP: a level-15 Charmander earns the required EXP, reaches level 16, evolves through `Growth.evolve()` into Charmeleon, keeps the same UID and party slot, persists the new species, and immediately exposes that evolved species through the overworld follower entity.
- Ranked autonomous development: a level-15 Bulbasaur gains the required level through ranked development and evolves into Ivysaur while preserving its UID and party identity.
- Legacy v0.6.2 repair: an overdue autonomous starter is repaired through the same authored level rules, including a multi-stage overdue chain where appropriate.
- Conservative captured-Pokémon repair: a later capture is repaired only when saved EXP proves post-capture progression. A freshly captured high-level lower-stage Pokémon is not forcibly evolved merely because its capture level is above the normal threshold.
- Non-level conditions: Pikachu remains unevolved without a real evolution stone and Kadabra remains unevolved without a real trade event.

Focused evolution and autonomous-world-life tests passed before the production build.

## Full staged release build

The project's production builder was run against a clean staged snapshot of this exact source tree:

`python Build/build.py --root . --existing-environment --no-open`

Result: **BUILD SUCCEEDED** in **257.2 seconds after staging began**.

Validation results recorded by the build:

- Python regression suite: **608 run, 607 passed, 1 skipped, 0 failures/errors**.
- The single skip is the explicit native Windows PowerShell execution test; this build host is Linux and does not simulate it as passed.
- Go client tests: **passed**.
- Go server-launcher tests: **passed**.
- `go vet`: **passed**.
- Windows x64 client cross-compilation: **passed**; GUI PE subsystem verified.
- Windows x64 world-server cross-compilation: **passed**; console PE subsystem verified.
- Headless launcher HTTP/security smoke checks: **passed**.
- Node/browser regression suite: **103/103 passed**.
- Generated client release ZIP: verified.
- Generated server release ZIP: verified.
- Generated complete release ZIP: verified.

Build evidence identifier: `build-20260915-175322-633028Z`.

## Environment boundary

The release builder was intentionally run with its explicit **existing-environment developer verification** mode because this container does not provide the Windows bootstrap environment. Accordingly, production Python dependency pins were **not** asserted by this build. The Windows `BUILD_ALL.bat` path remains unchanged and performs its normal isolated pinned-dependency installation/verification on the target build machine.

The Linux validation also cross-compiled and structurally verified the Windows binaries; it did not execute the native Windows GUI itself. MySQL/MariaDB deployment, TLS deployment, and 1,000 concurrent network sessions remain normal target-environment acceptance tests rather than claims made by this build.

## Acceptance focus

For runtime acceptance, observe an autonomous trainer whose lead Pokémon is one level below an authored evolution threshold. Allow it to gain the level through wild or ranked autonomous progression. Verify that the same trainer now shows the evolved species as its follower, uses that same UID/species in battle, and retains the evolution after a world-server restart.
