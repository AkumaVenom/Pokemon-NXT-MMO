# Autonomous Trainer Long-Uptime Performance Hardening

Release: **0.6.4-alpha · Autonomous Trainer Performance Hardening**  
Database schema: **3 (unchanged)**

## Problem addressed

The autonomous systems were functionally correct, but several persistence paths multiplied database work as the 2,000 trainers accumulated larger persistent Pokémon collections and personality history. The result could present as a healthy world at startup followed by increasingly severe MySQL disk activity, latency spikes and groups of visible bots apparently freezing together.

The central issue was **I/O amplification**, not the configured bot population or the gameplay simulation itself. Full `state_json` / `personality_json` payloads grow naturally as bots capture Pokémon, gain EXP, evolve and record travel/progression state. Previous runtime paths repeatedly fetched and decoded those growing blobs even though the world process already owned the only valid writer lease and already held the same authoritative population in memory.

## Root causes removed

### Repeated full-population snapshot reloads

Normal runtime previously reloaded all autonomous trainer rows on a timer and also forced a full reload after background-field and ranked passes. With 2,000 trainers this meant repeatedly reading and decoding the entire population, including every growing Pokémon collection, merely to reconstruct state that the same leased process had just written.

**0.6.4 contract:** normal world ticks do not perform a population reload. A full snapshot is now an explicit reconciliation operation (`force=True`) used for startup, migrations, recovery and tests that deliberately mutate storage out of band.

### Ranked query fan-out

A competitive pass previously combined several expensive patterns:

1. fetch due trainers with their complete JSON state;
2. reload each actor again;
3. query up to 24 complete candidate JSON rows per actor;
4. read recent opponents separately per actor;
5. commit pairs independently; and
6. reload the complete 2,000-trainer snapshot after the pass.

**0.6.4 contract:** due selection and rating-near candidate selection are computed from the authoritative in-memory population. Recent opponent IDs for the bounded due cohort are fetched once, all pair outcomes are developed on detached copies, and the final changed trainer states plus activity rows are committed in one lease-fenced transaction.

### Per-bot field commits

The off-screen field scheduler can process up to 16 trainers every two seconds. Previously each successful field action could open and commit its own transaction, followed by another full population reload. Visible field travel/wild outcomes likewise committed independently when several bots acted during the same world tick.

**0.6.4 contract:** off-screen field outcomes share one transaction per scheduler pass. Visible strong field outcomes share one transaction per world tick. Ordinary visible walking already used a dirty-state batch and retains that behavior.

### Repeated activity-retention deletes

The 45-day `ai_activity` cleanup query previously ran on every recorded autonomous activity write. Although indexed, repeatedly issuing the same retention delete on a hot activity table created avoidable index/transaction work.

**0.6.4 contract:** the 45-day retention rule is unchanged, but pruning occurs at most once per hour. Startup migration also idempotently creates `(actor_ai_id, opponent_kind, created_at)` to support bounded recent-opponent lookup.

## Authority and transaction model

The optimization does **not** weaken persistence authority.

- The database world lease still guarantees one world writer.
- Startup still loads and reconciles the durable autonomous population before gameplay.
- All autonomous mutations remain lease-fenced and transactional.
- Strong field outcomes persist full state/personality clocks; only routine public activity-feed sampling remains intentionally sampled exactly as before for off-screen ordinary wins.
- Competitive simulation uses detached working copies. Live in-memory bot state is updated only after the batch transaction succeeds.
- Field batching keeps the existing live mutation model; if a batched field write fails, only the touched bots are reconciled from durable storage on that exception path.
- Human-vs-bot ranked development also uses a detached bot copy. The human profile, bot result, rivalry and activity row commit atomically before that result is adopted into live memory.
- Explicit forced snapshot refresh remains available where storage was intentionally changed outside normal live mutation paths.

## Gameplay invariants deliberately preserved

No performance fix was implemented by lowering the population, slowing configured schedules or deleting features. The following remain unchanged:

- 2,000 persistent autonomous trainers by default;
- 24-trainer bounded competitive simulation batch every 8 seconds;
- 16-trainer off-screen field batch every 2 seconds;
- up to 8 materialized autonomous trainers per map;
- real wild battles through the shared Battle engine;
- real captures, collection growth, party optimization, supplies and money;
- authoritative EXP, levels and supported level evolution;
- regional travel, safety retreat, progression and resident-floor logic;
- Elo rating, tiers, W/L, recent-opponent suppression and AI Activity;
- human ranked challenges and rivalry persistence;
- shared-world bot movement/follower replication and map cohort stability.

## Upgrade from 0.6.3-alpha

1. Back up the configured world and MySQL database.
2. Stop the old world so it releases the database lease.
3. Build/deploy matching **0.6.4-alpha Client and Server** files.
4. Keep the existing configured `Server/config.ini`, database, certificates and private deployment files.
5. Start the 0.6.4 world normally. The supporting activity index is created idempotently by the existing migration path.

Do **not** reset the database, delete autonomous trainers, rerun MySQL provisioning, lower the bot population or wipe bot collections. Schema remains version 3.

## Runtime acceptance / soak validation

For the target Windows + MySQL deployment, the important acceptance test is sustained uptime rather than only a fresh-start smoke test:

1. Start with the normal `population = 2000`, `background_field_batch = 16`, `background_field_interval_seconds = 2` and `simulation_batch = 24` settings.
2. Leave the world running beyond the time at which the old build normally developed stalls.
3. Keep one or more clients on maps with materialized bots and verify movement remains continuous rather than freezing in synchronized bursts.
4. Observe `mysqld` disk throughput and server latency. Routine autonomous work should no longer show the old repeated full-population read pattern.
5. Verify off-screen bot captures/levels continue, AI Activity continues, ranked bot W/L and ratings move, and human-vs-bot challenges still save.
6. Restart the world and verify the progressed trainer state persists.

The automated regression suite validates the architectural no-fan-out/no-full-refresh contracts. The final hardware-specific MySQL disk graph is necessarily a deployment acceptance measurement because storage engine settings, disk cache, database history and Windows host load are outside the source test environment.

## Regression coverage

`Tests/test_autonomous_performance.py` guards the performance architecture directly:

- normal snapshot refresh performs zero database snapshot reads;
- forced refresh remains available and does perform one explicit reconciliation read;
- one off-screen batch commits all due field outcomes once and never reloads the population;
- one competitive pass uses one recent-opponent cohort read and one batch commit while legacy due/actor/candidate full-JSON query APIs are forbidden in that path;
- multiple visible field outcomes in the same tick share one commit;
- the 45-day activity-retention DELETE is issued at most once per hour rather than once per recorded action.

Existing `test_autonomous_world_life.py` and `test_autonomous_evolution.py` remain the functional regressions ensuring performance work did not remove travel, captures, persistence, party identity or evolution.
