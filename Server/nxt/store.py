"""MySQL/InnoDB persistence with parameterized SQL and atomic two-owner exchange.

SQLite exists exclusively for explicit developer testing. A failed MySQL connection
never falls back to another database. No account passwords are stored in plain text.
State schema is versioned JSON; revisions prevent delayed autosaves replacing newer trades.
"""
from __future__ import annotations
import json,sqlite3,threading,time,uuid
from contextlib import contextmanager,suppress
from .security import RequestError
from .admin_store import AdminStoreMixin
SCHEMA=2
LEASE_SECONDS=60

class WorldLeaseBusy(RuntimeError):
 """A recent lease is present; it may be active or left by an interrupted world."""
 def __init__(self,heartbeat,observed_at):
  self.heartbeat=int(heartbeat);self.observed_at=int(observed_at)
  self.remaining_seconds=max(1,LEASE_SECONDS-(self.observed_at-self.heartbeat))
  super().__init__(f'Another NXT world has a recent database lease. It expires in {self.remaining_seconds} seconds unless that world refreshes it. Stop the other NXT world before starting this copy.')

class WorldSchemaUpgradeBusy(RuntimeError):
 """Safe operator guidance; never serialize a driver/configuration payload."""
 def __init__(self):
  super().__init__('Stop the previous world before upgrading the database schema. A recent world lease is still present; no schema-2 upgrade was applied. After an unclean stop, allow the stale lease to expire, then retry. Keep the pre-upgrade database backup.')

class Store(AdminStoreMixin):
 def __init__(self,settings):
  self.s=settings;self.mysql=settings.get('database','backend')=='mysql';self.lock=threading.RLock();self.db=None;self.closed=False
  self.lease_id=str(uuid.uuid4());self.lease_active=False
  try:self.connect();self.migrate()
  except BaseException:
   self.closed=True
   if self.db is not None:
    with suppress(Exception):self.db.close()
   raise
 def connect(self):
  if self.mysql:
   try:import pymysql
   except ImportError as e:raise RuntimeError('PyMySQL is missing. Run 1 - Install Server Dependencies.cmd.') from e
   if self.s.password()=='CHANGE_ME_WITH_SETUP':raise RuntimeError('Database is not configured. Run 2 - Configure MySQL.cmd.')
   ca=self.s.get('database','ssl_ca')
   if ca:ca=str(self.s.path('database','ssl_ca').resolve())
   self.db=pymysql.connect(host=self.s.get('database','host'),port=self.s.int('database','port'),user=self.s.get('database','user'),password=self.s.password(),database=self.s.get('database','database'),charset='utf8mb4',autocommit=False,connect_timeout=8,read_timeout=15,write_timeout=15,ssl_ca=ca or None,ssl_verify_cert=bool(ca),ssl_verify_identity=bool(ca))
  else:
   p=self.s.path('database','sqlite_path');p.parent.mkdir(parents=True,exist_ok=True);self.db=sqlite3.connect(p,check_same_thread=False,timeout=10,isolation_level=None);self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA foreign_keys=ON')
 def sql(self,s):return s if self.mysql else s.replace('%s','?')
 @contextmanager
 def transaction(self):
  with self.lock:
   if self.closed:raise RuntimeError('World database connection is closed.')
   if self.mysql:self.db.ping(reconnect=True);self.db.begin()
   else:self.db.execute('BEGIN IMMEDIATE')
   cur=self.db.cursor()
   try:yield cur;self.db.commit()
   except BaseException:self.db.rollback();raise
   finally:cur.close()
 def migrate(self):
  suffix=' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin' if self.mysql else ''
  identity='BIGINT PRIMARY KEY AUTO_INCREMENT' if self.mysql else 'INTEGER PRIMARY KEY AUTOINCREMENT'
  large='LONGTEXT' if self.mysql else 'TEXT'
  with self.transaction() as c:
   c.execute('CREATE TABLE IF NOT EXISTS nxt_schema (id INTEGER PRIMARY KEY, version INTEGER NOT NULL)'+suffix)
   c.execute('SELECT version FROM nxt_schema WHERE id=1');row=c.fetchone()
   if row and row[0]>SCHEMA:raise RuntimeError('Database is newer than this server; do not downgrade.')
   c.execute(f'CREATE TABLE IF NOT EXISTS accounts (id {identity}, username VARCHAR(20) NOT NULL, login_key VARCHAR(20) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL, banned INTEGER NOT NULL DEFAULT 0, created_at BIGINT NOT NULL)'+suffix)
   c.execute(f'CREATE TABLE IF NOT EXISTS characters (account_id BIGINT PRIMARY KEY, revision BIGINT NOT NULL, state_json {large} NOT NULL, updated_at BIGINT NOT NULL, FOREIGN KEY (account_id) REFERENCES accounts(id))'+suffix)
   c.execute(f'CREATE TABLE IF NOT EXISTS trade_audit (trade_id VARCHAR(36) PRIMARY KEY, account_a BIGINT NOT NULL, account_b BIGINT NOT NULL, payload {large} NOT NULL, created_at BIGINT NOT NULL)'+suffix)
   c.execute(f'CREATE TABLE IF NOT EXISTS world_leases (id INTEGER PRIMARY KEY, owner VARCHAR(36) NOT NULL, heartbeat BIGINT NOT NULL)'+suffix)
   # Do not silently advance an old deployment's schema merely because a
   # second program was opened while that world still owns a recent lease.
   if row and row[0]<SCHEMA:
    c.execute('SELECT heartbeat FROM world_leases WHERE id=1'+(' FOR UPDATE' if self.mysql else ''));lease=c.fetchone()
    if lease and int(time.time())-lease[0]<LEASE_SECONDS:raise WorldSchemaUpgradeBusy()
   self.migrate_admin(c,suffix,large)
   if not row:c.execute(self.sql('INSERT INTO nxt_schema(id,version) VALUES(1,%s)'),(SCHEMA,))
   elif row[0]<SCHEMA:c.execute(self.sql('UPDATE nxt_schema SET version=%s WHERE id=1'),(SCHEMA,))
 def acquire_lease(self):
  """One world process per database: prevent dual-server ownership races."""
  # Keep ownership publication and close serialized even if a to_thread waiter
  # is cancelled while the underlying database operation is still completing.
  with self.lock:
   with self.transaction() as c:
    c.execute('SELECT owner,heartbeat FROM world_leases WHERE id=1'+(' FOR UPDATE' if self.mysql else ''));row=c.fetchone();now=int(time.time())
    if row and row[0]!=self.lease_id and now-row[1]<LEASE_SECONDS:raise WorldLeaseBusy(row[1],now)
    if row:c.execute(self.sql('UPDATE world_leases SET owner=%s,heartbeat=%s WHERE id=1'),(self.lease_id,now))
    else:c.execute(self.sql('INSERT INTO world_leases(id,owner,heartbeat) VALUES(1,%s,%s)'),(self.lease_id,now))
   self.lease_active=True
 def fence(self,c):
  if not self.lease_active:return
  c.execute('SELECT owner FROM world_leases WHERE id=1'+(' FOR UPDATE' if self.mysql else ''));row=c.fetchone()
  if not row or row[0]!=self.lease_id:raise RuntimeError('World lease fencing rejected this write.')
 def heartbeat(self):
  with self.transaction() as c:
   c.execute('SELECT owner FROM world_leases WHERE id=1'+(' FOR UPDATE' if self.mysql else ''));row=c.fetchone()
   if not row or row[0]!=self.lease_id:raise RuntimeError('World database lease lost. Stop to avoid conflicting ownership.')
   c.execute(self.sql('UPDATE world_leases SET heartbeat=%s WHERE id=1 AND owner=%s'),(int(time.time()),self.lease_id))
 def account(self,login):
  with self.transaction() as c:
   c.execute(self.sql('SELECT id,username,password_hash,banned FROM accounts WHERE login_key=%s'),(login.lower(),));r=c.fetchone()
   if not r:return None
   control=self._admin_account(c,uid=r[0])
   banned=bool(r[3]) and (control['ban_until']==0 or control['ban_until']>int(time.time()))
   return {'id':r[0],'username':r[1],'password_hash':r[2],'banned':banned}
 def create(self,username,password_hash,state):
  try:
   with self.transaction() as c:
    self.fence(c)
    c.execute(self.sql('INSERT INTO accounts(username,login_key,password_hash,created_at) VALUES(%s,%s,%s,%s)'),(username,username.lower(),password_hash,int(time.time())));uid=c.lastrowid
    c.execute(self.sql('INSERT INTO characters(account_id,revision,state_json,updated_at) VALUES(%s,%s,%s,%s)'),(uid,state['revision'],json.dumps(state,separators=(',',':')),int(time.time())))
    return int(uid)
  except Exception as e:
   # Only uniqueness violations are converted; all other errors remain failures.
   if isinstance(e,sqlite3.IntegrityError) or (e.args and e.args[0]==1062):raise RequestError('That username is already registered.') from e
   raise
 def load(self,uid):
  with self.transaction() as c:
   c.execute(self.sql('SELECT state_json FROM characters WHERE account_id=%s'),(uid,));r=c.fetchone()
   if not r:raise RuntimeError('Account has no character record; restore its database backup.')
   return json.loads(r[0])
 def save_many(self,records):
  if not records:return
  with self.transaction() as c:
   self.fence(c)
   for uid,state in records:
    c.execute(self.sql('UPDATE characters SET state_json=%s,revision=%s,updated_at=%s WHERE account_id=%s AND revision<=%s'),(json.dumps(state,separators=(',',':')),state['revision'],int(time.time()),uid,state['revision']))
 def trade(self,trade_id,a,astate,b,bstate,payload):
  with self.transaction() as c:
   self.fence(c)
   c.execute(self.sql('SELECT account_id,revision FROM characters WHERE account_id IN (%s,%s) ORDER BY account_id')+(' FOR UPDATE' if self.mysql else ''),(a,b));rows=c.fetchall()
   if len(rows)!=2:raise RuntimeError('Trade owner record missing.')
   versions={r[0]:r[1] for r in rows}
   if versions[a]>=astate['revision'] or versions[b]>=bstate['revision']:raise RuntimeError('Stale trade state; exchange cancelled.')
   c.execute(self.sql('INSERT INTO trade_audit(trade_id,account_a,account_b,payload,created_at) VALUES(%s,%s,%s,%s,%s)'),(trade_id,a,b,json.dumps(payload,separators=(',',':')),int(time.time())))
   for uid,state in [(a,astate),(b,bstate)]:c.execute(self.sql('UPDATE characters SET state_json=%s,revision=%s,updated_at=%s WHERE account_id=%s'),(json.dumps(state,separators=(',',':')),state['revision'],int(time.time()),uid))
 def ban(self,username,banned):
  # Legacy trusted-extension API; the interactive console uses audited admin_commit.
  with self.transaction() as c:
   self.fence(c);c.execute(self.sql('UPDATE accounts SET banned=%s WHERE login_key=%s'),(int(banned),username.lower()));count=c.rowcount
   c.execute(self.sql('UPDATE account_controls SET ban_until=0,epoch=epoch+1 WHERE account_id=(SELECT id FROM accounts WHERE login_key=%s)'),(username.lower(),));return count
 def close(self):
  # Startup failures and normal shutdown share cleanup. A rejected contender
  # must not remove the other world's lease, and a second close must be harmless.
  with self.lock:
   if self.closed:return
   try:
    if self.lease_active:
     with self.transaction() as c:c.execute(self.sql('DELETE FROM world_leases WHERE id=1 AND owner=%s'),(self.lease_id,))
   finally:
    self.lease_active=False;self.closed=True
    if self.db is not None:self.db.close()
