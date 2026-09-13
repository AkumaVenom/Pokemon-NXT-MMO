"""Durable, owner-isolated adventure services against a real temporary database.

The small trainer/center fixture isolates rules; ROM extraction and complete map
coverage are checked separately by the content and center suites.
"""
import asyncio,copy,dataclasses,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'))
from nxt.content import Content
from nxt.config import Settings
from nxt.store import Store
from nxt.world import World
from nxt.security import RequestError

class AdventureTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):cls.base=Content(ROOT/'Server/data/world.json')
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();config=Path(self.temp.name)/'config.ini';config.write_text((ROOT/'Build/config_templates/Server/config.ini').read_text());settings=Settings.load(config);settings.config.set('database','backend','sqlite');self.s=dataclasses.replace(settings,encounter_chance=0)
  self.c=copy.copy(self.base);self.c.data=copy.deepcopy(self.base.data);self.c.maps=self.c.data['maps'];self.c.data['adventure']=json.loads((ROOT/'Server/data/adventure.json').read_text());self.map=self.c.data['homes']['Kanto'];m=self.c.maps[self.map];x,y=m['spawn'];self.x=x;self.y=y
  m['objects']=[{'id':220,'x':x,'y':y-1,'graphics':64,'trainerType':0}]+[{'id':n,'x':x,'y':y-1,'graphics':19,'trainerType':1} for n in range(230,246)]
  self.c.data['centers']={self.map:{'nurseNpcIds':[220],'pcNpcIds':[],'nursePcAccess':True,'respawn':[x,y]}}
  trainers={};gyms=[]
  for i in range(16):
   region='kanto' if i<8 else 'johto';order=i%8+1;key=f'{self.map}:{230+i}';trainers[key]={'id':key,'map':self.map,'npc':230+i,'name':f'{region} leader {order}','team':[{'species':'fr_19','level':5,'moves':[33]}]};gyms.append({'region':region,'order':order,'name':trainers[key]['name'],'map':self.map,'npc':230+i})
  self.c.data['adventureRom']={'trainers':trainers,'gyms':gyms};self.db=Store(self.s);self.db.acquire_lease();self.w=World(self.c,self.db,self.s);self.a=await self.add('Akuma','fr_152');self.b=await self.add('Spider','fr_4')
 async def asyncTearDown(self):self.w.players.clear();self.db.close();self.temp.cleanup()
 async def add(self,name,starter):
  state=self.w.initial(name,'Kanto',starter,0);uid=self.db.create(name,'unused',state);return await self.w.join(uid,name,state,asyncio.Queue(maxsize=2048))
 def packets(self,p):
  packets=[]
  while not p.queue.empty():packets.append(p.queue.get_nowait())
  return packets
 async def win(self,p,npc=230):
  await self.w.dispatch(p,{'op':'npc','npc':npc,'action':'battle'});battle=self.w.battles[p.battle];battle.resolve=lambda:None;battle.ended=True;battle.winner=0;battle.experience_events=[{'species':'fr_19','level':5,'participants':[p.state['party'][0]]}];await self.w.resolve_battle(battle);return battle
 async def test_starter_identity_and_owned_dex_are_independent(self):
  self.assertEqual(self.a.state['adventure']['caught'],['fr_152']);self.assertEqual(self.b.state['adventure']['caught'],['fr_4']);self.assertEqual(self.w.adventure.public(self.a.state)['regions'][0]['badges'][0]['earned'],False)
 async def test_legacy_migration_preserves_character_and_visits_existing_location(self):
  old=copy.deepcopy(self.a.state);old.pop('adventure');expected={k:copy.deepcopy(v) for k,v in old.items()};self.w.validate_state(old)
  for k,v in expected.items():self.assertEqual(old[k],v)
  self.assertEqual(old['adventure']['visited'],[old['map']]);self.assertEqual(old['adventure']['caught'],['fr_152'])
 async def test_sixteen_ordered_badges_keep_regions_independent(self):
  for region,npcs in [('kanto',range(230,238)),('johto',range(238,246))]:
   with self.assertRaisesRegex(RequestError,'earlier badges'):await self.w.dispatch(self.a,{'op':'npc','npc':list(npcs)[1],'action':'battle'})
   for index,npc in enumerate(npcs,1):
    await self.win(self.a,npc);self.assertIn(f'{region}_{index}',self.db.load(self.a.id)['adventure']['badges'])
  self.assertEqual(len(self.a.state['adventure']['badges']),16);self.assertEqual(self.b.state['adventure']['badges'],[])
 async def test_trainer_victory_and_exp_commit_once_and_rematch_does_not_farm(self):
  before=copy.deepcopy(self.a.state);await self.win(self.a);saved=self.db.load(self.a.id);self.assertGreater(saved['money'],before['money']);self.assertGreater(saved['creatures'][0]['exp'],before['creatures'][0]['exp']);self.assertEqual(saved['adventure']['badges'],['kanto_1'])
  with self.assertRaisesRegex(RequestError,'resting'):await self.w.dispatch(self.a,{'op':'npc','npc':230,'action':'battle'})
  with patch('nxt.adventure.time.time',return_value=4_000_000_000):await self.win(self.a)
  after=self.db.load(self.a.id);self.assertEqual(after['money'],saved['money']);self.assertEqual(after['creatures'][0]['exp'],saved['creatures'][0]['exp']);self.assertEqual(after['adventure']['trainers'][f'{self.map}:230']['wins'],2)
 async def test_battle_save_failure_cannot_publish_badge_or_reward(self):
  await self.w.dispatch(self.a,{'op':'npc','npc':230,'action':'battle'});before=copy.deepcopy(self.a.state);battle=self.w.battles[self.a.battle];battle.resolve=lambda:None;battle.ended=True;battle.winner=0;battle.experience_events=[]
  with patch.object(self.db,'save_many',side_effect=OSError('disk unavailable')):await self.w.resolve_battle(battle)
  self.assertEqual(self.a.state,before);self.assertEqual(self.db.load(self.a.id),before);self.assertFalse(self.a.state['adventure']['badges']);self.assertIsNone(self.a.battle)
 async def test_trainer_start_requires_proximity_and_no_spoofed_remote_identity(self):
  self.a.state['x']=self.x+5
  with self.assertRaisesRegex(RequestError,'closer'):await self.w.dispatch(self.a,{'op':'npc','npc':230,'action':'battle','map':self.map,'ownerId':self.b.id})
  self.assertIsNone(self.a.battle);self.assertIsNone(self.b.battle)
 async def test_journal_claim_is_durable_once_and_private(self):
  await self.win(self.a);self.packets(self.a);self.packets(self.b);before=copy.deepcopy(self.b.state)
  await self.w.dispatch(self.a,{'op':'journal.claim','id':'first_trainer'});self.assertIn('first_trainer',self.db.load(self.a.id)['adventure']['claimed']);self.assertEqual(self.b.state,before);self.assertFalse(any(p['type']=='state' for p in self.packets(self.b)))
  with self.assertRaisesRegex(RequestError,'already'):await self.w.dispatch(self.a,{'op':'journal.claim','id':'first_trainer'})
 async def test_incomplete_and_full_bag_objectives_cannot_consume_claim(self):
  with self.assertRaisesRegex(RequestError,'Finish'):await self.w.dispatch(self.a,{'op':'journal.claim','id':'first_trainer'})
  await self.win(self.a);state=copy.deepcopy(self.a.state);state['items']['potion']=999;await self.w.commit(self.a,state)
  with self.assertRaisesRegex(RequestError,'Make room'):await self.w.dispatch(self.a,{'op':'journal.claim','id':'first_trainer'})
  self.assertNotIn('first_trainer',self.a.state['adventure']['claimed'])
 async def test_nurse_restores_party_hp_status_pp_and_saves_center(self):
  state=copy.deepcopy(self.a.state);mon=state['creatures'][0];mon['hp']=1;mon['status']='poison';mon['sleep']=2
  for move in mon['moves']:move['pp']=0
  await self.w.commit(self.a,state);await self.w.dispatch(self.a,{'op':'npc','npc':220,'action':'heal'});saved=self.db.load(self.a.id);mon=saved['creatures'][0];self.assertEqual(mon['hp'],self.c.stats(mon)[0]);self.assertEqual(mon['status'],'');self.assertEqual(mon['sleep'],0);self.assertTrue(all(m['pp']==self.c.moves[str(m['id'])]['pp'] for m in mon['moves']));self.assertEqual(saved['adventure']['lastCenter'],self.map)
 async def test_remote_heal_or_fake_nurse_cannot_bypass_location_even_with_atlas(self):
  with self.assertRaisesRegex(RequestError,'Nurse Joy'):await self.w.dispatch(self.a,{'op':'heal','npc':220})
  self.c.maps[self.map]['objects'].append({'id':219,'x':self.x,'y':self.y,'graphics':64,'trainerType':0})
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'npc','npc':219,'action':'heal'})
  self.a.state['x']=self.x+5
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'npc','npc':220,'action':'heal'})
 async def test_nurse_save_failure_keeps_injuries_and_emits_no_heal_confirmation(self):
  self.a.state['creatures'][0]['hp']=1;before=copy.deepcopy(self.a.state);self.packets(self.a)
  with patch.object(self.db,'save_many',side_effect=OSError('disk unavailable')):
   with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'npc','npc':220,'action':'heal'})
  self.assertEqual(self.a.state,before);self.assertFalse(any(p['type'] in ('audio','dialog','state') for p in self.packets(self.a)))
 async def test_pc_transfer_preserves_uid_and_durable_owner_only_collection(self):
  state=copy.deepcopy(self.a.state);extra=self.c.new_mon('fr_7',5,'Akuma');state['creatures'].append(extra);await self.w.commit(self.a,state);await self.w.dispatch(self.a,{'op':'pc','action':'withdraw','uid':extra['uid']});await self.w.dispatch(self.a,{'op':'pc','action':'deposit','uid':state['party'][0]});saved=self.db.load(self.a.id);self.assertEqual(saved['party'],[extra['uid']]);self.assertEqual(len(saved['creatures']),2);self.assertEqual(self.b.state['creatures'][0]['species'],'fr_4')
 async def test_pc_rejects_other_owner_last_healthy_and_remote_party_shortcut(self):
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'pc','action':'withdraw','uid':self.b.state['party'][0]})
  with self.assertRaisesRegex(RequestError,'healthy'):await self.w.dispatch(self.a,{'op':'pc','action':'deposit','uid':self.a.state['party'][0]})
  state=copy.deepcopy(self.a.state);extra=self.c.new_mon('fr_7',5,'Akuma');extra['hp']=0;state['creatures'].append(extra);state['party'].append(extra['uid']);await self.w.commit(self.a,state)
  with self.assertRaisesRegex(RequestError,'healthy'):await self.w.dispatch(self.a,{'op':'pc','action':'deposit','uid':state['party'][0]})
  self.a.state['x']=self.x+5
  with self.assertRaisesRegex(RequestError,'PC'):await self.w.dispatch(self.a,{'op':'party','party':[state['party'][0]]})
 async def test_storage_full_party_refuses_withdrawal(self):
  state=copy.deepcopy(self.a.state)
  for _ in range(6):state['creatures'].append(self.c.new_mon('fr_19',5,'Akuma'))
  state['party']=[m['uid'] for m in state['creatures'][:6]];await self.w.commit(self.a,state)
  with self.assertRaisesRegex(RequestError,'full'):await self.w.dispatch(self.a,{'op':'pc','action':'withdraw','uid':state['creatures'][-1]['uid']})
 async def test_exploration_and_surf_unlocks_require_real_badges(self):
  self.s.config.set('world','allow_alpha_atlas','false');self.s.config.set('world','allow_alpha_surf','false')
  with self.assertRaisesRegex(RequestError,'two badges'):await self.w.dispatch(self.a,{'op':'travel','map':self.c.data['homes']['Johto']})
  with self.assertRaisesRegex(RequestError,'Surf badge'):await self.w.dispatch(self.a,{'op':'surf'})
  await self.win(self.a,230);await self.win(self.a,231);await self.w.dispatch(self.a,{'op':'travel','map':self.c.data['homes']['Johto']});saved=self.db.load(self.a.id);self.assertIn(saved['map'],saved['adventure']['visited']);self.assertIn('travel_pass',saved['adventure']['unlocks'])
 async def test_restart_keeps_badge_objective_dex_and_starter(self):
  await self.win(self.a);await self.w.dispatch(self.a,{'op':'journal.claim','id':'first_trainer'});uid=self.a.id;expected=copy.deepcopy(self.a.state);await self.w.leave(self.a);new_world=World(self.c,self.db,self.s);p=await new_world.join(uid,'Akuma',None,asyncio.Queue());self.assertEqual(p.state,expected);self.assertEqual(p.entity()['follower'],'fr_152')

 async def test_legacy_login_migration_is_saved_before_joined_and_not_repeated(self):
  old=copy.deepcopy(self.a.state);old.pop('adventure');self.db.save_many([(self.a.id,old)]);world=World(self.c,self.db,self.s);queue=asyncio.Queue();player=await world.join(self.a.id,'Akuma',None,queue);saved=self.db.load(self.a.id);self.assertEqual(saved,player.state);self.assertEqual(saved['revision'],old['revision']+1);await world.leave(player);again=await world.join(self.a.id,'Akuma',None,asyncio.Queue());self.assertEqual(again.state['revision'],saved['revision'])
 async def test_failed_legacy_migration_publishes_no_session_or_changed_account(self):
  old=copy.deepcopy(self.a.state);old.pop('adventure');self.db.save_many([(self.a.id,old)]);world=World(self.c,self.db,self.s);queue=asyncio.Queue()
  with patch.object(self.db,'save_many',side_effect=OSError('disk unavailable')):
   with self.assertRaisesRegex(RequestError,'migration'):await world.join(self.a.id,'Akuma',None,queue)
  self.assertNotIn(self.a.id,world.players);self.assertTrue(queue.empty());self.assertEqual(self.db.load(self.a.id),old)
 async def test_money_trade_does_not_withdraw_stored_pokemon(self):
  for player in (self.a,self.b):
   state=copy.deepcopy(player.state);state['creatures'].append(self.c.new_mon('fr_7',5,player.username));await self.w.commit(player,state)
  original={p.id:list(p.state['party']) for p in (self.a,self.b)};trade={'id':'storage-preservation','players':[self.a.id,self.b.id],'offers':{self.a.id:{'pokemon':[],'items':{},'money':1},self.b.id:{'pokemon':[],'items':{},'money':0}}};await self.w.commit_trade(trade)
  for p in (self.a,self.b):self.assertEqual(p.state['party'],original[p.id]);self.assertEqual(self.db.load(p.id)['party'],original[p.id])
 async def test_exp_during_multi_pokemon_battle_survives_next_roster_snapshot(self):
  await self.w.dispatch(self.a,{'op':'npc','npc':230,'action':'battle'});battle=self.w.battles[self.a.battle];battle.rosters[1].append(self.c.new_mon('fr_16',5,'Trainer'));battle.rosters[1][0]['hp']=0;battle.active[1]=1;battle.resolve=lambda:None;battle.ended=False;battle.experience_events=[{'species':'fr_19','level':5,'participants':[self.a.state['party'][0]]}];before=self.a.state['creatures'][0]['exp'];await self.w.resolve_battle(battle);saved=self.db.load(self.a.id);self.assertGreater(saved['creatures'][0]['exp'],before);self.assertEqual(battle.rosters[0][0]['exp'],saved['creatures'][0]['exp']);battle.experience_events=[];await self.w.resolve_battle(battle);self.assertEqual(self.db.load(self.a.id)['creatures'][0]['exp'],saved['creatures'][0]['exp'])

 async def test_earned_waypoints_reject_interiors_even_when_visited(self):
  self.s.config.set('world','allow_alpha_atlas','false');inside=next(key for key,m in self.c.maps.items() if m.get('mapType')==8 and m.get('playable',True));state=copy.deepcopy(self.a.state);state['adventure']['unlocks'].append('travel_pass');state['adventure']['visited'].append(inside);await self.w.commit(self.a,state);before=copy.deepcopy(self.a.state)
  with self.assertRaisesRegex(RequestError,'outdoors'):await self.w.dispatch(self.a,{'op':'travel','map':inside})
  self.assertEqual(self.a.state,before);self.assertEqual(self.db.load(self.a.id),before)
 async def test_explicit_atlas_and_home_clear_returns_without_clearing_ordinary_relocation(self):
  self.s.config.set('world','allow_alpha_atlas','true');entry={'inside':'johto_32_0','outside':'johto_3_47','x':43,'y':6};state=copy.deepcopy(self.a.state);state['warpReturns']=[entry];await self.w.commit(self.a,state);await self.w.relocate_saved(self.a,self.map,transition='connection');self.assertEqual(self.a.state['warpReturns'],[entry]);await self.w.dispatch(self.a,{'op':'travel','map':self.c.data['homes']['Johto']});self.assertEqual(self.db.load(self.a.id)['warpReturns'],[])
  state=copy.deepcopy(self.a.state);state['warpReturns']=[entry];await self.w.commit(self.a,state);await self.w.dispatch(self.a,{'op':'unstuck'});self.assertEqual(self.db.load(self.a.id)['warpReturns'],[])
 async def test_shared_center_rescue_restores_each_accounts_actual_door(self):
  key='johto_32_0';self.c.data['centers'][key]=copy.deepcopy(self.base.data['centers'][key])
  async def step(player,direction):
   player.last_move=0;await self.w.dispatch(player,{'op':'move','seq':player.last_seq+1,'direction':direction})
  for player,x,y in ((self.a,43,6),(self.b,28,46)):
   await self.w.relocate_saved(player,'johto_3_47',x,y);await step(player,'up');self.assertEqual(player.state['map'],key)
   for _ in range(3):await step(player,'up')
   await self.w.dispatch(player,{'op':'npc','npc':1,'action':'heal'});saved_returns=copy.deepcopy(player.state['adventure']['lastCenterReturns']);self.assertEqual(saved_returns[-1]['x'],x)
   for _ in range(4):await step(player,'down')
   self.assertEqual(player.state['map'],'johto_3_47');self.assertEqual(player.state['warpReturns'],[])
   await self.w.start_wild(player,('fr_19',5));battle=self.w.battles[player.battle];battle.resolve=lambda:None;battle.ended=True;battle.winner=1;battle.experience_events=[]
   for mon in battle.rosters[0]:mon['hp']=0
   await self.w.resolve_battle(battle);self.assertEqual(player.state['map'],key);self.assertEqual(self.db.load(player.id)['warpReturns'],saved_returns)
   for _ in range(4):await step(player,'down')
   self.assertEqual((player.state['map'],player.state['x'],player.state['y']),('johto_3_47',x,y));self.assertEqual(player.state['warpReturns'],[])
  self.assertEqual(self.a.state['adventure']['lastCenterReturns'][-1]['x'],43);self.assertEqual(self.b.state['adventure']['lastCenterReturns'][-1]['x'],28)
 async def test_missing_shared_center_context_rescues_to_safe_home(self):
  key='johto_32_0';self.c.data['centers'][key]=copy.deepcopy(self.base.data['centers'][key]);state=copy.deepcopy(self.a.state);state['adventure'].update(lastCenter=key,lastCenterPosition=[28,4],lastCenterReturns=[]);await self.w.commit(self.a,state);await self.w.start_wild(self.a,('fr_19',5));battle=self.w.battles[self.a.battle];battle.resolve=lambda:None;battle.ended=True;battle.winner=1;battle.experience_events=[]
  for mon in battle.rosters[0]:mon['hp']=0
  await self.w.resolve_battle(battle);self.assertEqual(self.a.state['map'],self.c.data['homes']['Kanto']);self.assertEqual(self.db.load(self.a.id)['warpReturns'],[])
 async def test_center_and_gym_ice_tiles_cannot_start_wild_encounters(self):
  m=self.c.maps[self.map];m['behavior'][self.a.state['y']*m['width']+self.a.state['x']]=8;before=copy.deepcopy(self.a.state)
  with self.assertRaisesRegex(RequestError,'Centers and Gyms'):await self.w.dispatch(self.a,{'op':'encounter'})
  self.assertEqual(self.a.state,before);self.assertIsNone(self.a.battle)
  del self.c.data['centers'][self.map]
  with self.assertRaisesRegex(RequestError,'Centers and Gyms'):await self.w.dispatch(self.a,{'op':'encounter'})
  self.assertIsNone(self.a.battle)

if __name__=='__main__':unittest.main()
