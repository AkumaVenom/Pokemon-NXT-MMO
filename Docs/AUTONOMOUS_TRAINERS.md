# Autonomous Trainer World Life — 0.6.2-alpha

Pokemon NXT MMO maintains a persistent population of **2,000 autonomous trainers**. They are server-owned simulation actors rather than login accounts, so they cannot authenticate or collide with human credentials. The ranked ladder/rivals system, visible world actors and authoritative party identity remain in place; 0.6.0 introduced region-aware travel and progression; 0.6.1 stabilizes the visible map population so travel cannot cause crowding, rapid cohort churn or empty observed maps.

## Authoritative party identity

A bot has exactly one authoritative Pokémon collection and one authoritative ordered `state.party` UID list. The first UID is the overworld follower, and **that same ordered UID list** is cloned into wild battles and human-vs-bot ranked battles. Battle code may heal a temporary duel copy, but it may not generate, substitute, reorder or invent Pokémon.

Fresh autonomous trainers begin with **one level-5 starter only**. Additional Pokémon must be earned through real autonomous wild battles and captures. The accepted 0.5.1 legacy cleanup remains versioned and removes only the deterministic unearned bootstrap extras created by older releases while preserving genuine captures and party order.

## Dynamic regional travel — 0.6.0 / population stability — 0.6.1

Autonomous trainers are no longer permanent residents of a single map.

- Kanto-home bots remain in Kanto. Johto-home bots remain in Johto/Sigma. Autonomous travel never crosses a trainer's home-region boundary.
- Eligible destinations must have genuine encounter data and reachable non-Surf training tiles. Ordinary route/wilderness map classes and caves are included; verified outdoor route/forest/park maps from the secondary outdoor class are also accepted.
- Interior/building maps are excluded. Cities, towns and ordinary island settlement maps are excluded even when extracted edge/fishing encounter data exists. A bot therefore does not use shops, houses, Pokémon Centers or other interiors as random training destinations.
- Destination difficulty is computed from the **published local encounter tables** across morning/day/night. The travel profile stores minimum, maximum, weighted mean and 90th-percentile encounter level pressure.
- Destination selection compares that real encounter pressure with the bot's current core-party level. Safety is now a hard eligibility constraint before population balancing; recent destinations are penalized and equivalent safe choices receive deterministic variation plus meaningful resident-pressure spreading.
- Fresh level-5 trainers are migrated away from dangerous endgame fields before autonomous training can continue there.
- A map whose encounter pressure is too high triggers an immediate **unsafe retreat**.
- Repeated wild losses trigger a **retreat** to an easier level-appropriate map.
- Trainers that have outgrown their current map and accumulated enough successful wild training trigger **progression travel** toward a harder but still safe map.
- A bounded **routine travel** timer rotates trainers between comparable areas even when neither retreat nor advancement is required. 0.6.1 adds a minimum map dwell before routine/progression travel, a shorter retreat dwell, a persistent resident floor, and a one-visible-departure cadence for observed maps.
- Travel is a server-authoritative relocation, not simulated walking through map connections. The bot is placed directly on a valid encounter tile in the chosen destination and resumes ordinary GBA-style movement there.

Travel state is persistent in existing personality JSON: home travel region, version, travel count, recent maps, entry/last/next travel times, consecutive wild losses and per-map wild wins/losses. No SQL schema bump is required.

## GBA-style field movement

Only maps with connected human observers run high-frequency tile movement, and only a **stable bounded cohort** from that map is materialized. Logical residents beyond the cohort continue server-side simulation without being rendered or stepped at high frequency. This prevents nearest-N churn and makes observed maps stable.

- Bot steps use the same walkability/elevation/collision rules and tile cadence contract as human movement.
- Server state replicates the new tile plus the prior trainer tile as the follower anchor. The existing browser renderer interpolates authoritative tile changes and uses normal directional walking frames.
- Bots avoid solid map objects, warps, other materialized trainers and connected human positions when selecting a visible step.
- When a cohort is materialized it is authoritatively scattered across real encounter terrain. Each member keeps a local roam anchor/radius so the group does not reconverge onto one grass patch.
- Training-oriented bots seek real encounter terrain and wander within their local training territory rather than pacing only on decorative roads.
- Position and direction are batched to persistent storage. Travel relocations are committed immediately as autonomous activity events.

## Real wild battles, captures and training

Autonomous field development uses the **same `Battle` combat engine** as human wild encounters rather than a cosmetic outcome roll.

- The encounter resolver selects species and level from the bot's actual current map/tile.
- Bots make legal attacks, switches, healing-item uses and capture attempts based on their real party and capture personality.
- Move PP, HP/status outcomes, captures and battle experience are applied back to the persistent bot collection.
- Captured Pokémon enter storage or an open party slot. Bots can optimise their six-Pokémon party from Pokémon they actually own.
- The first real party Pokémon remains the visible follower and ranked-battle lead.
- Bots spend their own money to replenish bounded basic Poké Balls and Potions.
- Wild wins grant the established small field-money reward; defeats recover the party so the autonomous actor can continue.
- Wild outcomes feed the travel controller. Repeated losses schedule retreat; successful development can schedule advancement.
- Visible field battles briefly mark the actor busy and AI Activity records the resulting training/capture event.

## Offline / elapsed-time development

All 2,000 trainers continue to progress with no humans online. Due simulation is bounded per pass. Before each eligible autonomous action, the travel controller evaluates the bot's current map and persistent travel state. A due retreat, advancement, routine rotation or invalid-map repair is executed first; otherwise the bot performs genuine wild development or ranked competition.

This means an offline trainer can move to another appropriate route/cave, train there, capture Pokémon, grow its party and later advance again without a browser session or permanent high-frequency actor.

## Competitive simulation

- Rating-aware autonomous trainer-vs-trainer matchmaking with Elo-style movement.
- Recent-opponent suppression prevents repetitive farming loops.
- Persistent wins, losses, rating, ranking tier and activity history.
- Strong bots can naturally rise to Master and Champion tiers; weaker bots can fall.
- Human ranked challenges remain player-initiated only. Bots never issue unsolicited human challenges.
- Human rating, W/L and rivalry records are saved transactionally with bot results. Friendly human-vs-human duels remain unchanged.

## Shared-world materialization

All 2,000 trainers exist persistently, but a client receives only a stable bounded cohort for its current map. Cohort membership is map-stable rather than nearest-distance based, so normal player movement or tiny bot steps do not swap trainers in and out. Materialized bots are shared server entities: two humans observing the same area receive the same bot IDs, positions, movement, real follower and busy state.

When one bot legitimately travels away, only that bot leaves; unaffected cohort members remain and only the single vacancy is filled. Observed maps throttle visible departures and ordinary travel cannot reduce an occupied map below its resident floor. High-frequency walking still runs only on maps containing humans; the bounded elapsed-time system drives unobserved travel and development.

## UI and activity

The right-side gameplay panel retains **AI Activity**, **Ranking Ladder** and **Rivals Hub**. The ladder remains one combined human + autonomous ranking and AI rows expose direct ranked challenges. The activity feed can contain ranked results, wild training/captures and regional travel summaries.

## Persistence and configuration

Schema 3 remains authoritative and continues to use `ai_trainers`, `competitive_profiles`, `ai_activity` and `ai_rivals`. Travel metadata fits the existing trainer personality JSON; map/position and owned Pokémon remain in authoritative state JSON. Activity older than 45 days remains bounded by pruning.

`[autonomous_trainers]` defaults:

```ini
population = 2000
simulation_batch = 24
simulation_interval_seconds = 8
visible_per_map = 8
field_step_ms = 160
field_persist_seconds = 2
field_battle_display_seconds = 2.8
field_wild_cooldown_seconds = 7
field_wild_step_chance = 0.22
field_wild_battles_per_tick = 2
background_field_interval_seconds = 2
background_field_batch = 16
background_field_min_gap_seconds = 45
background_field_max_catchup_actions = 6
travel_min_seconds = 180
travel_max_seconds = 540
travel_loss_retreats = 2
travel_safe_level_margin = 4
travel_progress_level_margin = 4
travel_map_win_target = 4
travel_min_dwell_seconds = 240
travel_retreat_dwell_seconds = 60
map_resident_floor = 6
active_map_departure_seconds = 90
materialized_spacing_tiles = 6
materialized_roam_radius_tiles = 9
```

The travel interval controls routine rotation only. Invalid/unsafe repair may bypass ordinary dwell because leaving a dangerous field is a safety operation. Retreat/progression/routine movement uses hysteresis and map-presence protection. On observed maps, elapsed-time simulation defers ordinary travel to the field controller so the two schedulers cannot race each other. Competitive/offline simulation and field work intentionally remain outside the main gameplay actor lock. Database mutations remain world-lease fenced and transaction protected.

For the current materialization/travel stability contract see `Docs/AUTONOMOUS_POPULATION_STABILITY.md`. The underlying regional progression design remains documented in `Docs/AUTONOMOUS_REGIONAL_TRAVEL.md`.


## Off-screen field simulation (0.6.2-alpha)

Wild progression is not tied to a connected player, an observed map, or the competitive queue. The world service runs a separate bounded field scheduler for every non-materialized autonomous trainer. It uses the trainer's real persistent party, real map encounter table and the shared Battle engine, then commits captures, EXP/levels, supplies and travel state to storage. A connected client only changes presentation: the currently materialized cohort is handled by the visible field loop so the same bot is never progressed twice.
