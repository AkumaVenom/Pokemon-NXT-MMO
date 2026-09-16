"""Persistent autonomous trainers with competitive and visible overworld life.

Durable storage owns persistence while the leased world process owns the
authoritative in-memory runtime image of the full 2,000-trainer population.
Trainers remain bound to their home region but dynamically relocate between real
outdoor/cave encounter maps chosen for their current party strength. Only a
stable bounded cohort on maps with connected humans runs high-frequency field
movement; all other trainers continue through bounded elapsed-time simulation,
including regional travel and genuine wild battles.
"""
from __future__ import annotations

import asyncio
import collections
import copy
import math
import time
from collections import deque

from .combat import Battle, matchup
from .encounters import encounter_slots, select_encounter
from .security import RequestError, integer, require
from .varieties import variety_key

TIERS = ((0, 'Bronze'), (1100, 'Silver'), (1300, 'Gold'),
         (1550, 'Platinum'), (1800, 'Master'), (2100, 'Champion'))
WORLD_LIFE_VERSION = 3
PARTY_IDENTITY_VERSION = 1
REGIONAL_TRAVEL_VERSION = 2
BACKGROUND_FIELD_VERSION = 1
AUTONOMOUS_LEVEL_EVOLUTION_VERSION = 1
TRAVEL_MAP_TYPES = frozenset((3, 4))
TRAVEL_OUTDOOR_WORDS = ('route ', 'forest', 'national park', 'ruins of alph')
DIRECTIONS = (
    ('down', 0, 1),
    ('up', 0, -1),
    ('left', -1, 0),
    ('right', 1, 0),
)


def tier_for(rating):
    name = 'Bronze'
    for threshold, label in TIERS:
        if rating >= threshold:
            name = label
    return name


def elo(a, b, score, k=24):
    expected = 1 / (1 + 10 ** ((b - a) / 400))
    return max(0, int(round(a + k * (score - expected))))


class AutonomousTrainers:
    """Server-owned autonomous population and materialized field actors."""

    # Published map geometry and encounter tables are immutable for a content-pack
    # digest. Reuse the expensive training-tile and difficulty scans across World
    # instances (including clean restart/regression fixtures) without caching any
    # mutable bot state.
    _TRAINING_POINTS_CACHE = {}
    _TRAVEL_PROFILE_CACHE = {}
    _TRAVEL_CATALOG_CACHE = {}

    def __init__(self, world):
        self.w = world
        self.c = world.c
        self.db = world.db
        self.s = world.s
        self.lock = asyncio.Lock()
        self.last_simulation = 0.0
        self.last_background_field = 0.0
        self.background_cursor = 0
        self.last_persist = 0.0
        self.snapshot = []
        self.snapshot_at = 0.0
        self.by_id = {}
        self.by_map = collections.defaultdict(list)
        self.runtime = {}
        self.dirty = set()
        self.engaged = {}
        self.blocked_cache = {}
        # Materialization is intentionally separate from persistent residency. A
        # map may have many simulated residents, but only a stable bounded cohort
        # is replicated/moved while humans are present. This prevents nearest-N
        # churn, nameplate piles and mass travel flicker.
        self.materialized = {}
        self.materialized_layout = {}
        self.active_departure_at = {}

        self.population = self._cfg('population', 2000)
        self.batch = self._cfg('simulation_batch', 24)
        self.interval = self._cfg_float('simulation_interval_seconds', 8.0)
        self.world_per_map = self._cfg('visible_per_map', 12)
        self.field_step = max(self.s.step_ms / 1000.0,
                              self._cfg('field_step_ms', self.s.step_ms) / 1000.0)
        self.field_persist = max(0.5, self._cfg_float('field_persist_seconds', 2.0))
        self.field_battle_seconds = max(1.0, self._cfg_float('field_battle_display_seconds', 2.8))
        self.field_wild_cooldown = max(2.0, self._cfg_float('field_wild_cooldown_seconds', 7.0))
        self.field_wild_chance = min(1.0, max(0.0, self._cfg_float('field_wild_step_chance', 0.22)))
        self.field_wild_per_tick = max(1, self._cfg('field_wild_battles_per_tick', 2))
        # Off-screen field life has its own scheduler. It must never depend on a
        # human observing the map or on the ranked queue winning a probabilistic
        # branch. Only materialized bots are excluded to avoid double-simulating
        # a trainer that is already performing visible field actions.
        self.background_field_interval = max(.5, self._cfg_float('background_field_interval_seconds', 2.0))
        self.background_field_batch = max(1, self._cfg('background_field_batch', 16))
        self.background_field_min_gap = max(15, self._cfg('background_field_min_gap_seconds', 45))
        self.background_field_max_catchup = max(1, self._cfg('background_field_max_catchup_actions', 6))
        self.travel_min_seconds = max(60, self._cfg('travel_min_seconds', 180))
        self.travel_max_seconds = max(self.travel_min_seconds, self._cfg('travel_max_seconds', 540))
        self.travel_loss_retreats = max(1, self._cfg('travel_loss_retreats', 2))
        self.travel_safe_margin = max(1, self._cfg('travel_safe_level_margin', 4))
        self.travel_progress_margin = max(1, self._cfg('travel_progress_level_margin', 4))
        self.travel_map_win_target = max(1, self._cfg('travel_map_win_target', 4))
        self.travel_min_dwell = max(60, self._cfg('travel_min_dwell_seconds', 240))
        self.travel_retreat_dwell = max(15, min(self.travel_min_dwell, self._cfg('travel_retreat_dwell_seconds', 60)))
        self.map_resident_floor = max(1, self._cfg('map_resident_floor', 6))
        self.active_departure_seconds = max(30, self._cfg('active_map_departure_seconds', 90))
        self.materialized_spacing = max(2, self._cfg('materialized_spacing_tiles', 6))
        self.materialized_roam_radius = max(self.materialized_spacing, self._cfg('materialized_roam_radius_tiles', 9))

    def _cfg(self, key, default):
        return self.s.config.getint('autonomous_trainers', key, fallback=default)

    def _cfg_float(self, key, default):
        return self.s.config.getfloat('autonomous_trainers', key, fallback=default)

    async def initialize(self):
        """Seed missing IDs, upgrade field-life metadata and load the world snapshot."""
        async with self.lock:
            ids = set(await asyncio.to_thread(self.db.ai_ids))
            missing = [i for i in range(1, self.population + 1) if i not in ids]
            if missing:
                records = []
                now = int(time.time())
                starters = list(self.c.data['starters'])
                homes = list(self.c.data['homes'])
                for i in missing:
                    name = f'NXTBot{i:04d}'
                    home = homes[(i - 1) % len(homes)]
                    # Autonomous trainers now begin exactly like a real player: one
                    # persistent starter. Every later party member must come from a
                    # real captured Pokemon already owned in this bot's state.
                    state = self.w.initial(name, home, starters[(i * 7) % len(starters)], 0 if i % 2 else 7)
                    rating = 850 + (i * 29) % 351
                    records.append({
                        'id': i,
                        'username': name,
                        'rating': rating,
                        'tier': tier_for(rating),
                        'state': state,
                        'personality': {
                            'aggression': .35 + ((i * 17) % 60) / 100,
                            'capture': .15 + ((i * 31) % 55) / 100,
                            'training': .30 + ((i * 13) % 60) / 100,
                            'activity': 45 + (i * 19) % 180,
                            'partyIdentityVersion': PARTY_IDENTITY_VERSION,
                            'legacySyntheticPokemonRemoved': 0,
                            'levelEvolutionVersion': AUTONOMOUS_LEVEL_EVOLUTION_VERSION,
                        },
                        'next_action_at': now + (i % 90),
                    })
                for start in range(0, len(records), 200):
                    await asyncio.to_thread(self.db.ai_seed, records[start:start + 200])
            await self._refresh_snapshot_locked(force=True)
            await self._ensure_party_identity_locked()
            await self._ensure_autonomous_level_evolution_locked()
            await self._ensure_world_distribution_locked()
            await self._ensure_background_field_schedule_locked()
            await self._refresh_snapshot_locked(force=True)

    # ------------------------------------------------------------------
    # Authoritative party identity
    # ------------------------------------------------------------------

    def _party_members(self, bot, *, clone=False):
        """Return the bot's persistent party in its authoritative UID order.

        The ordered state['party'] list is the single source of truth for the
        overworld follower, wild battles and human-vs-bot battles.  Never rebuild
        a battle team by scanning collection order: collection order is storage,
        not party order.
        """
        state = bot['state']
        creatures = state.get('creatures', [])
        owned = {mon.get('uid'): mon for mon in creatures}
        party_ids = list(state.get('party', []))
        if not party_ids or len(party_ids) > 6 or len(set(party_ids)) != len(party_ids):
            raise RuntimeError(f'Autonomous trainer {bot["id"]} has an invalid persistent party list.')
        if any(uid not in owned for uid in party_ids):
            raise RuntimeError(f'Autonomous trainer {bot["id"]} party references an unowned Pokemon.')
        members = [owned[uid] for uid in party_ids]
        return copy.deepcopy(members) if clone else members

    async def _ensure_party_identity_locked(self):
        """One-time repair of the legacy synthetic bootstrap party members.

        0.4.0/0.5.0 created `id % 3` extra Pokemon immediately after each
        starter.  They were not earned in a wild battle.  Their positions and
        deterministic species are unambiguous, while genuine captures were always
        appended later, so we can remove only those legacy bootstrap records
        without guessing at legitimate captured Pokemon.
        """
        species = list(self.c.species)
        updates = []
        for bot in self.snapshot:
            personality = bot.setdefault('personality', {})
            if int(personality.get('partyIdentityVersion', 0) or 0) >= PARTY_IDENTITY_VERSION:
                continue
            state = bot['state']
            creatures = list(state.get('creatures', []))
            legacy_count = bot['id'] % 3
            removed_ids = set()
            if legacy_count and len(creatures) >= 1 + legacy_count:
                candidates = creatures[1:1 + legacy_count]
                expected = [species[(bot['id'] * 37 + j * 83) % len(species)]
                            for j in range(legacy_count)]
                recognized = all(
                    mon.get('species') == expected[j]
                    and mon.get('originalTrainer') == bot['username']
                    for j, mon in enumerate(candidates))
                if recognized:
                    removed_ids = {mon['uid'] for mon in candidates}
                    state['creatures'] = [creatures[0], *creatures[1 + legacy_count:]]
                    owned = {mon['uid'] for mon in state['creatures']}
                    state['party'] = [uid for uid in state.get('party', [])
                                      if uid not in removed_ids and uid in owned]
                    if not state['party'] and state['creatures']:
                        state['party'] = [state['creatures'][0]['uid']]
                    state['revision'] = int(state.get('revision', 0)) + 1
            personality['partyIdentityVersion'] = PARTY_IDENTITY_VERSION
            personality['legacySyntheticPokemonRemoved'] = len(removed_ids)
            updates.append(bot)
        for start in range(0, len(updates), 200):
            await asyncio.to_thread(self.db.ai_rebalance_world, updates[start:start + 200])

    # ------------------------------------------------------------------
    # Persistent off-screen field schedule
    # ------------------------------------------------------------------

    def _background_cadence(self, bot):
        # Personality activity already expresses how frequently this trainer acts.
        # Keep field life frequent enough to be observable over time while retaining
        # per-trainer variation and avoiding a 2,000-bot thundering herd.
        activity = max(self.background_field_min_gap, int(bot.get('personality', {}).get('activity', 120) or 120))
        return activity + (int(bot['id']) * 11) % 31

    async def _ensure_background_field_schedule_locked(self):
        """Add a persistent, staggered field clock to existing and new bots.

        This deliberately lives in personality JSON rather than next_action_at: the
        latter belongs to ranked/competitive activity. Separating the clocks means
        wild training continues even when no human is online and cannot be starved by
        repeated ranked actions.
        """
        now = int(time.time())
        updates = []
        spread = max(60, min(300, self.population // max(1, self.background_field_batch) * max(1, int(self.background_field_interval))))
        for bot in self.snapshot:
            personality = bot.setdefault('personality', {})
            if int(personality.get('backgroundFieldVersion', 0) or 0) >= BACKGROUND_FIELD_VERSION:
                continue
            personality['backgroundFieldVersion'] = BACKGROUND_FIELD_VERSION
            personality['nextBackgroundFieldAt'] = now + ((bot['id'] * 37) % spread)
            personality['lastBackgroundFieldAt'] = 0
            personality['backgroundWildBattles'] = int(personality.get('backgroundWildBattles', 0) or 0)
            updates.append(bot)
        for start in range(0, len(updates), 200):
            await asyncio.to_thread(self.db.ai_rebalance_world, updates[start:start + 200])

    def _advance_background_due(self, bot, now):
        personality = bot['personality']
        cadence = self._background_cadence(bot)
        due = int(personality.get('nextBackgroundFieldAt', now) or now)
        # Preserve bounded elapsed-time catch-up after downtime. At most the
        # configured number of historical field actions remain queued so a long
        # outage cannot monopolize the server on restart.
        oldest = now - cadence * max(0, self.background_field_max_catchup - 1)
        due = max(due, oldest)
        personality['lastBackgroundFieldAt'] = now
        personality['nextBackgroundFieldAt'] = due + cadence
        personality['backgroundWildBattles'] = int(personality.get('backgroundWildBattles', 0) or 0) + 1

    def _background_field_action_locked(self, bot, now):
        """Advance one due off-screen trainer entirely in memory.

        Persistence is intentionally deferred to ``background_field_tick`` so a
        16-bot scheduler pass becomes one MySQL transaction instead of sixteen
        independent commits.  The caller still persists every authoritative
        state/personality change; only public activity-feed rows are sampled.
        """
        if self.engaged.get(bot['id'], 0) > time.monotonic():
            return None
        reason = self._travel_reason(bot, now)
        if reason:
            travel = self._relocate_bot(bot, reason, now)
            if reason in ('repair', 'unsafe') and not travel:
                bot['personality']['nextBackgroundFieldAt'] = now + self.background_field_min_gap
                return {'processed': False, 'rebalance': True}
        if not self._place_on_training_tile(bot):
            # A malformed/temporarily unsuitable field should not spin every tick.
            bot['personality']['nextBackgroundFieldAt'] = now + self.background_field_min_gap
            return {'processed': False, 'rebalance': True}
        result = self._simulate_wild_battle(bot)
        if not result:
            bot['personality']['nextBackgroundFieldAt'] = now + self.background_field_min_gap
            return {'processed': False, 'rebalance': True}
        self._advance_background_due(bot, now)
        # Persist every field result, but keep the public activity table bounded:
        # captures, level-ups and losses are always noteworthy; routine wins are
        # sampled deterministically instead of producing millions of feed rows.
        action_count = int(bot['personality'].get('backgroundWildBattles', 0) or 0)
        notable = (result['result'] in ('capture', 'loss') or bool(result.get('levels'))
                   or bool(result.get('evolutions')) or (bot['id'] * 17 + action_count) % 20 == 0)
        return {
            'processed': True,
            'record': {
                'bot': bot,
                'event': {'kind': 'wild', 'opponent': 0, 'result': result['result'],
                          'summary': result['summary']},
                'record_activity': notable,
            },
        }

    async def background_field_tick(self, active_maps):
        """Progress off-screen trainers even when there are zero connected humans.

        ``active_maps`` affects presentation only. A bot is skipped solely when it
        is part of the currently materialized cohort on an observed map, because
        that exact trainer is already eligible for visible field simulation. Other
        bots on the same map continue background training normally.

        All due bot writes are committed in one bounded batch.  Crucially, the
        already-authoritative in-memory population is *not* re-read from MySQL
        afterwards; doing that every two seconds caused the complete 2,000-row JSON
        population to be deserialized repeatedly and was the dominant long-uptime
        disk/latency spike.
        """
        if time.monotonic() - self.last_background_field < self.background_field_interval:
            return 0
        async with self.lock:
            if time.monotonic() - self.last_background_field < self.background_field_interval:
                return 0
            self.last_background_field = time.monotonic()
            now = int(time.time())
            materialized = set()
            for map_id in active_maps:
                materialized.update(bot['id'] for bot in self._materialized_bots(map_id))
            bots = self.snapshot
            if not bots:
                return 0
            processed = 0
            inspected = 0
            total = len(bots)
            field_records = []
            rebalance = []
            while inspected < total and processed < self.background_field_batch:
                index = self.background_cursor % total
                self.background_cursor = (self.background_cursor + 1) % total
                inspected += 1
                bot = bots[index]
                if bot['id'] in materialized:
                    continue
                due = int(bot.get('personality', {}).get('nextBackgroundFieldAt', 0) or 0)
                if due > now:
                    continue
                outcome = self._background_field_action_locked(bot, now)
                if not outcome:
                    continue
                if outcome.get('rebalance'):
                    rebalance.append(bot)
                if outcome.get('processed'):
                    processed += 1
                    field_records.append(outcome['record'])
            if rebalance:
                try:
                    await asyncio.to_thread(self.db.ai_rebalance_world, rebalance)
                except Exception:
                    await self._rollback_bots_from_store_locked(bot['id'] for bot in rebalance)
                    raise
            if field_records:
                try:
                    committed_at = await asyncio.to_thread(self.db.ai_commit_fields, field_records)
                except Exception:
                    await self._rollback_bots_from_store_locked(
                        record['bot']['id'] for record in field_records)
                    raise
                for record in field_records:
                    bot = record['bot']
                    bot['last_action_at'] = committed_at
                    self.dirty.discard(bot['id'])
            return processed

    # ------------------------------------------------------------------
    # Authoritative autonomous level evolution
    # ------------------------------------------------------------------

    def _apply_level_evolutions(self, bot, uids=None):
        """Apply only authored level evolutions to owned autonomous Pokemon.

        The normal Growth service remains authoritative for eligibility, HP
        preservation, move queues, evolution history and species transitions.
        This AI layer merely decides *when* an autonomous trainer accepts an
        eligible level evolution. Stone and trade methods are deliberately not
        synthesized: they still require their real item/trade preconditions.

        Returns detached audit records for presentation/tests. The owned UID and
        party order never change.
        """
        state = bot['state']
        wanted = None if uids is None else set(uids)
        selected = [m['uid'] for m in state.get('creatures', [])
                    if wanted is None or m.get('uid') in wanted]
        events = []
        for uid in selected:
            seen_species = set()
            chain = 0
            while chain < 8:
                mon = next((m for m in state.get('creatures', []) if m.get('uid') == uid), None)
                if mon is None:
                    break
                # Growth.options is sourced from the authored ROM evolution table.
                # Preserve that source order instead of inventing an AI-specific
                # branch preference. Unsupported conditions remain unsupported.
                option = next((v for v in self.c.growth.options(mon)
                               if v.get('method') == 'level' and not v.get('deferred')), None)
                if option is None:
                    break
                source = mon['species']
                if source in seen_species:
                    raise RuntimeError(f'Autonomous evolution cycle detected for {bot["username"]} Pokemon {uid}.')
                seen_species.add(source)
                target = option['target']
                candidate = self.c.growth.evolve(state, uid, target)
                # Keep the same state object referenced by the bot/world runtime
                # while adopting the Growth service's detached authoritative copy.
                state.clear(); state.update(candidate)
                evolved = next((m for m in state['creatures'] if m.get('uid') == uid), None)
                if evolved is None or evolved.get('uid') != uid or evolved.get('species') != target:
                    raise RuntimeError('Autonomous evolution violated Pokemon identity.')
                events.append({
                    'uid': uid, 'source': source, 'target': target, 'level': evolved['level'],
                    'sourceName': self.c.species[source]['name'],
                    'targetName': self.c.species[target]['name'],
                })
                chain += 1
            if chain >= 8:
                mon = next((m for m in state.get('creatures', []) if m.get('uid') == uid), None)
                if mon and any(v.get('method') == 'level' and not v.get('deferred')
                               for v in self.c.growth.options(mon)):
                    raise RuntimeError(f'Autonomous evolution chain exceeded safety limit for {bot["username"]} Pokemon {uid}.')
        return events

    async def _ensure_autonomous_level_evolution_locked(self):
        """One-time upgrade for Pokemon that out-levelled evolution in older builds.

        Existing v0.6.2 populations may already contain level-eligible unevolved
        Pokemon. Repair those through the same Growth rules before field/ranked
        simulation resumes, while leaving stone/trade evolutions untouched.
        """
        updates = []
        for bot in self.snapshot:
            personality = bot.setdefault('personality', {})
            if int(personality.get('levelEvolutionVersion', 0) or 0) >= AUTONOMOUS_LEVEL_EVOLUTION_VERSION:
                continue
            state = bot['state']
            candidates = []
            for index, mon in enumerate(state.get('creatures', [])):
                # The first owned Pokemon is the persistent starter in autonomous
                # records. For later captures, require evidence that the Pokemon has
                # actually earned post-capture EXP before repairing an old missed
                # level evolution. This avoids auto-evolving a legitimate wild
                # lower-stage Pokemon merely because it was caught above the usual
                # evolution threshold.
                growth = self.c.species[mon['species']]['growth']
                progressed = int(mon.get('exp', 0)) > self.c.xp(int(mon.get('level', 1)), growth)
                if index == 0 or progressed:
                    candidates.append(mon['uid'])
            events = self._apply_level_evolutions(bot, candidates)
            personality['levelEvolutionVersion'] = AUTONOMOUS_LEVEL_EVOLUTION_VERSION
            personality['legacyLevelEvolutionsRepaired'] = len(events)
            if events:
                state['revision'] = int(state.get('revision', 0)) + 1
            updates.append(bot)
        for start in range(0, len(updates), 200):
            await asyncio.to_thread(self.db.ai_rebalance_world, updates[start:start + 200])

    # ------------------------------------------------------------------
    # Population placement and snapshot indexes
    # ------------------------------------------------------------------

    def _field_blocked(self, m):
        cached = self.blocked_cache.get(m['id'])
        if cached is not None:
            return cached
        blocked = {(o['x'], o['y']) for o in m.get('objects', [])}
        blocked.update((w['x'], w['y']) for w in m.get('warps', []))
        self.blocked_cache[m['id']] = blocked
        return blocked

    def _field_walkable(self, m, state, x, y, from_xy=None):
        if (x, y) in self._field_blocked(m):
            return False
        from_elevation = None
        if from_xy is not None:
            fx, fy = from_xy
            if 0 <= fx < m['width'] and 0 <= fy < m['height']:
                from_elevation = m['elevation'][fy * m['width'] + fx]
        return self.w.walkable(m, x, y, False, from_elevation, state=state)

    def _map_has_training(self, m):
        return bool(m.get('encounters') or m.get('encounterZones'))

    # ------------------------------------------------------------------
    # Region-aware autonomous travel and level-safe training destinations
    # ------------------------------------------------------------------

    @staticmethod
    def _home_region(bot):
        home = bot.get('state', {}).get('home')
        if home == 'Kanto':
            return 'Kanto'
        if home == 'Johto':
            return 'Johto / Sigma'
        return None

    def _travel_map_allowed(self, m):
        """Return whether bots may teleport here for autonomous field training.

        Map type 8 is the ROM's indoor/building class and is intentionally never
        used. Type 3 is the outdoor route/wilderness class and type 4 is caves.
        A small set of type-1 outdoor route/forest/park maps is also legitimate.
        Town/city maps are excluded even if their extracted encounter data includes
        fishing or edge-zone encounters.
        """
        if not m or not m.get('playable', True) or not self._map_has_training(m):
            return False
        map_type = m.get('mapType')
        name = str(m.get('name', '')).strip()
        lower = name.lower()
        if lower.endswith(' city') or lower.endswith(' town') or lower.endswith(' island'):
            return False
        if map_type in TRAVEL_MAP_TYPES:
            return bool(self._training_points(m))
        if map_type == 1 and any(word in lower for word in TRAVEL_OUTDOOR_WORDS):
            return bool(self._training_points(m))
        return False

    def _travel_profile(self, m):
        key = (self.c.pack, m['id'])
        if key in self._TRAVEL_PROFILE_CACHE:
            return self._TRAVEL_PROFILE_CACHE[key]
        if not self._map_has_training(m):
            self._TRAVEL_PROFILE_CACHE[key] = None
            return None
        points = self._training_points(m)
        if not points:
            self._TRAVEL_PROFILE_CACHE[key] = None
            return None
        samples = []
        low = 101
        high = 0
        seen = set()
        # Use morning/day/night so Johto travel remains valid across the clock.
        # De-duplicate identical rows from many grass tiles; row weights then remain
        # the authoritative encounter weighting rather than map-area size.
        for x, y in points:
            probe = {'x': x, 'y': y, 'surf': False}
            for hour in (6, 12, 22):
                for row in encounter_slots(m, probe, hour=hour):
                    key = (row['species'], row['min'], row['max'], row['weight'],
                           tuple(row.get('levelWeights', ())))
                    if key in seen:
                        continue
                    seen.add(key)
                    low = min(low, row['min'])
                    high = max(high, row['max'])
                    mean = (row['min'] + row['max']) / 2.0
                    samples.extend([mean] * max(1, min(100, int(row['weight']))))
        if not samples:
            self._TRAVEL_PROFILE_CACHE[key] = None
            return None
        samples.sort()
        q90 = samples[min(len(samples) - 1, int((len(samples) - 1) * .90))]
        profile = {
            'id': m['id'], 'name': m['name'], 'region': m['region'],
            'min': int(low), 'max': int(high), 'mean': sum(samples) / len(samples),
            'q90': float(q90), 'mapType': m.get('mapType'),
        }
        self._TRAVEL_PROFILE_CACHE[key] = profile
        return profile

    def _travel_catalog(self, region):
        key = (self.c.pack, region)
        cached = self._TRAVEL_CATALOG_CACHE.get(key)
        if cached is not None:
            return cached
        profiles = []
        for m in self.c.maps.values():
            if m.get('region') != region or not self._travel_map_allowed(m):
                continue
            profile = self._travel_profile(m)
            if profile:
                profiles.append(profile)
        profiles.sort(key=lambda p: (p['mean'], p['q90'], p['name'], p['id']))
        self._TRAVEL_CATALOG_CACHE[key] = tuple(profiles)
        return self._TRAVEL_CATALOG_CACHE[key]

    def _party_level(self, bot):
        levels = sorted((int(mon.get('level', 1)) for mon in self._party_members(bot)), reverse=True)
        if not levels:
            return 1.0
        core = levels[:min(3, len(levels))]
        return sum(core) / len(core)

    def _travel_metadata(self, bot, now=None):
        now = int(time.time()) if now is None else int(now)
        personality = bot.setdefault('personality', {})
        region = personality.get('travelRegion') or self._home_region(bot)
        if region not in ('Kanto', 'Johto / Sigma'):
            current = self.c.maps.get(bot.get('state', {}).get('map'))
            region = current.get('region') if current else 'Kanto'
        personality['travelRegion'] = region
        personality.setdefault('travelVersion', REGIONAL_TRAVEL_VERSION)
        personality.setdefault('travelCount', 0)
        personality.setdefault('recentMaps', [])
        personality.setdefault('consecutiveWildLosses', 0)
        personality.setdefault('mapWildWins', 0)
        personality.setdefault('mapWildLosses', 0)
        personality.setdefault('mapEnteredAt', now)
        personality.setdefault('lastTravelAt', 0)
        if not int(personality.get('nextTravelAt', 0) or 0):
            personality['nextTravelAt'] = now + self._travel_delay(bot)
        return personality

    def _travel_delay(self, bot):
        span = self.travel_max_seconds - self.travel_min_seconds
        if span <= 0:
            return self.travel_min_seconds
        count = int(bot.get('personality', {}).get('travelCount', 0) or 0)
        return self.travel_min_seconds + ((bot['id'] * 97 + count * 53) % (span + 1))

    def _select_travel_map(self, bot, reason='routine', *, exclude_current=True):
        personality = self._travel_metadata(bot)
        region = personality['travelRegion']
        catalog = list(self._travel_catalog(region))
        if not catalog:
            return None
        level = self._party_level(bot)
        current_id = bot['state'].get('map')
        current = self._travel_profile(self.c.maps[current_id]) if current_id in self.c.maps else None
        safe_margin = self.travel_safe_margin + min(6, int(level // 20))
        desired = max(2.0, min(100.0, level + 1.0 + float(personality.get('training', .5)) * 2.5))
        if reason in ('retreat', 'unsafe', 'repair'):
            desired = max(2.0, level - 1.0)
            safe_margin = max(2, self.travel_safe_margin - 1)
        # Safety is a hard constraint, not merely a score. Population pressure may
        # choose among safe maps but can never push a low-level trainer into a
        # stronger field just to make the histogram look balanced.
        safe_catalog = [p for p in catalog
                        if p['q90'] <= level + safe_margin and p['min'] <= level + 2.0]
        if safe_catalog:
            catalog = safe_catalog
        recent = set(personality.get('recentMaps', [])[-5:])
        travel_count = int(personality.get('travelCount', 0) or 0)
        scored = []
        for profile in catalog:
            if exclude_current and profile['id'] == current_id and len(catalog) > 1:
                continue
            risk = max(0.0, profile['q90'] - (level + safe_margin))
            entry_risk = max(0.0, profile['min'] - (level + 2.0))
            score = abs(profile['mean'] - desired) * 10.0 + risk * 90.0 + entry_risk * 120.0
            if profile['id'] in recent:
                score += 34.0
            # Discourage grinding a map far below the bot's current capability.
            if profile['q90'] < level - 8:
                score += (level - 8 - profile['q90']) * 4.0
            if reason == 'progress' and current and profile['mean'] <= current['mean']:
                score += 45.0
            if reason in ('retreat', 'unsafe') and current and profile['q90'] >= current['q90']:
                score += 65.0
            # Population pressure is deliberately meaningful. Persistent residents
            # may outnumber the replicated cohort, but equivalent destinations should
            # still share them instead of collapsing hundreds of trainers onto one
            # mathematically optimal route.
            residents = len(self.by_map.get(profile['id'], ()))
            point_capacity = max(4.0, min(24.0, len(self._training_points(self.c.maps[profile['id']])) / 6.0))
            score += (residents / point_capacity) * 36.0
            score += ((bot['id'] * 131 + travel_count * 17 + sum(map(ord, profile['id']))) % 41) / 10.0
            scored.append((score, profile))
        if not scored:
            return None
        scored.sort(key=lambda row: (row[0], row[1]['q90'], row[1]['id']))
        # Keep selection level-safe. If the best maps are near-equivalent, rotate
        # among them so all 2,000 trainers do not collapse onto one route.
        best = scored[0][0]
        near = [profile for score, profile in scored[:12] if score <= best + 12.0]
        if not near:
            near = [scored[0][1]]
        return near[(bot['id'] + travel_count) % len(near)]

    def _travel_point(self, bot, m):
        points = self._training_points(m)
        if not points:
            return None
        occupied = {(b['state']['x'], b['state']['y']) for b in self.by_map.get(m['id'], ())
                    if b['id'] != bot['id']}
        count = int(bot.get('personality', {}).get('travelCount', 0) or 0)
        start = (bot['id'] * 37 + count * 19) % len(points)
        for offset in range(len(points)):
            point = points[(start + offset) % len(points)]
            if point not in occupied:
                return point
        return points[start]

    def _resident_floor(self, map_id):
        m = self.c.maps.get(map_id)
        if not m or not self._travel_map_allowed(m):
            return 0
        # Small maps still keep a visible presence; larger maps can sustain the
        # configured floor without forcing every resident to be materialized.
        return min(self.map_resident_floor, max(2, len(self._training_points(m)) // 8))

    def _can_depart_map(self, bot, reason):
        """Prevent routine/progression travel from draining a field to zero.

        Invalid or genuinely unsafe placements may always escape. All ordinary
        travel leaves a persistent resident floor so a route does not suddenly
        become empty while the population migrates elsewhere.
        """
        if reason in ('repair', 'unsafe'):
            return True
        current_id = bot.get('state', {}).get('map')
        return len(self.by_map.get(current_id, ())) > self._resident_floor(current_id)

    def _relocate_bot(self, bot, reason, now=None, destination=None):
        now = int(time.time()) if now is None else int(now)
        personality = self._travel_metadata(bot, now)
        if not self._can_depart_map(bot, reason):
            personality['travelPending'] = ''
            personality['nextTravelAt'] = max(int(personality.get('nextTravelAt', 0) or 0), now + self._travel_delay(bot))
            return None
        profile = destination or self._select_travel_map(bot, reason)
        if not profile or profile['id'] == bot['state'].get('map'):
            personality['travelPending'] = ''
            personality['nextTravelAt'] = now + self._travel_delay(bot)
            return None
        m = self.c.maps[profile['id']]
        point = self._travel_point(bot, m)
        if not point:
            return None
        old_map = bot['state'].get('map')
        old_name = self.c.maps.get(old_map, {}).get('name', old_map or 'unknown area')
        state = bot['state']
        state.update(map=m['id'], x=point[0], y=point[1], direction='down', surf=False)
        state['revision'] = int(state.get('revision', 0)) + 1
        personality['travelVersion'] = REGIONAL_TRAVEL_VERSION
        personality['assignedMap'] = m['id']  # retained for old dashboard/save compatibility
        personality['lastTravelMap'] = old_map
        personality['lastTravelAt'] = now
        personality['mapEnteredAt'] = now
        personality['travelCount'] = int(personality.get('travelCount', 0) or 0) + 1
        personality['nextTravelAt'] = now + self._travel_delay(bot)
        personality['travelPending'] = ''
        personality['consecutiveWildLosses'] = 0
        personality['mapWildWins'] = 0
        personality['mapWildLosses'] = 0
        recent = list(personality.get('recentMaps', []))
        if old_map:
            recent.append(old_map)
        personality['recentMaps'] = recent[-5:]
        self.runtime.pop(bot['id'], None)
        self.dirty.discard(bot['id'])
        # Preserve every unaffected member of the observed cohort. Removing the
        # whole map cache here would make one legitimate departure look like eight
        # entities blinking out/in at once. The next cohort lookup fills only the
        # single vacancy. Destination cohorts are likewise left untouched unless
        # they have spare capacity.
        if old_map in self.materialized:
            self.materialized[old_map] = tuple(i for i in self.materialized[old_map] if i != bot['id'])
        self.materialized_layout.pop(old_map, None)
        if self.by_id.get(bot['id']) is bot:
            if old_map in self.by_map:
                self.by_map[old_map] = [b for b in self.by_map[old_map] if b['id'] != bot['id']]
            self.by_map[m['id']].append(bot)
        return {
            'from': old_map, 'to': m['id'], 'profile': profile,
            'summary': f'{bot["username"]} traveled from {old_name} to {m["name"]} for level-appropriate wild training.'
        }

    def _travel_reason(self, bot, now=None):
        now = int(time.time()) if now is None else int(now)
        personality = self._travel_metadata(bot, now)
        pending = personality.get('travelPending')
        state = bot['state']
        current = self.c.maps.get(state.get('map'))
        region = personality['travelRegion']
        if not current or current.get('region') != region or not self._travel_map_allowed(current):
            return 'repair'
        profile = self._travel_profile(current)
        if not profile:
            return 'repair'
        level = self._party_level(bot)
        margin = self.travel_safe_margin + min(6, int(level // 20))
        if profile['q90'] > level + margin:
            return 'unsafe'

        entered = int(personality.get('mapEnteredAt', now) or now)
        dwell = max(0, now - entered)
        if pending == 'retreat' or int(personality.get('consecutiveWildLosses', 0) or 0) >= self.travel_loss_retreats:
            return 'retreat' if dwell >= self.travel_retreat_dwell else None
        if pending == 'progress':
            return 'progress' if dwell >= self.travel_min_dwell else None
        if profile['q90'] + self.travel_progress_margin <= level:
            if (int(personality.get('mapWildWins', 0) or 0) >= self.travel_map_win_target
                    or level - profile['q90'] >= 8) and dwell >= self.travel_min_dwell:
                return 'progress'
        if now >= int(personality.get('nextTravelAt', 0) or 0) and dwell >= self.travel_min_dwell:
            return 'routine'
        return None

    def _record_wild_outcome(self, bot, result):
        personality = self._travel_metadata(bot)
        if result['result'] == 'loss':
            personality['consecutiveWildLosses'] = int(personality.get('consecutiveWildLosses', 0) or 0) + 1
            personality['mapWildLosses'] = int(personality.get('mapWildLosses', 0) or 0) + 1
            if result.get('level', 1) > self._party_level(bot) + 1 or personality['consecutiveWildLosses'] >= self.travel_loss_retreats:
                personality['travelPending'] = 'retreat'
        else:
            personality['consecutiveWildLosses'] = 0
            personality['mapWildWins'] = int(personality.get('mapWildWins', 0) or 0) + 1
            current = self.c.maps.get(bot['state'].get('map'))
            profile = self._travel_profile(current) if current else None
            if profile and profile['q90'] + self.travel_progress_margin <= self._party_level(bot) \
                    and personality['mapWildWins'] >= self.travel_map_win_target:
                personality['travelPending'] = 'progress'

    async def _ensure_world_distribution_locked(self):
        """Upgrade fixed residents into level-safe, region-bound roaming trainers."""
        bots = sorted(self.snapshot, key=lambda b: b['id'])[:self.population]
        if len(bots) != self.population:
            raise RuntimeError(f'Autonomous population incomplete: expected {self.population}, found {len(bots)}')

        updates = []
        now = int(time.time())
        # Clear the static placement load index while planning migration. We rebuild
        # it as bots are assigned so equivalent starter routes share the population.
        planned = collections.defaultdict(list)
        original_by_map = self.by_map
        try:
            self.by_map = planned
            for bot in bots:
                personality = bot.setdefault('personality', {})
                state = bot['state']
                version = int(personality.get('worldLifeVersion', 0) or 0)
                travel_version = int(personality.get('travelVersion', 0) or 0)
                expected_appearance = 0 if bot['id'] % 2 else 7
                personality['travelRegion'] = self._home_region(bot) or personality.get('travelRegion')
                self._travel_metadata(bot, now)
                current = self.c.maps.get(state.get('map'))
                current_profile = self._travel_profile(current) if current and self._travel_map_allowed(current) else None
                level = self._party_level(bot)
                margin = self.travel_safe_margin + min(6, int(level // 20))
                safe_current = bool(
                    current_profile
                    and current.get('region') == personality['travelRegion']
                    and current_profile['q90'] <= level + margin)
                # v2 regional travel is a one-time population-stability rebalance:
                # re-place every older resident through the population-aware selector
                # so maps recover from v0.6.0 crowding/drain state.
                needs_relocation = not safe_current or travel_version < REGIONAL_TRAVEL_VERSION
                needs = (version < WORLD_LIFE_VERSION or travel_version < REGIONAL_TRAVEL_VERSION
                         or state.get('appearance') != expected_appearance or needs_relocation)
                if needs_relocation:
                    destination = self._select_travel_map(bot, 'repair', exclude_current=False)
                    if not destination:
                        raise RuntimeError('No level-safe autonomous travel destination exists for ' + personality['travelRegion'])
                    m = self.c.maps[destination['id']]
                    points = self._training_points(m)
                    if not points:
                        raise RuntimeError('No training tile exists for autonomous destination ' + m['id'])
                    index = (bot['id'] * 37 + len(planned[m['id']]) * 11) % len(points)
                    x, y = points[index]
                    state.update(map=m['id'], x=x, y=y, direction='down', surf=False)
                    personality['assignedMap'] = m['id']
                    personality['lastTravelMap'] = None
                    personality['lastTravelAt'] = now
                    personality['mapEnteredAt'] = now
                    personality['nextTravelAt'] = now + self._travel_delay(bot)
                    personality['travelPending'] = ''
                    personality['consecutiveWildLosses'] = 0
                    personality['mapWildWins'] = 0
                    personality['mapWildLosses'] = 0
                planned[state['map']].append(bot)
                if state.get('appearance') != expected_appearance:
                    state['appearance'] = expected_appearance
                if needs:
                    state['revision'] = int(state.get('revision', 0)) + 1
                    personality['worldLifeVersion'] = WORLD_LIFE_VERSION
                    personality['travelVersion'] = REGIONAL_TRAVEL_VERSION
                    personality.setdefault('fieldHeading', 'down')
                    updates.append(bot)
        finally:
            self.by_map = original_by_map
        for start in range(0, len(updates), 200):
            await asyncio.to_thread(self.db.ai_rebalance_world, updates[start:start + 200])

    def _runtime_for(self, bot):
        s = bot['state']
        rt = self.runtime.get(bot['id'])
        if rt is None or rt.get('map') != s.get('map'):
            rt = {
                'map': s.get('map'),
                'fx': s.get('x', 0),
                'fy': s.get('y', 0),
                'next_step': 0.0,
                'next_wild': 0.0,
                'busy_until': 0.0,
                'field_action': '',
                'wild_species': None,
                'path': [],
                'heading': s.get('direction', 'down'),
                'anchor': (s.get('x', 0), s.get('y', 0)),
            }
            m = self.c.maps.get(s.get('map'))
            if m:
                for _, dx, dy in DIRECTIONS:
                    nx, ny = s['x'] + dx, s['y'] + dy
                    if self._field_walkable(m, s, nx, ny, (s['x'], s['y'])):
                        rt['fx'], rt['fy'] = nx, ny
                        break
            self.runtime[bot['id']] = rt
        return rt

    def _index_snapshot(self):
        self.by_id = {b['id']: b for b in self.snapshot}
        self.by_map = collections.defaultdict(list)
        for bot in self.snapshot:
            self.by_map[bot['state'].get('map')].append(bot)
            self._runtime_for(bot)
        live_ids = set(self.by_id)
        live_maps = set(self.by_map)
        self.materialized = {m: tuple(i for i in ids if i in live_ids and self.by_id[i]['state'].get('map') == m)
                             for m, ids in self.materialized.items() if m in live_maps}
        self.materialized_layout = {m: key for m, key in self.materialized_layout.items() if m in live_maps}

    async def _refresh_snapshot_locked(self, force=False):
        """Reload the complete population only for explicit reconciliation.

        The world lease guarantees a single authoritative server writer.  During
        normal runtime every autonomous mutation is therefore already represented
        in ``self.snapshot``/``self.by_id``.  Periodically SELECTing and decoding
        all 2,000 growing JSON states was redundant and became an enormous MySQL
        read-amplification source after long uptimes.

        ``force=True`` remains available for startup, recovery tools and focused
        regression tests that deliberately mutate storage out-of-band.
        """
        if not force:
            return
        if self.dirty:
            await self._flush_world_locked(force=True)
        self.snapshot = await asyncio.to_thread(self.db.ai_world_snapshot)
        self.snapshot_at = time.monotonic()
        self._index_snapshot()

    async def refresh_snapshot(self, force=False):
        async with self.lock:
            await self._refresh_snapshot_locked(force)

    def _adopt_bot_locked(self, source):
        """Merge a successfully committed detached bot into the live snapshot."""
        target = self.by_id.get(int(source['id']))
        if target is None:
            target = source
            self.snapshot.append(target)
            self._index_snapshot()
            return target
        old_map = target.get('state', {}).get('map')
        target.clear()
        target.update(source)
        new_map = target.get('state', {}).get('map')
        if old_map != new_map:
            if old_map in self.by_map:
                self.by_map[old_map] = [bot for bot in self.by_map[old_map]
                                        if bot['id'] != target['id']]
            if not any(bot['id'] == target['id'] for bot in self.by_map[new_map]):
                self.by_map[new_map].append(target)
            self.runtime.pop(target['id'], None)
            if old_map in self.materialized:
                self.materialized[old_map] = tuple(
                    bot_id for bot_id in self.materialized[old_map] if bot_id != target['id'])
                self.materialized_layout.pop(old_map, None)
        return target

    async def _rollback_bots_from_store_locked(self, bot_ids):
        """Best-effort durable rollback after an exceptional batched write failure.

        Field simulation mutates the live actor before persistence so presentation
        can use the result immediately.  Batching increases the number of actors in
        one transaction, so if that transaction fails restore only those touched
        rows from durable storage.  This slow path is never used during successful
        runtime and therefore cannot reintroduce population-wide read amplification.
        """
        for ai_id in sorted({int(ai_id) for ai_id in bot_ids}):
            try:
                stored = await asyncio.to_thread(self.db.ai_get, ai_id)
            except Exception:
                continue
            if stored is not None:
                self._adopt_bot_locked(stored)
                self.dirty.discard(ai_id)

    # ------------------------------------------------------------------
    # Shared-world entities and field movement
    # ------------------------------------------------------------------

    def entity(self, bot):
        s = bot['state']
        rt = self._runtime_for(bot)
        party = self._party_members(bot)
        lead = party[0]
        now = time.monotonic()
        engaged = self.engaged.get(bot['id'], 0) > now
        busy = rt.get('busy_until', 0) > now or engaged
        action = rt.get('field_action', '') if busy else ('ranked_battle' if engaged else '')
        return {
            'id': f'ai:{bot["id"]}',
            'aiId': bot['id'],
            'autonomous': True,
            'username': bot['username'],
            'map': s['map'],
            'x': s['x'],
            'y': s['y'],
            'direction': s.get('direction', 'down'),
            'appearance': s.get('appearance', 0),
            'follower': lead['species'],
            'followerUid': lead['uid'],
            'followerLevel': lead['level'],
            'shiny': variety_key(lead) == 'shiny',
            'followerVariety': variety_key(lead),
            'fx': rt.get('fx', s['x']),
            'fy': rt.get('fy', s['y']),
            'busy': busy,
            'fieldAction': action,
            'wildSpecies': rt.get('wild_species') if busy and action == 'wild_battle' else None,
            'surf': False,
            'rating': bot['rating'],
            'tier': bot['tier'],
        }

    @staticmethod
    def _map_rank(map_id, bot_id):
        salt = sum((i + 1) * ord(ch) for i, ch in enumerate(map_id))
        return (bot_id * 1103515245 + salt * 2654435761) & 0xFFFFFFFF

    def _materialized_bots(self, map_id):
        """Return a stable bounded cohort for a map, never nearest-N churn."""
        residents = list(self.by_map.get(map_id, ()))
        if not residents:
            self.materialized.pop(map_id, None)
            self.materialized_layout.pop(map_id, None)
            return []
        limit = min(self.world_per_map, len(residents))
        resident_ids = {b['id'] for b in residents}
        chosen = [i for i in self.materialized.get(map_id, ()) if i in resident_ids][:limit]
        if len(chosen) < limit:
            candidates = [b for b in residents if b['id'] not in chosen]
            # Fill the cohort with spatially separated residents. Stable hash order
            # breaks ties, so refreshes do not reshuffle the visible population.
            while candidates and len(chosen) < limit:
                if not chosen:
                    pick = min(candidates, key=lambda b: (self._map_rank(map_id, b['id']), b['id']))
                else:
                    selected = [self.by_id[i]['state'] for i in chosen if i in self.by_id]
                    def key(bot):
                        s = bot['state']
                        distance = min(max(abs(s['x'] - q['x']), abs(s['y'] - q['y'])) for q in selected)
                        return (-distance, self._map_rank(map_id, bot['id']), bot['id'])
                    pick = min(candidates, key=key)
                chosen.append(pick['id'])
                candidates.remove(pick)
        self.materialized[map_id] = tuple(chosen)
        return [self.by_id[i] for i in chosen if i in self.by_id and self.by_id[i]['state'].get('map') == map_id]

    def _ensure_materialized_spacing(self, map_id, bots, human_positions=()):
        """Scatter a newly materialized cohort across real encounter terrain.

        Positions remain authoritative and are persisted; this is not a render-only
        offset. The layout is recalculated only when cohort membership changes.
        """
        ids = tuple(b['id'] for b in bots)
        if self.materialized_layout.get(map_id) == ids:
            return False
        m = self.c.maps.get(map_id)
        points = list(self._training_points(m)) if m else []
        if not points:
            self.materialized_layout[map_id] = ids
            return False
        anchors = list(human_positions)
        changed = False
        # Deterministically rotate the point list per map/cohort so entering the
        # same map after a restart does not collapse everyone onto point zero.
        offset = (sum(self._map_rank(map_id, b['id']) for b in bots) if bots else 0) % len(points)
        ordered = points[offset:] + points[:offset]
        for bot in bots:
            state = bot['state']
            current = (state['x'], state['y'])
            if current in points and all(max(abs(current[0]-x), abs(current[1]-y)) >= self.materialized_spacing for x, y in anchors):
                point = current
            else:
                def score(point):
                    if not anchors:
                        separation = self.materialized_spacing
                    else:
                        separation = min(max(abs(point[0]-x), abs(point[1]-y)) for x, y in anchors)
                    # Stable per-bot tie breaker, after maximizing actual spacing.
                    tie = -(((point[0] * 73856093) ^ (point[1] * 19349663) ^ (bot['id'] * 83492791)) & 0xFFFF)
                    return (separation, tie)
                point = max(ordered, key=score)
                if point != current:
                    state['x'], state['y'] = point
                    state['direction'] = 'down'
                    state['revision'] = int(state.get('revision', 0)) + 1
                    self.runtime.pop(bot['id'], None)
                    self.dirty.add(bot['id'])
                    changed = True
            rt = self._runtime_for(bot)
            rt['anchor'] = point
            rt['path'] = []
            anchors.append(point)
        self.materialized_layout[map_id] = ids
        return changed

    def visible(self, p, radius):
        # Cohort membership is map-stable and intentionally independent of player
        # distance. Only a handful of entities are sent, and off-screen actors are
        # culled by the renderer. This eliminates nearest-N swap flicker.
        return [self.entity(b) for b in self._materialized_bots(p.state['map'])]

    def _training_points(self, m):
        key = (self.c.pack, m['id'])
        if key in self._TRAINING_POINTS_CACHE:
            return self._TRAINING_POINTS_CACHE[key]
        if not self._map_has_training(m):
            self._TRAINING_POINTS_CACHE[key] = ()
            return ()
        probe = {'x': 0, 'y': 0, 'surf': False}
        points = []
        for y in range(m['height']):
            for x in range(m['width']):
                if not self._field_walkable(m, None, x, y):
                    continue
                probe['x'], probe['y'] = x, y
                if encounter_slots(m, probe):
                    points.append((x, y))
        if len(points) > 128:
            stride = max(1, len(points) // 128)
            points = points[::stride][:128]
        points = tuple(points)
        self._TRAINING_POINTS_CACHE[key] = points
        return points

    def _neighbors(self, m, state, pos):
        x, y = pos
        for direction, dx, dy in DIRECTIONS:
            nx, ny = x + dx, y + dy
            if self._field_walkable(m, state, nx, ny, (x, y)):
                yield direction, nx, ny

    def _path_to_training(self, m, state, start):
        goals = set(self._training_points(m))
        if not goals or start in goals:
            return []
        q = deque([start])
        previous = {start: None}
        via = {}
        found = None
        limit = m['width'] * m['height']
        while q and len(previous) <= limit:
            pos = q.popleft()
            for direction, nx, ny in self._neighbors(m, state, pos):
                nxt = (nx, ny)
                if nxt in previous:
                    continue
                previous[nxt] = pos
                via[nxt] = direction
                if nxt in goals:
                    found = nxt
                    q.clear()
                    break
                q.append(nxt)
        if found is None:
            return []
        path = []
        cur = found
        while previous[cur] is not None:
            path.append((via[cur], cur[0], cur[1]))
            cur = previous[cur]
        path.reverse()
        return path

    def _step_bot(self, bot, occupied, now):
        state = bot['state']
        m = self.c.maps.get(state.get('map'))
        if not m:
            return False
        rt = self._runtime_for(bot)
        if now < rt['next_step'] or now < rt['busy_until'] or self.engaged.get(bot['id'], 0) > now:
            return False
        rt['next_step'] = now + self.field_step + (bot['id'] % 5) * .012
        start = (state['x'], state['y'])
        options = list(self._neighbors(m, state, start))
        options = [o for o in options if (o[1], o[2]) not in occupied or (o[1], o[2]) == start]
        if not options:
            return False
        anchor = rt.get('anchor', start)
        bounded = [o for o in options
                   if max(abs(o[1] - anchor[0]), abs(o[2] - anchor[1])) <= self.materialized_roam_radius]
        if bounded:
            options = bounded

        # Training-oriented bots visibly seek grass/cave encounter floors instead
        # of wandering only on decorative paths.
        probe = dict(state)
        currently_training = bool(encounter_slots(m, probe)) if self._map_has_training(m) else False
        choice = None
        if self._map_has_training(m) and not currently_training and bot['personality'].get('training', .5) >= .35:
            if not rt['path']:
                rt['path'] = self._path_to_training(m, state, start)
            if rt['path']:
                desired = rt['path'].pop(0)
                choice = next((o for o in options if o[0] == desired[0] and (o[1], o[2]) == (desired[1], desired[2])), None)
                if choice is None:
                    rt['path'] = []
        if choice is None:
            # Prefer staying on encounter terrain when already training.
            weighted = []
            for o in options:
                probe['x'], probe['y'] = o[1], o[2]
                weight = 4 if currently_training and encounter_slots(m, probe) else 1
                if o[0] == rt.get('heading'):
                    weight += 2
                distance = max(abs(o[1] - anchor[0]), abs(o[2] - anchor[1]))
                if distance <= max(2, self.materialized_roam_radius // 2):
                    weight += 2
                elif distance >= self.materialized_roam_radius - 1:
                    weight = max(1, weight - 1)
                weighted.extend([o] * weight)
            choice = self.c.rng.choice(weighted)

        direction, nx, ny = choice
        occupied.discard(start)
        occupied.add((nx, ny))
        rt['fx'], rt['fy'] = state['x'], state['y']
        state['x'], state['y'] = nx, ny
        state['direction'] = direction
        state['revision'] = int(state.get('revision', 0)) + 1
        rt['heading'] = direction
        bot['personality']['fieldHeading'] = direction
        self.dirty.add(bot['id'])
        return True

    async def _flush_world_locked(self, force=False):
        if not self.dirty:
            return 0
        if not force and time.monotonic() - self.last_persist < self.field_persist:
            return 0
        records = [self.by_id[i] for i in sorted(self.dirty) if i in self.by_id]
        if records:
            await asyncio.to_thread(self.db.ai_save_world_states, records)
        self.dirty.difference_update(b['id'] for b in records)
        self.last_persist = time.monotonic()
        return len(records)

    async def flush_world(self):
        async with self.lock:
            return await self._flush_world_locked(force=True)

    # ------------------------------------------------------------------
    # Pokemon development and real autonomous wild battles
    # ------------------------------------------------------------------

    def _team_strength(self, bot):
        party = self._party_members(bot)
        return 1 if not party else (
            sum(m['level'] * 12 + sum(self.c.stats(m)[1:]) / 8 for m in party) / len(party)
            + bot['rating'] * .12)

    def _next(self, bot, now):
        return now + max(30, int(bot['personality'].get('activity', 120)))

    def _optimize_party(self, bot):
        state = bot['state']
        ranked = sorted(state['creatures'], key=lambda m: (m['level'], sum(self.c.stats(m)), m['uid']), reverse=True)
        state['party'] = [m['uid'] for m in ranked[:6]] or state['party']

    def _develop(self, bot, won):
        state = bot['state']
        leveled = []
        for mon in self._party_members(bot):
            gained = self.c.gain_xp(mon, max(8, int((20 if won else 9) * (1 + bot['personality'].get('training', .5)))))
            if gained:
                leveled.append(mon['uid'])
        evolutions = self._apply_level_evolutions(bot, leveled)
        self._optimize_party(bot)
        for mon in state['creatures']:
            if mon['uid'] in state['party']:
                self.c.heal(mon)
        state['revision'] = int(state.get('revision', 0)) + 1
        return evolutions

    def _capture_item(self, items):
        choices = [k for k, spec in self.c.items.items() if 'capture' in spec and items.get(k, 0) > 0]
        return choices[0] if choices else None

    def _healing_item(self, items):
        choices = [k for k, spec in self.c.items.items() if 'heal' in spec and items.get(k, 0) > 0]
        return choices[0] if choices else None

    def _restock_field_supplies(self, state):
        """Bots spend their own field money on basic supplies instead of infinite items."""
        money = int(state.get('money', 0))
        for key, target in (('pokeball', 6), ('potion', 3)):
            if key not in self.c.items:
                continue
            current = int(state.setdefault('items', {}).get(key, 0))
            price = int(self.c.items[key].get('price', 0) or 0)
            if current >= target or price <= 0:
                continue
            buy = min(target - current, money // price)
            if buy > 0:
                state['items'][key] = current + buy
                money -= buy * price
        state['money'] = money

    def _best_attack(self, battle, side=0):
        mon = battle.mon(side)
        enemy = battle.mon(1 - side)
        usable = battle.usable(mon)
        if not usable:
            return -1
        scored = []
        for slot in usable:
            move = self.c.moves[str(mon['moves'][slot]['id'])]
            power = move.get('power', 0) or 0
            mult = matchup(move.get('type', 0), self.c.species[enemy['species']]['types']) if power else .2
            stab = 1.35 if move.get('type') in self.c.species[mon['species']]['types'] else 1.0
            score = max(1, power) * max(.05, mult) * stab + self.c.rng.random() * 12
            scored.append((score, slot))
        return max(scored)[1]

    def _wild_action(self, bot, battle):
        mon = battle.mon(0)
        enemy = battle.mon(1)
        enemy_max = max(1, self.c.stats(enemy)[0])
        own_max = max(1, self.c.stats(mon)[0])
        capture_item = self._capture_item(battle.items[0])
        if (capture_item and len(bot['state']['creatures']) < min(self.s.max_owned, 120)
                and enemy['hp'] / enemy_max <= .48
                and self.c.rng.random() < .30 + bot['personality'].get('capture', .4) * .55):
            return {'action': 'capture', 'item': capture_item}
        heal_item = self._healing_item(battle.items[0])
        if heal_item and mon['hp'] / own_max < .25:
            return {'action': 'item', 'item': heal_item}
        healthy = [m for i, m in enumerate(battle.rosters[0]) if i != battle.active[0] and m['hp'] > 0]
        if mon['hp'] / own_max < .14 and healthy:
            best = max(healthy, key=lambda m: (m['level'], sum(self.c.stats(m))))
            return {'action': 'switch', 'uid': best['uid']}
        return {'action': 'attack', 'slot': self._best_attack(battle, 0)}

    def _simulate_wild_battle(self, bot):
        """Run the same Battle engine used for humans, then apply persistent EXP/catch state."""
        state = bot['state']
        m = self.c.maps.get(state.get('map'))
        if not m:
            return None
        slots = encounter_slots(m, state)
        if not slots:
            return None
        party = self._party_members(bot, clone=True)
        if not party:
            return None
        if not any(mon['hp'] > 0 for mon in party):
            for mon in party:
                self.c.heal(mon)
        key, level = select_encounter(slots, self.c.rng)
        enemy = self.c.new_mon(key, level, variety=self.c.varieties.roll(key))
        self._restock_field_supplies(state)
        battle = Battle(
            self.c, 'wild', [bot['id'], None], [bot['username'], 'Wild ' + self.c.varieties.display_name(enemy)],
            [party, [enemy]], [copy.deepcopy(state.get('items', {})), {}],
            self.s.int('gameplay', 'battle_turn_seconds'), audio_source=m['id'].split('_', 1)[0])
        exp_awards = collections.Counter()
        turns = 0
        while not battle.ended and turns < 64:
            turns += 1
            action = self._wild_action(bot, battle)
            try:
                battle.choose(0, action)
            except RequestError:
                # A planned heal/capture can become invalid after a prior turn;
                # recover with a normal legal attack, but do not hide programmer or
                # data errors behind a blanket exception handler.
                battle.choice.pop(0, None)
                battle.choose(0, {'action': 'attack', 'slot': self._best_attack(battle, 0)})
            battle.resolve()
            for event in battle.experience_events:
                participants = [mon for mon in battle.rosters[0]
                                if mon['uid'] in event['participants'] and mon['hp'] > 0]
                if not participants:
                    continue
                total = max(1, self.c.species[event['species']]['baseExperience'] * event['level'] * 2 // 14)
                exp = max(1, total // len(participants))
                for mon in participants:
                    exp_awards[mon['uid']] += exp
        if not battle.ended:
            battle.ended = True
            battle.winner = None

        by_uid = {mon['uid']: copy.deepcopy(mon) for mon in battle.rosters[0]}
        state['creatures'] = [by_uid.get(mon['uid'], mon) for mon in state['creatures']]
        state['items'] = copy.deepcopy(battle.items[0])
        levels = []
        leveled_uids = []
        for mon in state['creatures']:
            amount = exp_awards.get(mon['uid'], 0)
            if amount:
                before = mon['level']
                gained = self.c.gain_xp(mon, amount)
                if gained:
                    levels.append((self.c.species[mon['species']]['name'], before, mon['level']))
                    leveled_uids.append(mon['uid'])
        evolutions = self._apply_level_evolutions(bot, leveled_uids)

        caught_name = None
        caught_species = None
        if battle.caught is not None and len(state['creatures']) < min(self.s.max_owned, 120):
            caught = copy.deepcopy(battle.caught)
            state['creatures'].append(caught)
            caught_name = self.c.varieties.display_name(caught)
            caught_species = caught['species']
            if len(state['party']) < 6:
                state['party'].append(caught['uid'])
        if battle.ended and battle.winner == 0 and not battle.caught:
            state['money'] = min(2_000_000_000, int(state.get('money', 0)) + 25)
        if battle.winner == 1 or not any(mon['hp'] > 0 for mon in state['creatures'] if mon['uid'] in state['party']):
            # The trainer recovers its party. Regional travel policy decides whether
            # the loss should trigger a retreat to a safer encounter map.
            for mon in state['creatures']:
                if mon['uid'] in state['party']:
                    self.c.heal(mon)
        self._optimize_party(bot)
        self._restock_field_supplies(state)
        self.w.adventure.observe(state, [key], caught=False)
        if caught_species:
            self.w.adventure.observe(state, [caught_species], caught=True)
        self.c.varieties.observe(state, state['creatures'], caught=True)
        state['revision'] = int(state.get('revision', 0)) + 1

        result = 'capture' if caught_name else 'win' if battle.winner == 0 else 'loss' if battle.winner == 1 else 'training'
        if caught_name:
            summary = f'{bot["username"]} captured {caught_name} (Lv. {level}) during wild training on {m["name"]}.'
        elif battle.winner == 0:
            summary = f'{bot["username"]} defeated a wild {self.c.varieties.display_name(enemy)} (Lv. {level}) on {m["name"]}.'
        elif battle.winner == 1:
            summary = f'{bot["username"]} was defeated by a wild {self.c.varieties.display_name(enemy)} (Lv. {level}) and recovered.'
        else:
            summary = f'{bot["username"]} trained against a wild {self.c.varieties.display_name(enemy)} (Lv. {level}) on {m["name"]}.'
        if levels:
            summary += ' ' + ', '.join(f'{name} reached Lv. {after}' for name, _before, after in levels[:2]) + '.'
        if evolutions:
            summary += ' ' + ', '.join(f'{e["sourceName"]} evolved into {e["targetName"]}' for e in evolutions[:2]) + '.'
        outcome = {
            'result': result,
            'summary': summary,
            'species': key,
            'level': level,
            'caught': caught_name,
            'levels': levels,
            'evolutions': evolutions,
            'turns': turns,
        }
        self._record_wild_outcome(bot, outcome)
        return outcome

    async def field_tick(self, active_maps):
        """High-frequency world life only where at least one human can observe it.

        Movement remains high frequency and is persisted by the existing dirty-state
        batch.  Visible travel/wild results are stronger state transitions, but they
        are now accumulated and committed once per world tick instead of opening one
        transaction per bot.  This preserves every event while removing fsync/redo-log
        amplification when several visible trainers act together.
        """
        if not active_maps:
            async with self.lock:
                await self._flush_world_locked(force=False)
            return
        async with self.lock:
            now = time.monotonic()
            for bot_id, expiry in list(self.engaged.items()):
                if expiry <= now:
                    self.engaged.pop(bot_id, None)
            wild_started = 0
            field_records = []
            human_positions = collections.defaultdict(set)
            for p in self.w.players.values():
                if not p.closed:
                    human_positions[p.state['map']].add((p.state['x'], p.state['y']))
            epoch = int(time.time())
            for map_id in sorted(active_maps):
                bots = self._materialized_bots(map_id)
                if not bots:
                    continue
                self._ensure_materialized_spacing(map_id, bots, human_positions.get(map_id, ()))
                occupied = {(b['state']['x'], b['state']['y']) for b in bots}
                occupied.update(human_positions.get(map_id, ()))
                departure_open = now >= self.active_departure_at.get(map_id, 0.0)
                for bot in list(bots):
                    rt = self._runtime_for(bot)
                    if (self.engaged.get(bot['id'], 0) <= now and rt.get('busy_until', 0) <= now):
                        reason = self._travel_reason(bot, epoch)
                        if reason and departure_open:
                            old_position = (bot['state']['x'], bot['state']['y'])
                            travel = self._relocate_bot(bot, reason, epoch)
                            if travel:
                                occupied.discard(old_position)
                                departure_open = False
                                self.active_departure_at[map_id] = now + self.active_departure_seconds
                                bot['next_action_at'] = max(int(bot.get('next_action_at', 0)), epoch + 30)
                                field_records.append({
                                    'bot': bot,
                                    'event': {
                                        'kind': 'travel', 'opponent': 0, 'result': 'relocate',
                                        'summary': travel['summary'],
                                    },
                                    'record_activity': True,
                                })
                                continue
                    moved = self._step_bot(bot, occupied, now)
                    if not moved or wild_started >= self.field_wild_per_tick:
                        continue
                    if now < rt.get('next_wild', 0) or rt.get('busy_until', 0) > now:
                        continue
                    state = bot['state']
                    m = self.c.maps[state['map']]
                    if not encounter_slots(m, state):
                        continue
                    rt['next_wild'] = now + self.field_wild_cooldown + (bot['id'] % 7) * .35
                    if self.c.rng.random() > self.field_wild_chance:
                        continue
                    result = self._simulate_wild_battle(bot)
                    if not result:
                        continue
                    wild_started += 1
                    rt['busy_until'] = now + self.field_battle_seconds
                    rt['field_action'] = 'wild_battle'
                    rt['wild_species'] = result['species']
                    bot['next_action_at'] = self._next(bot, epoch)
                    field_records.append({
                        'bot': bot,
                        'event': {
                            'kind': 'wild', 'opponent': 0, 'result': result['result'],
                            'summary': result['summary'],
                        },
                        'record_activity': True,
                    })

            if field_records:
                try:
                    committed_at = await asyncio.to_thread(self.db.ai_commit_fields, field_records)
                except Exception:
                    await self._rollback_bots_from_store_locked(
                        record['bot']['id'] for record in field_records)
                    raise
                for record in field_records:
                    bot = record['bot']
                    bot['last_action_at'] = committed_at
                    self.dirty.discard(bot['id'])
            await self._flush_world_locked(force=False)

    # ------------------------------------------------------------------
    # Elapsed-time competitive/offline simulation
    # ------------------------------------------------------------------

    def _place_on_training_tile(self, bot):
        state = bot['state']
        m = self.c.maps.get(state.get('map'))
        if not m or not self._map_has_training(m):
            return False
        if encounter_slots(m, state):
            return True
        points = self._training_points(m)
        if not points:
            return False
        x, y = min(points, key=lambda p: (abs(p[0] - state['x']) + abs(p[1] - state['y']), p[1], p[0]))
        state['x'], state['y'] = x, y
        state['direction'] = 'down'
        state['revision'] = int(state.get('revision', 0)) + 1
        return bool(encounter_slots(m, state))

    async def _simulate_due_locked(self):
        """Run one bounded competitive pass from the authoritative memory image.

        Earlier builds queried full ``state_json``/``personality_json`` rows for
        the due cohort, re-read every actor, fetched up to 24 full candidate rows
        per actor, committed each pairing separately, and finally re-read all
        2,000 trainers.  As bot collections grew that multiplied MySQL I/O every
        eight seconds.  The world lease makes the in-memory population authoritative,
        so matchmaking can be computed here and committed once at the end.
        """
        await self._flush_world_locked(force=True)
        now = int(time.time())
        due_ids = [bot['id'] for bot in sorted(
            (bot for bot in self.snapshot if int(bot.get('next_action_at', 0)) <= now),
            key=lambda bot: (int(bot.get('next_action_at', 0)), bot['id']))[:self.batch]]
        if not due_ids:
            return

        recent_by_id = await asyncio.to_thread(
            self.db.ai_recent_opponents_many, due_ids, now - 21600, 8)
        working = {}
        changed_ids = set()
        events = []

        def work(ai_id):
            ai_id = int(ai_id)
            if ai_id not in working:
                live = self.by_id.get(ai_id)
                if live is None:
                    return None
                working[ai_id] = copy.deepcopy(live)
            return working[ai_id]

        def effective(bot):
            return working.get(bot['id'], bot)

        for ai_id in due_ids:
            if self.engaged.get(ai_id, 0) > time.monotonic():
                continue
            a = work(ai_id)
            if not a or a['next_action_at'] > now:
                continue

            recent = set(recent_by_id.get(a['id'], ()))
            low, high = max(0, int(a['rating']) - 350), int(a['rating']) + 350
            candidates = []
            for live in self.snapshot:
                candidate = effective(live)
                if candidate['id'] == a['id'] or not low <= int(candidate['rating']) <= high:
                    continue
                candidates.append(candidate)
            # Preserve the historical query semantics exactly: choose the 24
            # rating-nearest rows first, then exclude currently engaged bots.
            candidates.sort(key=lambda bot: (abs(int(bot['rating']) - int(a['rating'])), bot['id']))
            candidates = candidates[:24]
            candidates = [bot for bot in candidates
                          if self.engaged.get(bot['id'], 0) <= time.monotonic()]
            filtered = [bot for bot in candidates if bot['id'] not in recent]
            if filtered:
                candidates = filtered
            if not candidates:
                a['next_action_at'] = self._next(a, now)
                changed_ids.add(a['id'])
                continue

            chosen = min(candidates, key=lambda bot: (
                abs(bot['rating'] - a['rating']) + self.c.rng.randrange(75), bot['id']))
            b = work(chosen['id'])
            if b is None:
                a['next_action_at'] = self._next(a, now)
                changed_ids.add(a['id'])
                continue

            sa, sb = self._team_strength(a), self._team_strength(b)
            pa = 1 / (1 + math.exp(max(-8, min(8, (sb - sa) / 110))))
            a_won = self.c.rng.random() < pa
            before_a, before_b = a['rating'], b['rating']
            a['rating'] = elo(before_a, before_b, 1 if a_won else 0)
            b['rating'] = elo(before_b, before_a, 0 if a_won else 1)
            a['wins'] += int(a_won)
            a['losses'] += int(not a_won)
            b['wins'] += int(not a_won)
            b['losses'] += int(a_won)
            a['tier'] = tier_for(a['rating'])
            b['tier'] = tier_for(b['rating'])
            evolutions_a = self._develop(a, a_won)
            evolutions_b = self._develop(b, not a_won)
            a['next_action_at'] = self._next(a, now)
            b['next_action_at'] = self._next(b, now) + self.c.rng.randrange(30)
            winner = a if a_won else b
            loser = b if a_won else a
            summary = f'{winner["username"]} defeated {loser["username"]} in autonomous ranked play.'
            ranked_evolutions = evolutions_a + evolutions_b
            if ranked_evolutions:
                summary += ' ' + ', '.join(
                    f'{event["sourceName"]} evolved into {event["targetName"]}'
                    for event in ranked_evolutions[:2]) + '.'
            events.extend((
                {'actor': a['id'], 'kind': 'ai', 'opponent': b['id'],
                 'result': 'win' if a_won else 'loss', 'summary': summary,
                 'before': before_a, 'after': a['rating']},
                {'actor': b['id'], 'kind': 'ai', 'opponent': a['id'],
                 'result': 'loss' if a_won else 'win', 'summary': summary,
                 'before': before_b, 'after': b['rating']},
            ))
            recent_by_id.setdefault(a['id'], []).append(b['id'])
            recent_by_id.setdefault(b['id'], []).append(a['id'])
            changed_ids.update((a['id'], b['id']))

        if not changed_ids:
            return
        records = [working[ai_id] for ai_id in sorted(changed_ids)]
        committed_at = await asyncio.to_thread(self.db.ai_commit_competitive_batch, records, events)
        for bot in records:
            bot['last_action_at'] = committed_at
            self._adopt_bot_locked(bot)

    async def simulate_due(self):
        async with self.lock:
            await self._simulate_due_locked()

    async def maybe_tick(self):
        if time.monotonic() - self.last_simulation < self.interval:
            return
        async with self.lock:
            if time.monotonic() - self.last_simulation < self.interval:
                return
            self.last_simulation = time.monotonic()
            await self._simulate_due_locked()

    # ------------------------------------------------------------------
    # Human-facing ranked services
    # ------------------------------------------------------------------

    async def dashboard(self, p):
        p.send('ai.dashboard', dashboard=await asyncio.to_thread(self.db.ai_dashboard, p.id))

    async def challenge(self, p, raw_id):
        self.w.free(p)
        require(any(m['hp'] > 0 for m in self.w.party(p)), 'Your party needs healing.')
        ai_id = integer(raw_id, 1, self.population, 'Autonomous trainer ID')
        engaged = False
        try:
            async with self.lock:
                # The lease-protected snapshot is the authoritative trainer image.
                # Flush pending position state before engaging the bot, then clone
                # directly from memory instead of re-reading a growing JSON row.
                await self._flush_world_locked(force=True)
                bot = self.by_id.get(ai_id)
                require(bot is not None, 'That autonomous trainer is unavailable.')
                roster = self._party_members(bot, clone=True)
                require(bool(roster), 'That autonomous trainer has no valid party.')
                bot_name = bot['username']
                self.engaged[ai_id] = time.monotonic() + max(180, self.s.int('gameplay', 'battle_turn_seconds') * 20)
                engaged = True
            for m in roster:
                self.c.heal(m)
            b = Battle(
                self.c, 'duel', [p.id, None], [p.username, bot_name], [self.w.party(p), roster], [{}, {}],
                self.s.int('gameplay', 'battle_turn_seconds'), audio_source=p.state['map'].split('_', 1)[0])
            b.ai_trainer_id = ai_id
            self.w.battles[b.id] = b
            p.battle = b.id
            p.send('battle', battle=b.view(0))
        except Exception:
            if engaged:
                self.engaged.pop(ai_id, None)
            raise

    def release_engagement(self, ai_id):
        """Release a materialized bot after an abandoned/invalid human challenge."""
        if ai_id:
            self.engaged.pop(int(ai_id), None)

    async def finish_human_battle(self, b):
        ai_id = getattr(b, 'ai_trainer_id', None)
        if not ai_id or not b.ended:
            return
        if b.winner is None:
            self.release_engagement(ai_id)
            return
        p = self.w.players.get(b.players[0])
        if not p:
            self.engaged.pop(b.ai_trainer_id, None)
            return
        async with self.lock:
            await self._flush_world_locked(force=True)
            live = self.by_id.get(int(b.ai_trainer_id))
            if not live:
                self.engaged.pop(b.ai_trainer_id, None)
                return

            # Develop a detached copy first.  Nothing in the live snapshot changes
            # unless the joint human+AI transaction commits successfully.
            bot = copy.deepcopy(live)
            human = await asyncio.to_thread(self.db.competitive_profile, p.id)
            human_before = human['rating']
            ai_before = bot['rating']
            human_won = b.winner == 0
            human_after = elo(human_before, ai_before, 1 if human_won else 0, 32)
            ai_after = elo(ai_before, human_before, 0 if human_won else 1, 32)
            evolutions = self._develop(bot, not human_won)
            summary = f'{p.username} ' + ('defeated' if human_won else 'lost to') + f' {bot["username"]} in ranked play.'
            if evolutions:
                summary += ' ' + ', '.join(f'{e["sourceName"]} evolved into {e["targetName"]}' for e in evolutions[:2]) + '.'
            committed_at = await asyncio.to_thread(
                self.db.ai_ranked_human_result, p.id, bot['id'], human_won, human_after, tier_for(human_after),
                ai_before, ai_after, tier_for(ai_after), bot['state'], summary)

            bot['rating'] = ai_after
            bot['tier'] = tier_for(ai_after)
            bot['wins'] += int(not human_won)
            bot['losses'] += int(human_won)
            bot['next_action_at'] = committed_at + 120
            bot['last_action_at'] = committed_at
            self._adopt_bot_locked(bot)
            self.engaged.pop(bot['id'], None)
            b.logs.append(f'Ranked rating: {human_before} → {human_after}.')
            p.send('notice', message=f'Ranked result saved. Rating {human_before} → {human_after}.')
