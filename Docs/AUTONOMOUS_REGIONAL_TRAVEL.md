# Autonomous Trainer Regional Travel — 0.6.0-alpha (stabilized by 0.6.1)


> **0.6.1 stability addendum:** regional travel remains the progression model described below, but observed maps now materialize a stable bounded cohort, ordinary travel uses dwell-time hysteresis and a resident floor, and observed departures are staggered. Destination safety is a hard filter before population pressure. See `AUTONOMOUS_POPULATION_STABILITY.md` for the current visible-population contract.

## Problem corrected

The 0.5.x overworld-life implementation gave each autonomous trainer a persistent field map. That made bots visible, but it also made initial placement effectively permanent. A level-5 bot that happened to be assigned to a high-level route/cave could repeatedly recover and fight the same overpowered wild table without a mechanism to leave. Conversely, a successful bot could outgrow a starter route and remain there indefinitely.

0.6.0 changes map placement from a permanent residency rule into a **persistent regional progression controller**.

## Region ownership

A trainer's original player-style `state.home` remains the source of its autonomous travel region:

- `Kanto` home → Kanto travel catalog.
- `Johto` home → Johto / Sigma travel catalog.

Travel never changes that home and never selects a destination from the other region. The existing 2,000-bot alternating home seed therefore remains an exact 1,000 Kanto / 1,000 Johto population unless an administrator intentionally changes persistent trainer data outside this feature.

## Eligible destination policy

The controller does not use every playable level as a destination. A travel map must satisfy all of the following:

1. It is playable in the published world pack.
2. It has genuine local wild-encounter data.
3. It has at least one reachable, walkable, non-Surf tile where the encounter resolver produces a wild table.
4. It belongs to the bot's home region.
5. It is an outdoor route/wilderness class, a cave class, or one of the verified outdoor route/forest/park names from the secondary outdoor map class.

The policy explicitly rejects the ROM indoor/building map class. It also rejects city/town and ordinary island settlement names even if an extracted edge/fishing table would otherwise make them appear encounter-capable. Bots therefore teleport to training areas, not randomly into houses, shops, Pokémon Centers or administrative/interior rooms.

## Encounter-based difficulty profile

Destination difficulty is not a hard-coded route-number table. For each eligible map the server asks the existing encounter resolver for morning, day and night rows on its reachable training tiles. Equivalent rows are deduplicated and the existing encounter weights are retained.

The resulting profile contains:

- minimum wild level,
- maximum wild level,
- weighted mean wild level,
- weighted 90th-percentile (`q90`) pressure.

The `q90` value is used as the safety guard so a route with a few significantly stronger common encounters is not mislabeled merely because its average looks low.

## Party-strength input

Travel difficulty reads the same persistent party used by followers and battles. The controller takes the average level of the strongest three current party members (or all members when fewer than three exist). It never scans unselected PC/storage Pokémon to inflate travel capability.

This preserves the 0.5.1 identity rule: one owned party drives presentation, combat and progression decisions.

## Travel reasons

### Repair

Used when the persistent map is missing, no longer eligible, outside the trainer's home region or otherwise invalid for autonomous training. This also provides the upgrade path from old fixed residency.

### Unsafe

If the current map's upper encounter pressure exceeds the party's level plus the configured safety allowance, the trainer relocates before another autonomous training action is selected. This is the primary protection for low-level trainers that were previously stuck in endgame caves/routes.

### Retreat

Each real wild loss increments a persistent consecutive-loss counter. At the configured threshold (default 2), the next travel evaluation chooses an easier level-appropriate map. A particularly overleveled opponent can also set retreat pending immediately.

### Progress

Successful wild training increments a persistent per-map win counter. When the trainer has outgrown the map by the configured margin and has demonstrated the configured number of wins, it selects a harder destination. Very large overlevel differences can trigger advancement without forcing more trivial wins.

### Routine

Every trainer also has a deterministic bounded travel timer (default 180–540 seconds). When it expires, the bot rotates to another near-level destination. Recent maps are penalized so this becomes real regional movement rather than an A/B loop.

## Destination scoring

Candidate scoring combines:

- distance from the desired wild level for the current party,
- heavy penalty for unsafe `q90` pressure,
- heavy penalty when even the minimum encounter level is too high,
- recent-map penalty,
- penalty for fields far below the bot's capability,
- direction bias (progression prefers harder than current; retreat prefers easier),
- resident-pressure spreading among already level-safe destinations,
- deterministic per-bot/per-travel variation.

Only near-best candidates participate in final deterministic rotation. In 0.6.1, unsafe candidates are removed before this scoring step; population pressure can spread safe choices but can never force a low-level bot upward merely to reduce crowding.

## Teleport semantics

Regional travel is deliberately **not** pathfinding through doors, gates or multi-map connections. When travel is approved, the server directly changes the bot's map and chooses a valid local training tile. The relocation:

- updates map, X/Y, facing and revision,
- clears stale field runtime/busy path state,
- moves the bot between server map indexes,
- persists travel history and counters,
- schedules its next routine travel,
- records a readable AI Activity event.

After arrival, ordinary GBA-style tile walking resumes on that map.

## Observed and offline behavior

On a map containing human players, high-frequency `field_tick` operates only the stable materialized cohort. Ordinary visible departures are staggered, and a single departure preserves the rest of the cohort instead of rebuilding all visible membership.

When nobody is online, the existing bounded due simulation checks the same travel controller before wild/ranked activity. Ordinary elapsed-time travel is deferred for maps currently observed by humans so it cannot race the field controller. Unobserved maps continue bounded simulation normally.

## Upgrade behavior

No SQL schema change is required. 0.6.1 advances the autonomous metadata to `worldLifeVersion = 3` and `travelVersion = 2`. At startup, older 0.6.0 residents receive a one-time population-stability rebalance through the same region/level-safe catalog, repairing both overcrowded and drained placement while preserving trainer/Pokémon identity.

The migration preserves:

- bot ID and username,
- Red/Leaf identity,
- rating/tier/W-L history,
- rival/activity history,
- complete owned Pokémon collection,
- authoritative party UID order,
- Pokémon levels, EXP, moves, variety and ownership.

## Configuration

```ini
travel_min_seconds = 180
travel_max_seconds = 540
travel_loss_retreats = 2
travel_safe_level_margin = 4
travel_progress_level_margin = 4
travel_map_win_target = 4
```

These are server settings. Changing them affects selection timing/policy; it does not rewrite player progress or create Pokémon.
