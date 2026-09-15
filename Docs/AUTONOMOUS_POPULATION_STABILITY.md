# Autonomous Trainer Population Stability — 0.6.1-alpha

## Purpose

0.6.1 corrects two regressions introduced by the first regional-travel implementation: very large logical resident groups could collapse into the same visible grass area, and nearest-resident selection plus unrestricted departures could cause trainers to blink in/out and eventually leave an observed field with no autonomous population.

The fix does **not** fake or clone trainers. The same persistent 2,000 database-owned trainers, their real Pokémon UIDs, parties, ratings and travel state remain authoritative.

## Stable materialization

Persistent residency and live rendering are now separate concerns. A map may contain many simulated residents, but an observing client receives at most the configured `visible_per_map` cohort. Cohort membership is stable by trainer ID and map and is not recomputed from nearest-distance ordering every frame. A legitimate departure removes only that trainer and fills only that one vacancy; it does not reshuffle every visible bot.

When a cohort is first materialized, its trainers are placed on real walkable encounter tiles using a deterministic farthest-spacing pass. Those positions are server-authoritative and persisted. Each visible trainer receives a local roam anchor and stays within the configured territory while walking/training, preventing a previously scattered cohort from reconverging onto one small grass patch.

## Travel hysteresis and population floors

Regional travel remains server-authoritative and level-aware, but normal movement between maps now has stability rules:

- routine/progression travel waits for `travel_min_dwell_seconds` after entering a map;
- loss-driven retreat waits for the shorter `travel_retreat_dwell_seconds`, while invalid or truly unsafe placements can still escape immediately;
- ordinary departures cannot reduce an occupied training map below `map_resident_floor`;
- an observed map permits at most one visible departure per `active_map_departure_seconds`;
- elapsed-time simulation defers ordinary travel for maps currently observed by humans so it cannot race the visible field controller;
- destination selection treats level safety as a hard constraint and uses meaningful resident-pressure scoring only among safe candidates.

## Upgrade behavior

`WORLD_LIFE_VERSION=3` and `REGIONAL_TRAVEL_VERSION=2` trigger a one-time autonomous-only population rebalance for older 0.6.0 saves. Human characters and bot Pokémon/ratings/histories are not reset. Existing bots are re-placed only through real level-safe encounter maps in their own region, then the new stable-cohort rules take over.

No SQL schema bump is required; the stability metadata uses the existing autonomous personality/state records.

## Preserved contracts

- exact persistent party UID order remains the source for follower, wild battle and ranked battle identity;
- Kanto bots remain in Kanto and Johto/Sigma bots remain in Johto/Sigma;
- interiors, cities/towns and non-training maps remain excluded from autonomous travel;
- captures and levels still come from genuine server Battle-engine wild activity;
- only the bounded live cohort walks at high frequency; the rest of the 2,000 population continues elapsed-time simulation.
