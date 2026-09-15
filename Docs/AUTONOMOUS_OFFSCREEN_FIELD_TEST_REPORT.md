# Autonomous Off-Screen Field Simulation — Validation Report

Release: 0.6.2-alpha
Date: 2026-09-16

## Reported regression

Autonomous trainers only performed real wild battles/captures when a human player was present on the same map, making off-screen progression unreliable.

## Fix

Field progression now uses a dedicated persistent `nextBackgroundFieldAt` clock, completely separate from ranked `next_action_at`. The world tick invokes the background field scheduler regardless of online player count. Only exact bots in an observed map's materialized cohort are excluded, because those trainers are already eligible for visible field simulation.

## Focused acceptance coverage

- Zero connected humans, zero active maps: a due autonomous trainer completes a real wild Battle-engine action and persists its changed state.
- A human observing a different map does not suppress the bot's off-screen progression.
- A non-materialized resident on an observed map still progresses in the background.
- A materialized trainer is excluded from background progression to prevent double-simulation.
- Existing party UID identity, population stability, regional travel and persistence tests remain green.
- Routine background wins are sampled in the public activity feed while captures, level-ups and losses are always retained, avoiding unbounded activity-table growth.

## Executed validation

- `Tests.test_autonomous_world_life`: 5/5 passed after the fix.
- Key release/content/bootstrap/source-selection suite: 39/39 passed.
- Client/UI Node regression suite: 103/103 passed.
- Python syntax compilation: 98 files passed.
- Go launcher tests/vet: client and server launchers passed.
- Version/manual-catalog/CRLF release-contract checks: 3/3 passed.

The complete monolithic release-builder regression pass was attempted in this container but exceeded the tool execution window while its Python test stage was still progressing without a reported failure. The focused and cross-system checks above are the executed evidence for this source package; run `BUILD_ALL.bat` on the target Windows machine for the normal full production build verification.
