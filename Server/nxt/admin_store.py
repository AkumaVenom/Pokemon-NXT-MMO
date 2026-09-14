"""Private console persistence. No method in this module is a network endpoint.

Account controls and the successful administrative audit are committed in the
same transaction as affected characters. All writes retain world-lease fencing.
No passwords, full character snapshots or connection secrets enter the audit.
"""
from __future__ import annotations

import hmac
import json
import sqlite3
import time
from .security import RequestError, require

CONTROL_FIELDS = ('ban_until', 'locked', 'frozen', 'trade_blocked')


class AdminStoreMixin:
    def migrate_admin(self, cursor, suffix, large):
        cursor.execute('CREATE TABLE IF NOT EXISTS account_controls ('
                       'account_id BIGINT PRIMARY KEY, ban_until BIGINT NOT NULL DEFAULT 0, '
                       'locked INTEGER NOT NULL DEFAULT 0, frozen INTEGER NOT NULL DEFAULT 0, '
                       'trade_blocked INTEGER NOT NULL DEFAULT 0, epoch BIGINT NOT NULL DEFAULT 0, '
                       'FOREIGN KEY (account_id) REFERENCES accounts(id))' + suffix)
        identity = 'BIGINT PRIMARY KEY AUTO_INCREMENT' if self.mysql else 'INTEGER PRIMARY KEY AUTOINCREMENT'
        cursor.execute(f'CREATE TABLE IF NOT EXISTS admin_audit ('
                       f'entry_id {identity}, audit_id VARCHAR(36) NOT NULL UNIQUE, actor VARCHAR(160) NOT NULL, '
                       f'command VARCHAR(40) NOT NULL, payload {large} NOT NULL, '
                       f'created_at BIGINT NOT NULL)' + suffix)
        cursor.execute('CREATE TABLE IF NOT EXISTS admin_audit_targets ('
                       'account_id BIGINT NOT NULL, audit_id VARCHAR(36) NOT NULL, '
                       'PRIMARY KEY (account_id, audit_id), '
                       'FOREIGN KEY (audit_id) REFERENCES admin_audit(audit_id))' + suffix)

    def _admin_account(self, cursor, *, uid=None, login=None):
        field, value = ('a.id', uid) if uid is not None else ('a.login_key', login.lower())
        cursor.execute(self.sql(
            'SELECT a.id,a.username,a.banned,a.created_at,'
            'COALESCE(c.ban_until,0),COALESCE(c.locked,0),COALESCE(c.frozen,0),'
            'COALESCE(c.trade_blocked,0),COALESCE(c.epoch,0) '
            'FROM accounts a LEFT JOIN account_controls c ON c.account_id=a.id '
            f'WHERE {field}=%s'), (value,))
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip(('id', 'username', 'banned_raw', 'created_at',
                         *CONTROL_FIELDS, 'epoch'), row))

    def admin_account(self, *, uid=None, login=None):
        """Exact stable ID or login-key lookup; deliberately omits password hashes."""
        with self.transaction() as cursor:
            return self._admin_account(cursor, uid=uid, login=login)

    def auth_guard(self, uid, expected_hash):
        """Recheck admission AFTER authentication, under the world's join lock.

        A ban/lock/password reset racing the expensive password check must win
        before a new player is published. Plaintext passwords are never accepted.
        """
        with self.transaction() as cursor:
            account = self._admin_account(cursor, uid=uid)
            require(account is not None, 'Username or password is incorrect.')
            cursor.execute(self.sql('SELECT password_hash FROM accounts WHERE id=%s'), (uid,))
            row = cursor.fetchone()
            require(row is not None and isinstance(expected_hash, str)
                    and hmac.compare_digest(str(row[0]), expected_hash),
                    'Account credentials changed during login. Sign in again.')
            banned = bool(account['banned_raw']) and (
                account['ban_until'] == 0 or account['ban_until'] > int(time.time()))
            require(not banned, 'This account is banned. Contact the server administrator.')
            require(not account['locked'], 'This account is locked. Contact the server administrator.')
            return account

    def _admin_audit(self, cursor, event):
        """Must be called inside the same transaction as a successful action."""
        cursor.execute(self.sql('INSERT INTO admin_audit '
            '(audit_id,actor,command,payload,created_at) VALUES(%s,%s,%s,%s,%s)'),
            (event['id'], event['actor'], event['command'],
             json.dumps(event, ensure_ascii=True, separators=(',', ':'), allow_nan=False),
             int(time.time())))
        for uid in sorted(set(event.get('targets', []))):
            cursor.execute(self.sql('INSERT INTO admin_audit_targets '
                '(account_id,audit_id) VALUES(%s,%s)'), (uid, event['id']))

    def admin_commit(self, event, *, records=(), controls=(), passwords=(),
                     expected_epochs=(), create=None):
        """Atomically apply a prepared console action and its durable audit.

        records: (account ID, source live revision, detached NEW state).
        controls: (account ID, changed fields), including optional banned_raw.
        passwords: (account ID, a precomputed scrypt hash); never audited.
        A newer DB revision rejects the ENTIRE batch, including the audit row.
        """
        created_id = None
        try:
            with self.transaction() as cursor:
                require(self.lease_active, 'World database ownership is not active.')
                self.fence(cursor)
                for uid, epoch in expected_epochs:
                    account = self._admin_account(cursor, uid=uid)
                    require(account is not None and account['epoch'] == epoch,
                            'Account controls changed. Run the command again.')
                for uid, source_revision, state in records:
                    cursor.execute(self.sql('SELECT revision FROM characters WHERE account_id=%s')
                                   + (' FOR UPDATE' if self.mysql else ''), (uid,))
                    row = cursor.fetchone()
                    require(row is not None and row[0] <= source_revision
                            and state['revision'] == source_revision + 1,
                            'A newer character revision exists. Nothing was changed.')
                    cursor.execute(self.sql('UPDATE characters SET state_json=%s,revision=%s,'
                                            'updated_at=%s WHERE account_id=%s'),
                                   (json.dumps(state, separators=(',', ':'), allow_nan=False),
                                    state['revision'], int(time.time()), uid))
                updates = {uid: dict(values) for uid, values in controls}
                for uid, encoded in passwords:
                    require(isinstance(encoded, str) and encoded.startswith('scrypt$'),
                            'Invalid password reset encoding.')
                    cursor.execute(self.sql('UPDATE accounts SET password_hash=%s WHERE id=%s'),
                                   (encoded, uid))
                    updates.setdefault(uid, {})
                for uid, values in updates.items():
                    require(set(values).issubset({*CONTROL_FIELDS, 'banned_raw'}),
                            'Unsupported account-control field.')
                    account = self._admin_account(cursor, uid=uid)
                    require(account is not None, 'Account no longer exists.')
                    if 'banned_raw' in values:
                        cursor.execute(self.sql('UPDATE accounts SET banned=%s WHERE id=%s'),
                                       (int(bool(values['banned_raw'])), uid))
                    merged = {key: int(values.get(key, account[key])) for key in CONTROL_FIELDS}
                    cursor.execute(self.sql('SELECT account_id FROM account_controls WHERE account_id=%s'), (uid,))
                    if cursor.fetchone():
                        cursor.execute(self.sql('UPDATE account_controls SET ban_until=%s,locked=%s,'
                            'frozen=%s,trade_blocked=%s,epoch=%s WHERE account_id=%s'),
                            (*(merged[key] for key in CONTROL_FIELDS), account['epoch'] + 1, uid))
                    else:
                        cursor.execute(self.sql('INSERT INTO account_controls '
                            '(account_id,ban_until,locked,frozen,trade_blocked,epoch) VALUES(%s,%s,%s,%s,%s,%s)'),
                            (uid, *(merged[key] for key in CONTROL_FIELDS), account['epoch'] + 1))
                if create is not None:
                    name, encoded, state = create
                    cursor.execute(self.sql('INSERT INTO accounts '
                        '(username,login_key,password_hash,created_at) VALUES(%s,%s,%s,%s)'),
                        (name, name.lower(), encoded, int(time.time())))
                    created_id = int(cursor.lastrowid)
                    cursor.execute(self.sql('INSERT INTO characters '
                        '(account_id,revision,state_json,updated_at) VALUES(%s,%s,%s,%s)'),
                        (created_id, state['revision'], json.dumps(state, separators=(',', ':'),
                                                                 allow_nan=False), int(time.time())))
                    event = {**event, 'targets': [created_id]}
                self._admin_audit(cursor, event)
        except Exception as error:
            if create is not None and (isinstance(error, sqlite3.IntegrityError)
                    or (error.args and error.args[0] == 1062)):
                raise RequestError('That account already exists or its audit ID conflicts. Nothing was changed.') from None
            raise
        return created_id

    def admin_history(self, uid=None, *, command=None, limit=20):
        require(type(limit) is int and 1 <= limit <= 100, 'History limit must be 1..100.')
        clauses, values = [], []
        query = 'SELECT a.payload,a.created_at,a.entry_id FROM admin_audit a '
        if uid is not None:
            query += 'JOIN admin_audit_targets t ON t.audit_id=a.audit_id '
            clauses.append('t.account_id=%s'); values.append(uid)
        if command is not None:
            clauses.append('a.command=%s'); values.append(command)
        if clauses:
            query += 'WHERE ' + ' AND '.join(clauses)
        query += ' ORDER BY a.entry_id DESC LIMIT %s'; values.append(limit)
        with self.transaction() as cursor:
            cursor.execute(self.sql(query), tuple(values))
            return [{**json.loads(row[0]), 'committed_at': row[1], 'sequence': row[2]} for row in cursor.fetchall()]

    def admin_trade_history(self, uid, limit=20):
        require(type(limit) is int and 1 <= limit <= 100, 'History limit must be 1..100.')
        with self.transaction() as cursor:
            cursor.execute(self.sql('SELECT trade_id,account_a,account_b,payload,created_at '
                'FROM trade_audit WHERE account_a=%s OR account_b=%s '
                'ORDER BY created_at DESC,trade_id DESC LIMIT %s'), (uid, uid, limit))
            return [{'trade': row[0], 'owners': [row[1], row[2]],
                     'exchange': json.loads(row[3]), 'time': row[4]} for row in cursor.fetchall()]

    def admin_economy(self, live_balances):
        """Stream saved accounts; substitute live balances from the locked actor."""
        total = count = 0
        with self.transaction() as cursor:
            last = 0
            while True:
                cursor.execute(self.sql('SELECT account_id,state_json FROM characters WHERE account_id>%s ORDER BY account_id LIMIT 100'),(last,))
                rows = cursor.fetchall()
                if not rows:break
                for uid, text in rows:
                    last = uid
                    count += 1
                    amount = live_balances[uid] if uid in live_balances else json.loads(text)['money']
                    require(type(amount) is int and 0 <= amount <= 2_000_000_000,
                            'An account has invalid currency; economy report stopped.')
                    total += amount
        return {'accounts': count, 'totalMoney': total, 'onlineAccounts': len(live_balances),
                'onlineMoney': sum(live_balances.values())}
