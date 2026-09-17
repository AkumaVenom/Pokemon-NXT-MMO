"""Deterministic regression contracts. All databases are isolated temporary SQLite files.
These tests do NOT establish MySQL deployment or a 1,000-user performance rating.
Run: python -m unittest discover -s Tests -v
"""
from __future__ import annotations
import asyncio,copy,dataclasses,hashlib,json,random,sys,tempfile,time,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
TEMPLATE=ROOT/'Build/config_templates/Server/config.ini'
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.world import World,Player
from nxt.security import RequestError,credentials,password_hash,password_verify,integer,Bucket
from nxt.combat import Battle,matchup
class SecurityTests(unittest.TestCase):
 def test_username_and_password_bounds(self):
  for name in ('a','x'*21,'a b',"sql'",'<script>','Αlpha'):
   with self.assertRaises(RequestError):credentials(name,'good-password-123')
  self.assertEqual(credentials('Valid_Trainer','good-password-123')[0],'Valid_Trainer')
 def test_integer_rejects_bool_float_and_nan(self):
  for value in (True,False,1.1,float('nan'),'1',None,-1,11):
   with self.assertRaises(RequestError):integer(value,0,10)
 def test_scrypt_verification_and_salts(self):
  a=password_hash('Strong_test_password!');b=password_hash('Strong_test_password!');self.assertNotEqual(a,b);self.assertTrue(password_verify('Strong_test_password!',a));self.assertFalse(password_verify('Wrong_test_password!',a));self.assertFalse(password_verify('bad','broken'))
 def test_bucket_is_bounded(self):
  b=Bucket(2,60);self.assertTrue(b.take());self.assertTrue(b.take());self.assertFalse(b.take())
 def test_hard_cap_config_validation(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'config.ini';p.write_text(TEMPLATE.read_text().replace('max_players = 1000','max_players = 1001'))
   with self.assertRaises(ValueError):Settings.load(p)
class ContentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=Content(ROOT/'Server/data/world.json')
 def test_map_dimensions_and_safe_spawns(self):
  # Adventure retains the 859 baseline maps and restores 100 native Sigma maps.
  self.assertEqual(len(self.c.maps),959)
  for m in self.c.maps.values():
   self.assertEqual(len(m['collision']),m['width']*m['height']);self.assertEqual(len(m['behavior']),len(m['collision']))
   if m.get('playable',True):x,y=m['spawn'];self.assertTrue(0<=x<m['width'] and 0<=y<m['height']);self.assertEqual(m['collision'][y*m['width']+x],0)
 def test_starter_species_and_correct_learnset_alignment(self):
  for key in self.c.data['starters']:self.assertIn(key,self.c.species)
  self.assertEqual(self.c.species['fr_4']['learnset'][0],[1,10]);self.assertIn([7,52],self.c.species['fr_4']['learnset']);self.assertEqual(self.c.species['fr_7']['learnset'][0],[1,33]);self.assertIn([7,145],self.c.species['fr_7']['learnset'])
 def test_catalog_assets_exist(self):
  assets=ROOT/'Client/app/assets'
  for s in self.c.species.values():
   for field in ('front','back','shiny','backShiny','icon'):self.assertTrue((assets/s[field]).is_file(),f"{s['name']}: {field}")
 def test_client_pack_and_digest_match(self):
  client=json.loads((ROOT/'Client/app/assets/world/client.json').read_text());self.assertEqual(client['pack'],self.c.pack);self.assertEqual(client['assetDigest'],self.c.data['assetDigest']);world=copy.deepcopy(self.c.data);pack=world.pop('pack');self.assertEqual(hashlib.sha256(json.dumps(world,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()[:24],pack)
 def test_png_digest_matches_actual_assets(self):
  root=ROOT/'Client/app/assets';digest=hashlib.sha256()
  for path in sorted(root.rglob('*.png')):
   name=path.relative_to(root).as_posix().encode();digest.update(len(name).to_bytes(4,'big'));digest.update(name);digest.update(hashlib.sha256(path.read_bytes()).digest())
  self.assertEqual(digest.hexdigest(),self.c.data['assetDigest'])
 def test_type_chart_immunity_and_dual_type(self):
  self.assertEqual(matchup(13,[4]),0);self.assertEqual(matchup(10,[12,6]),4);self.assertEqual(matchup(11,[10,5]),4);self.assertEqual(matchup(0,[7]),0)
 def test_unique_ownership_ids_and_growth(self):
  a=self.c.new_mon('fr_1',5);b=self.c.new_mon('fr_1',5);self.assertNotEqual(a['uid'],b['uid']);self.assertEqual(a['hp'],self.c.stats(a)[0]);self.c.gain_xp(a,1000);self.assertGreater(a['level'],5);self.assertLessEqual(a['hp'],self.c.stats(a)[0])
class WorldTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):cls.c=Content(ROOT/'Server/data/world.json')
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();path=Path(self.tmp.name)/'config.ini';path.write_text(TEMPLATE.read_text());self.s=Settings.load(path);self.s.config.set('database','backend','sqlite')
  # These legacy fixtures test replication, chat and atomic transactions. Enable
  # the explicit administrator exploration mode only here; the adventure suite
  # independently exercises badge travel and nearby-Mart rules with it disabled.
  self.s.config.set('world','allow_alpha_atlas','true')
  self.s=dataclasses.replace(self.s,encounter_chance=0);self.db=Store(self.s);self.db.acquire_lease();self.w=World(self.c,self.db,self.s);self.old_rng=self.c.rng;self.c.rng=random.Random(5678)
  self.a=await self.make_player('Alice');self.b=await self.make_player('Bobby')
 async def asyncTearDown(self):
  self.w.players.clear();self.c.rng=self.old_rng;self.db.close();self.tmp.cleanup()
 async def make_player(self,name,starter='fr_1'):
  state=self.w.initial(name,'Kanto',starter,0);uid=self.db.create(name,'unit-test-hash-not-for-network',state);return await self.w.join(uid,name,state,asyncio.Queue(maxsize=2048))
 def packets(self,p,kind=None):
  out=[]
  while not p.queue.empty():
   v=p.queue.get_nowait()
   if kind is None or v['type']==kind:out.append(v)
  return out
 async def begin_trade(self):
  await self.w.dispatch(self.a,{'op':'invite','kind':'trade','target':self.b.id});key=next(iter(self.w.invites));await self.w.dispatch(self.b,{'op':'invite.answer','id':key,'accept':True});return self.w.trades[self.a.trade]
 async def offer(self,p,t,mons=(),money=0,items=None):await self.w.dispatch(p,{'op':'trade','id':t['id'],'action':'offer','revision':t['revision'],'offer':{'pokemon':list(mons),'items':items or {},'money':money}})
 async def finish(self,t):
  for p in (self.a,self.b):await self.w.dispatch(p,{'op':'trade','id':t['id'],'action':'lock','revision':t['revision']})
  for p in (self.a,self.b):await self.w.dispatch(p,{'op':'trade','id':t['id'],'action':'confirm','revision':t['revision'],'digest':self.w.trade_digest(t)})
 async def test_register_case_insensitive_unique(self):
  with self.assertRaises(RequestError):self.db.create('aLiCe','unused',self.a.state)
 async def test_duplicate_login_rejected(self):
  with self.assertRaises(RequestError):await self.w.join(self.a.id,self.a.username,copy.deepcopy(self.a.state),asyncio.Queue())
 async def test_1000_admission_cap_logic_only(self):
  initial=self.w.initial('Capacity','Kanto','fr_1',0)
  for i in range(3,1001):await self.w.join(i,'Capacity'+str(i),copy.deepcopy(initial),asyncio.Queue(maxsize=10))
  self.assertEqual(len(self.w.players),1000)
  with self.assertRaises(RequestError):await self.w.join(1001,'Overflow',copy.deepcopy(initial),asyncio.Queue())
 async def test_movement_and_follower_are_authoritative(self):
  old=(self.a.state['x'],self.a.state['y']);await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':'right'});self.assertEqual((self.a.state['x'],self.a.state['y']),(old[0]+1,old[1]));self.assertEqual((self.a.fx,self.a.fy),old)
 async def test_speed_and_replayed_sequence_do_not_teleport(self):
  await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':'right'});x=self.a.state['x'];await self.w.dispatch(self.a,{'op':'move','seq':2,'direction':'right'});await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':'right'});self.assertEqual(self.a.state['x'],x)
 async def test_collision_and_invalid_direction(self):
  m=self.c.maps[self.a.state['map']];self.assertFalse(self.w.walkable(m,0,0));self.assertFalse(self.w.walkable(m,-1,0))
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':'teleport'})
 async def test_invalid_placeholder_map_is_blocked(self):
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'travel','map':'kanto_3_50'})
 async def test_region_travel_and_replication_isolation(self):
  self.packets(self.a);self.packets(self.b);await self.w.dispatch(self.b,{'op':'travel','map':'johto_3_0'});await self.w.tick();self.assertEqual(self.b.state['map'],'johto_3_0');scenes=self.packets(self.a,'scene');self.assertTrue(scenes);self.assertNotIn(self.b.id,[q['id'] for q in scenes[-1]['players']])
 async def test_global_chat_crosses_regions_and_trusts_server_name(self):
  await self.w.dispatch(self.b,{'op':'travel','map':'johto_3_0'});self.packets(self.b);await self.w.dispatch(self.a,{'op':'chat','channel':'trade','text':'Selling a Potion','username':'Impostor'});msg=self.packets(self.b,'chat')[-1];self.assertEqual(msg['username'],'Alice');self.assertEqual(msg['text'],'Selling a Potion')
 async def test_chat_invalid_channel_and_newline_rejected(self):
  for d in ({'channel':'admin','text':'test'},{'channel':'general','text':'a\nb'}):
   with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'chat',**d})
 async def test_own_state_is_private(self):
  packets=self.packets(self.b);self.assertEqual(len([p for p in packets if p['type']=='state']),1);await self.w.tick();scene=self.packets(self.b,'scene')[-1]
  for entity in scene['players']:
   for forbidden in ('items','money','creatures','password','ivs'):self.assertNotIn(forbidden,entity)
 async def test_invitation_contains_kind(self):
  self.packets(self.b);await self.w.dispatch(self.a,{'op':'invite','kind':'trade','target':self.b.id});self.assertEqual(self.packets(self.b,'invite')[-1]['kind'],'trade')
 async def test_invite_self_and_far_trainer_rejected(self):
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'invite','kind':'trade','target':self.a.id})
  await self.w.dispatch(self.b,{'op':'travel','map':'johto_3_0'})
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'invite','kind':'challenge','target':self.b.id})
 async def test_trade_atomic_ownership_money_items_and_audit(self):
  au=self.a.state['party'][0];bu=self.b.state['party'][0];t=await self.begin_trade();await self.offer(self.a,t,[au],100,{'pokeball':3});await self.offer(self.b,t,[bu],0,{'potion':1});await self.finish(t)
  self.assertEqual(self.a.state['party'][0],bu);self.assertEqual(self.b.state['party'][0],au);self.assertEqual(self.a.state['money'],2900);self.assertEqual(self.b.state['money'],3100);self.assertEqual(self.a.state['items']['pokeball'],17);self.assertEqual(self.b.state['items']['pokeball'],23);self.assertEqual(self.a.state['items']['potion'],6);self.assertEqual(self.db.load(self.a.id),self.a.state)
  with self.db.transaction()as cur:cur.execute('SELECT COUNT(*) FROM trade_audit');self.assertEqual(cur.fetchone()[0],1)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'trade','id':t['id'],'action':'confirm','revision':t['revision'],'digest':self.w.trade_digest(t)})
 async def test_trade_edit_resets_both_locks_and_confirmations(self):
  t=await self.begin_trade()
  for p in (self.a,self.b):await self.w.dispatch(p,{'op':'trade','id':t['id'],'action':'lock','revision':t['revision']})
  await self.w.dispatch(self.a,{'op':'trade','id':t['id'],'action':'confirm','revision':t['revision'],'digest':self.w.trade_digest(t)});await self.offer(self.b,t,money=10);self.assertFalse(t['ready']);self.assertFalse(t['confirmed'])
 async def test_trade_stale_revision_and_wrong_digest_rejected(self):
  t=await self.begin_trade();await self.offer(self.a,t,money=10)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'trade','id':t['id'],'action':'lock','revision':0})
  for p in (self.a,self.b):await self.w.dispatch(p,{'op':'trade','id':t['id'],'action':'lock','revision':t['revision']})
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'trade','id':t['id'],'action':'confirm','revision':t['revision'],'digest':'bad'})
 async def test_trade_unowned_and_duplicate_pokemon_rejected(self):
  t=await self.begin_trade()
  with self.assertRaises(RequestError):await self.offer(self.a,t,[self.b.state['party'][0]])
  with self.assertRaises(RequestError):await self.offer(self.a,t,[self.a.state['party'][0]]*2)
 async def test_trade_cannot_remove_last_pokemon_without_replacement(self):
  before=copy.deepcopy(self.a.state);t=await self.begin_trade();await self.offer(self.a,t,self.a.state['party'])
  with self.assertRaises(RequestError):await self.finish(t)
  self.assertEqual(self.a.state,before);self.assertFalse(t['confirmed'])
 async def test_trade_db_failure_changes_neither_owner(self):
  before_a=copy.deepcopy(self.a.state);before_b=copy.deepcopy(self.b.state);t=await self.begin_trade();await self.offer(self.a,t,money=100);original=self.db.trade
  def fail(*args):raise RuntimeError('injected transaction failure')
  self.db.trade=fail
  with self.assertLogs('nxt.world',level='ERROR'):await self.finish(t)
  self.db.trade=original;self.assertEqual(self.a.state,before_a);self.assertEqual(self.b.state,before_b);self.assertEqual(self.db.load(self.a.id),before_a);self.assertNotIn(t['id'],self.w.trades)
 async def test_disconnect_cancels_trade_without_exchange(self):
  t=await self.begin_trade();await self.offer(self.a,t,money=100);await self.w.leave(self.b);self.assertIsNone(self.a.trade);self.assertEqual(self.a.state['money'],3000);self.assertNotIn(t['id'],self.w.trades)
 async def test_trade_locks_movement_and_party_changes(self):
  await self.begin_trade();old=copy.deepcopy(self.a.state);await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':'right'});self.assertEqual(self.a.state,old)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'party','party':self.a.state['party']})
 async def test_purchases_validate_balance_and_persist(self):
  await self.w.dispatch(self.a,{'op':'buy','item':'pokeball','quantity':2});self.assertEqual(self.a.state['money'],2600);self.assertEqual(self.db.load(self.a.id)['items']['pokeball'],22)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'buy','item':'ultraball','quantity':99})
 async def test_party_requires_owned_nonempty_unique(self):
  for party in ([],[self.b.state['party'][0]],self.a.state['party']*2):
   with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'party','party':party})
 async def test_wild_capture_persists_and_consumes_ball(self):
  await self.w.start_wild(self.a,('fr_129',2));b=self.w.battles[self.a.battle];self.c.rng.random=lambda:0.0
  native_shake_range = self.c.rng.randrange; self.c.rng.randrange = lambda *args: 0 if args==(65536,) else native_shake_range(*args)
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'capture','item':'pokeball'});self.assertEqual(len(self.a.state['creatures']),2);self.assertEqual(self.a.state['items']['pokeball'],19);self.assertEqual(self.db.load(self.a.id),self.a.state);self.assertIsNone(self.a.battle)
 async def test_capture_full_collection_spends_no_ball(self):
  self.w.s=dataclasses.replace(self.s,max_owned=1);await self.w.start_wild(self.a,('fr_129',2));b=self.w.battles[self.a.battle]
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'capture','item':'pokeball'})
  self.assertEqual(b.items[0]['pokeball'],20)
 async def test_duel_is_cloned_and_forfeit_immediate(self):
  original_a=copy.deepcopy(self.a.state);original_b=copy.deepcopy(self.b.state);await self.w.dispatch(self.a,{'op':'invite','kind':'challenge','target':self.b.id});key=next(iter(self.w.invites));await self.w.dispatch(self.b,{'op':'invite.answer','id':key,'accept':True});battle=self.w.battles[self.a.battle]
  await self.w.dispatch(self.a,{'op':'battle','id':battle.id,'action':'attack','slot':0});await self.w.dispatch(self.b,{'op':'battle','id':battle.id,'action':'attack','slot':0});await self.w.dispatch(self.a,{'op':'battle','id':battle.id,'action':'run'});self.assertIsNone(self.a.battle);self.assertIsNone(self.b.battle);self.assertEqual(self.a.state,original_a);self.assertEqual(self.b.state,original_b)
 async def test_old_save_does_not_overwrite_committed_revision(self):
  old=copy.deepcopy(self.a.state);await self.w.dispatch(self.a,{'op':'buy','item':'pokeball','quantity':1});self.db.save_many([(self.a.id,old)]);self.assertEqual(self.db.load(self.a.id)['money'],2800)
 async def test_database_fencing_blocks_old_world_writes(self):
  old=copy.deepcopy(self.a.state)
  with self.db.transaction()as cur:cur.execute('UPDATE world_leases SET owner=? WHERE id=1',('replacement-world',))
  with self.assertRaises(RuntimeError):self.db.save_many([(self.a.id,old)])
  with self.assertRaises(RuntimeError):self.db.heartbeat()
 async def test_queue_overflow_marks_slow_client_closed(self):
  p=Player(999,'Slow',self.a.state,asyncio.Queue(maxsize=1));p.send('one');p.send('two');self.assertTrue(p.closed)
if __name__=='__main__':unittest.main()
