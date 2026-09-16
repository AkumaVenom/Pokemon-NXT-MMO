"""Persistent autonomous trainer ladder storage.

The autonomous population is intentionally write-heavy.  Keep all persistence
transactional, but batch independent bot updates so MySQL performs one commit
and one lease fence per scheduler pass instead of one fsync-sized transaction
per trainer.
"""
from __future__ import annotations

import json
import time


class AIStoreMixin:
    ACTIVITY_RETENTION_SECONDS = 3_888_000  # 45 days
    ACTIVITY_PRUNE_INTERVAL_SECONDS = 3600

    def migrate_ai(self, c, suffix, large, identity):
        c.execute(
            f"CREATE TABLE IF NOT EXISTS ai_trainers (id BIGINT PRIMARY KEY, username VARCHAR(20) NOT NULL UNIQUE, "
            f"rating INTEGER NOT NULL, wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, "
            f"tier VARCHAR(16) NOT NULL, state_json {large} NOT NULL, personality_json {large} NOT NULL, "
            f"next_action_at BIGINT NOT NULL, last_action_at BIGINT NOT NULL DEFAULT 0, created_at BIGINT NOT NULL, "
            f"updated_at BIGINT NOT NULL)" + suffix)
        c.execute(
            "CREATE TABLE IF NOT EXISTS competitive_profiles (account_id BIGINT PRIMARY KEY, rating INTEGER NOT NULL "
            "DEFAULT 1000, wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, tier VARCHAR(16) NOT "
            "NULL DEFAULT 'Bronze', updated_at BIGINT NOT NULL, FOREIGN KEY (account_id) REFERENCES accounts(id))" + suffix)
        c.execute(
            f"CREATE TABLE IF NOT EXISTS ai_activity (id {identity}, actor_ai_id BIGINT NOT NULL, opponent_kind "
            "VARCHAR(8) NOT NULL, opponent_id BIGINT NOT NULL, result VARCHAR(16) NOT NULL, summary VARCHAR(255) NOT "
            "NULL, rating_before INTEGER NOT NULL, rating_after INTEGER NOT NULL, created_at BIGINT NOT NULL)" + suffix)
        c.execute(
            "CREATE TABLE IF NOT EXISTS ai_rivals (account_id BIGINT NOT NULL, ai_id BIGINT NOT NULL, battles INTEGER "
            "NOT NULL DEFAULT 0, human_wins INTEGER NOT NULL DEFAULT 0, ai_wins INTEGER NOT NULL DEFAULT 0, rivalry "
            "INTEGER NOT NULL DEFAULT 0, last_battle_at BIGINT NOT NULL, PRIMARY KEY(account_id,ai_id), FOREIGN KEY "
            "(account_id) REFERENCES accounts(id))" + suffix)
        for stmt in (
            'CREATE INDEX idx_ai_trainers_rating ON ai_trainers(rating)',
            'CREATE INDEX idx_ai_trainers_due ON ai_trainers(next_action_at)',
            'CREATE INDEX idx_ai_activity_time ON ai_activity(created_at)',
            'CREATE INDEX idx_ai_activity_actor ON ai_activity(actor_ai_id,created_at)',
            'CREATE INDEX idx_ai_activity_actor_kind_time ON ai_activity(actor_ai_id,opponent_kind,created_at)',
            'CREATE INDEX idx_ai_rivals_account ON ai_rivals(account_id,rivalry)',
        ):
            try:
                c.execute(stmt)
            except Exception:
                # MySQL and SQLite both report an error when an index already
                # exists.  Existing deployments must remain upgrade-safe.
                pass

    @staticmethod
    def _dump(value):
        return json.dumps(value, separators=(',', ':'))

    def _bot(self, row):
        return {
            'id': int(row[0]), 'username': row[1], 'rating': int(row[2]),
            'wins': int(row[3]), 'losses': int(row[4]), 'tier': row[5],
            'state': json.loads(row[6]), 'personality': json.loads(row[7]),
            'next_action_at': int(row[8]), 'last_action_at': int(row[9]),
        }

    def _prune_ai_activity(self, c, now):
        """Bound the feed without repeating a DELETE for every bot action.

        A one-hour pruning cadence still enforces the 45-day retention contract,
        while avoiding needless index churn on the high-frequency field path.
        The timestamp is published only after the surrounding transaction commits.
        """
        last = int(getattr(self, '_last_ai_activity_prune', 0) or 0)
        if now - last < self.ACTIVITY_PRUNE_INTERVAL_SECONDS:
            return False
        c.execute(self.sql('DELETE FROM ai_activity WHERE created_at<%s'),
                  (now - self.ACTIVITY_RETENTION_SECONDS,))
        return True

    def ai_count(self):
        with self.transaction() as c:
            c.execute('SELECT COUNT(*) FROM ai_trainers')
            return int(c.fetchone()[0])

    def ai_ids(self):
        with self.transaction() as c:
            c.execute('SELECT id FROM ai_trainers ORDER BY id')
            return [int(row[0]) for row in c.fetchall()]

    def ai_seed(self, records):
        if not records:
            return
        now = int(time.time())
        sql = self.sql(
            'INSERT INTO ai_trainers(id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,'
            'last_action_at,created_at,updated_at) VALUES(%s,%s,%s,0,0,%s,%s,%s,%s,0,%s,%s)')
        params = [
            (record['id'], record['username'], record['rating'], record['tier'],
             self._dump(record['state']), self._dump(record['personality']),
             record['next_action_at'], now, now)
            for record in records
        ]
        with self.transaction() as c:
            self.fence(c)
            c.executemany(sql, params)

    def ai_get(self, ai_id):
        with self.transaction() as c:
            c.execute(self.sql(
                'SELECT id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at '
                'FROM ai_trainers WHERE id=%s'), (ai_id,))
            row = c.fetchone()
        return self._bot(row) if row else None

    # Retained as compatibility/debugging APIs.  The live scheduler no longer
    # depends on repeated full-JSON reads for due/candidate selection.
    def ai_due(self, now, limit):
        with self.transaction() as c:
            c.execute(self.sql(
                'SELECT id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at '
                'FROM ai_trainers WHERE next_action_at<=%s ORDER BY next_action_at,id LIMIT %s'),
                (int(now), int(limit)))
            rows = c.fetchall()
        return [self._bot(row) for row in rows]

    def ai_candidates(self, ai_id, rating, limit=24):
        with self.transaction() as c:
            c.execute(self.sql(
                'SELECT id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at '
                'FROM ai_trainers WHERE id<>%s AND rating BETWEEN %s AND %s ORDER BY ABS(rating-%s),id LIMIT %s'),
                (ai_id, max(0, int(rating) - 350), int(rating) + 350, int(rating), int(limit)))
            rows = c.fetchall()
        return [self._bot(row) for row in rows]

    def ai_recent_opponents(self, ai_id, since, limit=12):
        with self.transaction() as c:
            c.execute(self.sql(
                "SELECT opponent_id FROM ai_activity WHERE actor_ai_id=%s AND opponent_kind='ai' AND created_at>=%s "
                'ORDER BY created_at DESC,id DESC LIMIT %s'),
                (ai_id, int(since), int(limit)))
            return [int(row[0]) for row in c.fetchall()]

    def ai_recent_opponents_many(self, ai_ids, since, limit=8):
        """Read recent ranked opponents for a due cohort in one transaction."""
        ids = sorted({int(ai_id) for ai_id in ai_ids})
        result = {ai_id: [] for ai_id in ids}
        if not ids:
            return result
        placeholders = ','.join('%s' for _ in ids)
        sql = self.sql(
            f"SELECT actor_ai_id,opponent_id FROM ai_activity WHERE actor_ai_id IN ({placeholders}) "
            "AND opponent_kind='ai' AND created_at>=%s ORDER BY actor_ai_id,created_at DESC,id DESC")
        with self.transaction() as c:
            c.execute(sql, (*ids, int(since)))
            for actor, opponent in c.fetchall():
                actor = int(actor)
                if len(result[actor]) < int(limit):
                    result[actor].append(int(opponent))
        return result

    def ai_commit_competitive_batch(self, records, events):
        """Commit a complete competitive scheduler pass in one transaction."""
        if not records and not events:
            return int(time.time())
        now = int(time.time())
        # A trainer can appear as an opponent and later as a due actor in the same
        # pass.  Persist only its final authoritative state.
        unique = {int(bot['id']): bot for bot in records}
        update_sql = self.sql(
            'UPDATE ai_trainers SET rating=%s,wins=%s,losses=%s,tier=%s,state_json=%s,next_action_at=%s,'
            'last_action_at=%s,updated_at=%s WHERE id=%s')
        update_params = [
            (bot['rating'], bot['wins'], bot['losses'], bot['tier'], self._dump(bot['state']),
             bot['next_action_at'], now, now, bot['id'])
            for bot in unique.values()
        ]
        insert_sql = self.sql(
            'INSERT INTO ai_activity(actor_ai_id,opponent_kind,opponent_id,result,summary,rating_before,rating_after,'
            'created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)')
        insert_params = [
            (event['actor'], event['kind'], event['opponent'], event['result'], event['summary'][:255],
             event['before'], event['after'], now)
            for event in events
        ]
        pruned = False
        with self.transaction() as c:
            self.fence(c)
            if update_params:
                c.executemany(update_sql, update_params)
            if insert_params:
                c.executemany(insert_sql, insert_params)
            if insert_params:
                pruned = self._prune_ai_activity(c, now)
        if pruned:
            self._last_ai_activity_prune = now
        return now

    def ai_commit_pair(self, a, b, event_a, event_b):
        return self.ai_commit_competitive_batch((a, b), (event_a, event_b))

    def ai_save_single(self, bot):
        now = int(time.time())
        with self.transaction() as c:
            self.fence(c)
            c.execute(self.sql(
                'UPDATE ai_trainers SET state_json=%s,next_action_at=%s,last_action_at=%s,updated_at=%s WHERE id=%s'),
                (self._dump(bot['state']), bot['next_action_at'], now, now, bot['id']))
        return now

    def ai_rebalance_world(self, records):
        if not records:
            return
        now = int(time.time())
        sql = self.sql('UPDATE ai_trainers SET state_json=%s,personality_json=%s,updated_at=%s WHERE id=%s')
        params = [(self._dump(bot['state']), self._dump(bot['personality']), now, bot['id']) for bot in records]
        with self.transaction() as c:
            self.fence(c)
            c.executemany(sql, params)

    def ai_save_world_states(self, records):
        if not records:
            return
        now = int(time.time())
        sql = self.sql('UPDATE ai_trainers SET state_json=%s,updated_at=%s WHERE id=%s')
        params = [(self._dump(bot['state']), now, bot['id']) for bot in records]
        with self.transaction() as c:
            self.fence(c)
            c.executemany(sql, params)

    def ai_commit_fields(self, records):
        """Commit field outcomes for many bots with one lease fence/commit.

        Each record is ``{'bot': bot, 'event': event, 'record_activity': bool}``.
        State/personality/field clock persistence is never sampled; only the
        public activity-feed row may be sampled by the caller.
        """
        if not records:
            return int(time.time())
        now = int(time.time())
        unique = {int(record['bot']['id']): record for record in records}
        update_sql = self.sql(
            'UPDATE ai_trainers SET state_json=%s,personality_json=%s,next_action_at=%s,last_action_at=%s,'
            'updated_at=%s WHERE id=%s')
        update_params = []
        insert_params = []
        for record in unique.values():
            bot = record['bot']
            update_params.append((self._dump(bot['state']), self._dump(bot['personality']),
                                  bot['next_action_at'], now, now, bot['id']))
            if record.get('record_activity', True):
                event = record.get('event') or {}
                insert_params.append((
                    bot['id'], event.get('kind', 'wild'), int(event.get('opponent', 0)),
                    event.get('result', 'training')[:16],
                    event.get('summary', 'Autonomous field training.')[:255],
                    bot['rating'], bot['rating'], now))
        insert_sql = self.sql(
            'INSERT INTO ai_activity(actor_ai_id,opponent_kind,opponent_id,result,summary,rating_before,rating_after,'
            'created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)')
        pruned = False
        with self.transaction() as c:
            self.fence(c)
            c.executemany(update_sql, update_params)
            if insert_params:
                c.executemany(insert_sql, insert_params)
                pruned = self._prune_ai_activity(c, now)
        if pruned:
            self._last_ai_activity_prune = now
        return now

    def ai_commit_field(self, bot, event, record_activity=True):
        return self.ai_commit_fields(({
            'bot': bot, 'event': event, 'record_activity': bool(record_activity),
        },))

    def competitive_profile(self, account_id):
        now = int(time.time())
        with self.transaction() as c:
            c.execute(self.sql('SELECT rating,wins,losses,tier FROM competitive_profiles WHERE account_id=%s'),
                      (account_id,))
            row = c.fetchone()
            if row:
                return {'rating': int(row[0]), 'wins': int(row[1]), 'losses': int(row[2]), 'tier': row[3]}
            self.fence(c)
            c.execute(self.sql(
                "INSERT INTO competitive_profiles(account_id,rating,wins,losses,tier,updated_at) "
                "VALUES(%s,1000,0,0,'Bronze',%s)"), (account_id, now))
            return {'rating': 1000, 'wins': 0, 'losses': 0, 'tier': 'Bronze'}

    def ai_ranked_human_result(self, account_id, ai_id, human_won, human_after, human_tier,
                               ai_before, ai_after, ai_tier, ai_state, summary):
        now = int(time.time())
        pruned = False
        with self.transaction() as c:
            self.fence(c)
            if self.mysql:
                c.execute(self.sql(
                    'INSERT INTO competitive_profiles(account_id,rating,wins,losses,tier,updated_at) '
                    'VALUES(%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE rating=VALUES(rating),'
                    'wins=wins+VALUES(wins),losses=losses+VALUES(losses),tier=VALUES(tier),updated_at=VALUES(updated_at)'),
                    (account_id, human_after, 1 if human_won else 0, 0 if human_won else 1, human_tier, now))
            else:
                c.execute(self.sql(
                    'INSERT INTO competitive_profiles(account_id,rating,wins,losses,tier,updated_at) '
                    'VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(account_id) DO UPDATE SET rating=excluded.rating,'
                    'wins=competitive_profiles.wins+excluded.wins,losses=competitive_profiles.losses+excluded.losses,'
                    'tier=excluded.tier,updated_at=excluded.updated_at'),
                    (account_id, human_after, 1 if human_won else 0, 0 if human_won else 1, human_tier, now))
            c.execute(self.sql(
                'UPDATE ai_trainers SET rating=%s,wins=wins+%s,losses=losses+%s,tier=%s,state_json=%s,'
                'last_action_at=%s,next_action_at=%s,updated_at=%s WHERE id=%s'),
                (ai_after, 0 if human_won else 1, 1 if human_won else 0, ai_tier,
                 self._dump(ai_state), now, now + 120, now, ai_id))
            c.execute(self.sql(
                "INSERT INTO ai_activity(actor_ai_id,opponent_kind,opponent_id,result,summary,rating_before,"
                "rating_after,created_at) VALUES(%s,'human',%s,%s,%s,%s,%s,%s)"),
                (ai_id, account_id, 'loss' if human_won else 'win', summary[:255], ai_before, ai_after, now))
            if self.mysql:
                c.execute(self.sql(
                    'INSERT INTO ai_rivals(account_id,ai_id,battles,human_wins,ai_wins,rivalry,last_battle_at) '
                    'VALUES(%s,%s,1,%s,%s,1,%s) ON DUPLICATE KEY UPDATE battles=battles+1,'
                    'human_wins=human_wins+VALUES(human_wins),ai_wins=ai_wins+VALUES(ai_wins),'
                    'rivalry=rivalry+1,last_battle_at=VALUES(last_battle_at)'),
                    (account_id, ai_id, 1 if human_won else 0, 0 if human_won else 1, now))
            else:
                c.execute(self.sql(
                    'INSERT INTO ai_rivals(account_id,ai_id,battles,human_wins,ai_wins,rivalry,last_battle_at) '
                    'VALUES(%s,%s,1,%s,%s,1,%s) ON CONFLICT(account_id,ai_id) DO UPDATE SET '
                    'battles=ai_rivals.battles+1,human_wins=ai_rivals.human_wins+excluded.human_wins,'
                    'ai_wins=ai_rivals.ai_wins+excluded.ai_wins,rivalry=ai_rivals.rivalry+1,'
                    'last_battle_at=excluded.last_battle_at'),
                    (account_id, ai_id, 1 if human_won else 0, 0 if human_won else 1, now))
            pruned = self._prune_ai_activity(c, now)
        if pruned:
            self._last_ai_activity_prune = now
        return now

    def ai_dashboard(self, account_id, activity_limit=60, ladder_limit=100, rival_limit=20):
        profile = self.competitive_profile(account_id)
        with self.transaction() as c:
            c.execute(self.sql(
                'SELECT id,username,rating,wins,losses,tier,state_json,last_action_at FROM ai_trainers '
                'ORDER BY rating DESC,wins DESC,id LIMIT %s'), (ladder_limit,))
            ai_ladder = c.fetchall()
            c.execute(self.sql(
                'SELECT a.id,a.username,p.rating,p.wins,p.losses,p.tier,p.updated_at FROM competitive_profiles p '
                'JOIN accounts a ON a.id=p.account_id ORDER BY p.rating DESC,p.wins DESC,a.id LIMIT %s'),
                (ladder_limit,))
            human_ladder = c.fetchall()
            c.execute(self.sql(
                'SELECT a.id,a.username,a.rating,a.wins,a.losses,a.tier,r.battles,r.human_wins,r.ai_wins,r.rivalry,'
                'r.last_battle_at,a.state_json FROM ai_rivals r JOIN ai_trainers a ON a.id=r.ai_id '
                'WHERE r.account_id=%s ORDER BY r.rivalry DESC,a.rating DESC LIMIT %s'),
                (account_id, rival_limit))
            rivals = c.fetchall()
            c.execute(self.sql(
                'SELECT x.id,x.actor_ai_id,a.username,x.opponent_kind,x.opponent_id,x.result,x.summary,'
                'x.rating_before,x.rating_after,x.created_at FROM ai_activity x JOIN ai_trainers a '
                'ON a.id=x.actor_ai_id ORDER BY x.created_at DESC,x.id DESC LIMIT %s'), (activity_limit,))
            activity = c.fetchall()
            c.execute('SELECT COUNT(*),AVG(rating),MAX(rating),SUM(wins),SUM(losses) FROM ai_trainers')
            stats = c.fetchone()
            c.execute(self.sql('SELECT COUNT(*) FROM ai_trainers WHERE rating>%s'), (profile['rating'],))
            above_ai = int(c.fetchone()[0])
            c.execute(self.sql(
                'SELECT COUNT(*) FROM competitive_profiles WHERE account_id<>%s AND rating>%s'),
                (account_id, profile['rating']))
            above_human = int(c.fetchone()[0])
            human_rank = above_ai + above_human + 1

        def state_summary(raw):
            state = json.loads(raw)
            lead = next((mon for mon in state.get('creatures', [])
                         if state.get('party') and mon['uid'] == state['party'][0]), None)
            return {
                'map': state.get('map'), 'collection': len(state.get('creatures', [])),
                'partySize': len(state.get('party', [])),
                'leadSpecies': lead['species'] if lead else None,
                'leadLevel': lead['level'] if lead else 0,
            }

        ladder = []
        for row in ai_ladder:
            ladder.append({
                'id': int(row[0]), 'username': row[1], 'rating': int(row[2]),
                'wins': int(row[3]), 'losses': int(row[4]), 'tier': row[5],
                **state_summary(row[6]), 'lastAction': int(row[7]), 'autonomous': True,
            })
        for row in human_ladder:
            ladder.append({
                'id': int(row[0]), 'username': row[1], 'rating': int(row[2]),
                'wins': int(row[3]), 'losses': int(row[4]), 'tier': row[5],
                'map': None, 'collection': None, 'partySize': None,
                'leadSpecies': None, 'leadLevel': 0, 'lastAction': int(row[6]), 'autonomous': False,
            })
        ladder.sort(key=lambda item: (-item['rating'], -item['wins'], item['username'].lower(), item['id']))
        ladder = ladder[:int(ladder_limit)]
        return {
            'population': int(stats[0] or 0), 'averageRating': round(float(stats[1] or 0), 1),
            'topRating': int(stats[2] or 0), 'totalWins': int(stats[3] or 0),
            'totalLosses': int(stats[4] or 0), 'human': {**profile, 'rank': human_rank},
            'ladder': ladder,
            'rivals': [{
                'id': int(row[0]), 'username': row[1], 'rating': int(row[2]),
                'wins': int(row[3]), 'losses': int(row[4]), 'tier': row[5],
                'battles': int(row[6]), 'humanWins': int(row[7]), 'aiWins': int(row[8]),
                'rivalry': int(row[9]), 'lastBattle': int(row[10]), **state_summary(row[11]),
            } for row in rivals],
            'activity': [{
                'id': int(row[0]), 'actorId': int(row[1]), 'actor': row[2],
                'opponentKind': row[3], 'opponentId': int(row[4]), 'result': row[5],
                'summary': row[6], 'before': int(row[7]), 'after': int(row[8]), 'time': int(row[9]),
            } for row in activity],
        }

    def ai_world_snapshot(self):
        with self.transaction() as c:
            c.execute(
                'SELECT id,username,rating,wins,losses,tier,state_json,personality_json,next_action_at,last_action_at '
                'FROM ai_trainers ORDER BY id')
            rows = c.fetchall()
        return [self._bot(row) for row in rows]
