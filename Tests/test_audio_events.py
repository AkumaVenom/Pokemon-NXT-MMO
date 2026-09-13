"""Authoritative audio contracts using real isolated database transactions.

These check confirmation timing, rejected actions, rollback, event identity,
perspective and the current gameplay hooks. They do not certify audible output.
"""
from __future__ import annotations
import asyncio,copy,dataclasses,json,random,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'))
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.world import World
from nxt.security import RequestError


class AudioEventTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):cls.c=Content(ROOT/'Server/data/world.json')
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();path=Path(self.tmp.name)/'config.ini';path.write_text((ROOT/'Server/config.ini').read_text())
  self.s=Settings.load(path);self.s.config.set('database','backend','sqlite');self.s=dataclasses.replace(self.s,encounter_chance=0)
  self.db=Store(self.s);self.db.acquire_lease();self.w=World(self.c,self.db,self.s);self.old_rng=self.c.rng;self.c.rng=random.Random(720)
  self.a=await self.player('AudioAlice');self.b=await self.player('AudioBobby')
  self.drain(self.a);self.drain(self.b)
 async def asyncTearDown(self):
  self.w.players.clear();self.c.rng=self.old_rng;self.db.close();self.tmp.cleanup()
 async def player(self,name):
  state=self.w.initial(name,'Kanto','fr_4',0);uid=self.db.create(name,'test-hash-only',state)
  return await self.w.join(uid,name,state,asyncio.Queue(maxsize=2048))
 def drain(self,p):
  packets=[]
  while not p.queue.empty():packets.append(p.queue.get_nowait())
  return packets
 def field_events(self,packets):return [e for p in packets if p['type']=='audio' for e in p['events']]
 def battle_events(self,packets):return [e for p in packets if p['type']=='battle' for e in p['battle']['audio']['events']]
 def cues(self,events):return [e['cue'] for e in events]
 async def wild(self,species='fr_1',level=5):
  await self.w.start_wild(self.a,(species,level));return self.w.battles[self.a.battle]
 async def duel(self):
  await self.w.dispatch(self.a,{'op':'invite','kind':'challenge','target':self.b.id});key=next(iter(self.w.invites))
  await self.w.dispatch(self.b,{'op':'invite.answer','id':key,'accept':True});return self.w.battles[self.a.battle]
 async def trade(self):
  await self.w.dispatch(self.a,{'op':'invite','kind':'trade','target':self.b.id});key=next(iter(self.w.invites))
  await self.w.dispatch(self.b,{'op':'invite.answer','id':key,'accept':True});return self.w.trades[self.a.trade]
 async def finish_trade(self,t):
  for p in (self.a,self.b):await self.w.dispatch(p,{'op':'trade','id':t['id'],'action':'lock','revision':t['revision']})
  for p in (self.a,self.b):await self.w.dispatch(p,{'op':'trade','id':t['id'],'action':'confirm','revision':t['revision'],'digest':self.w.trade_digest(t)})
 def deterministic_attacks(self,b,move=52,enemy_move=150):
  b.mon(0)['moves']=[{'id':move,'pp':20}];b.mon(1)['moves']=[{'id':enemy_move,'pp':20}]
  self.c.rng.randrange=lambda n:1
  self.c.rng.random=lambda:.5
  self.c.rng.randint=lambda a,z:z

 async def test_purchase_audio_follows_successful_transaction_and_is_private(self):
  actual=self.db.save_many
  def save(records):
   self.assertFalse(any(p['type']=='audio' for p in self.a.queue._queue));return actual(records)
  with patch.object(self.db,'save_many',side_effect=save):await self.w.dispatch(self.a,{'op':'buy','item':'potion','quantity':1})
  packets=self.drain(self.a);events=self.field_events(packets)
  self.assertEqual(self.cues(events),['purchase']);self.assertEqual(events[0]['item'],'potion');self.assertEqual(events[0]['quantity'],1)
  self.assertLess(next(i for i,p in enumerate(packets) if p['type']=='state'),next(i for i,p in enumerate(packets) if p['type']=='audio'))
  self.assertEqual(self.db.load(self.a.id),self.a.state);self.assertFalse(self.field_events(self.drain(self.b)))

 async def test_rejected_and_failed_purchases_emit_no_success(self):
  before=copy.deepcopy(self.a.state)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'buy','item':'ultraball','quantity':99})
  self.assertFalse(self.field_events(self.drain(self.a)))
  with patch.object(self.db,'save_many',side_effect=RuntimeError('injected save failure')):
   with self.assertLogs('nxt.world',level='ERROR'),self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'buy','item':'potion','quantity':1})
  self.assertEqual(self.a.state,before);self.assertFalse(self.field_events(self.drain(self.a)))

 async def test_event_ids_are_unique_per_session_and_survive_json(self):
  await self.w.dispatch(self.a,{'op':'save'});await self.w.dispatch(self.a,{'op':'save'});await self.w.dispatch(self.b,{'op':'save'})
  packets=self.drain(self.a)+self.drain(self.b);events=self.field_events(json.loads(json.dumps(packets)))
  self.assertEqual(len(events),3);self.assertEqual(len({e['id'] for e in events}),3)
  for e in events:self.assertEqual(e['source'],'kanto')
  self.assertNotIn('audio_session',self.db.load(self.a.id));self.assertNotIn('audio_sequence',self.db.load(self.a.id))

 async def test_failed_save_heal_and_item_do_not_emit_confirmation(self):
  self.a.state['creatures'][0]['hp']=1
  for op in ({'op':'save'},{'op':'heal'},{'op':'use','item':'potion','uid':self.a.state['party'][0]}):
   with patch.object(self.db,'save_many',side_effect=RuntimeError('injected save failure')):
    if op['op']=='save':
     with self.assertRaises(RuntimeError):await self.w.dispatch(self.a,op)
    else:
     with self.assertLogs('nxt.world',level='ERROR'),self.assertRaises(RequestError):await self.w.dispatch(self.a,op)
   self.assertFalse(self.field_events(self.drain(self.a)))

 async def test_field_heal_item_and_follower_change_have_semantic_cues(self):
  self.a.state['creatures'][0]['hp']=1;await self.w.dispatch(self.a,{'op':'use','item':'potion','uid':self.a.state['party'][0]})
  self.assertEqual(self.cues(self.field_events(self.drain(self.a))),['item'])
  await self.w.heal(self.a,at_nurse=True);events=self.field_events(self.drain(self.a));self.assertEqual(self.cues(events),['heal']);self.assertTrue(events[0]['atNurse'])
  mon=self.c.new_mon('fr_7',5,self.a.username);self.a.state['creatures'].append(mon)
  await self.w.dispatch(self.a,{'op':'party','party':[mon['uid'],self.a.state['party'][0]]})
  events=self.field_events(self.drain(self.a));self.assertEqual(self.cues(events),['party_changed']);self.assertTrue(events[0]['leadChanged']);self.assertEqual(events[0]['species'],'fr_7')
  await self.w.dispatch(self.a,{'op':'party','party':list(self.a.state['party'])});self.assertFalse(self.field_events(self.drain(self.a)))

 async def test_battle_initial_source_and_cry_species_are_independent(self):
  self.w.relocate(self.a,'johto_3_0');self.drain(self.a);self.a.state['creatures'][0]['shiny']=True
  b=await self.wild();packet=next(p['battle'] for p in self.drain(self.a) if p['type']=='battle');events=packet['audio']['events']
  self.assertEqual(packet['source'],'johto');self.assertEqual(self.cues(events),['battle_start','sendout','sendout','shiny'])
  self.assertEqual([e['side'] for e in events if e['cue']=='sendout'],['opponent','you'])
  self.assertEqual(events[-1]['species'],'fr_4');self.assertEqual(self.c.species[events[-1]['species']]['source'],'kanto')
  self.assertEqual(packet['audio'],b.view(0)['audio'])

 async def test_waiting_resends_stable_ids_and_rejected_duplicate_is_silent(self):
  b=await self.duel();initial=b.view(0)['audio'];self.drain(self.a);self.drain(self.b)
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'attack','slot':0})
  waiting=next(p['battle'] for p in self.drain(self.a) if p['type']=='battle')
  self.assertTrue(waiting['waiting']);self.assertEqual(waiting['audio'],initial)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'attack','slot':0})
  self.assertFalse(self.drain(self.a));self.assertEqual(b.view(0)['audio'],initial)

 async def test_capture_audio_waits_for_commit_and_has_stable_ordered_result(self):
  b=await self.wild('fr_129',2);self.drain(self.a);self.c.rng.random=lambda:0.0;actual=self.db.save_many
  def save(records):
   self.assertFalse(any(p['type'] in ('audio','battle') for p in self.a.queue._queue));return actual(records)
  with patch.object(self.db,'save_many',side_effect=save):await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'capture','item':'pokeball'})
  events=self.battle_events(self.drain(self.a));self.assertEqual(self.cues(events),['capture_throw','capture_success','battle_end']);self.assertEqual(events[-1]['result'],'caught')
  self.assertEqual(len(self.db.load(self.a.id)['creatures']),2);self.assertEqual(events,b.view(0)['audio']['events'])

 async def test_capture_rollback_discards_throw_success_and_reward_events(self):
  before=copy.deepcopy(self.a.state);b=await self.wild('fr_129',2);self.drain(self.a);self.c.rng.random=lambda:0.0
  with patch.object(self.db,'save_many',side_effect=RuntimeError('injected capture rollback')):
   with self.assertLogs('nxt.world',level='ERROR'):await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'capture','item':'pokeball'})
  events=self.battle_events(self.drain(self.a));self.assertEqual(self.cues(events),['abort']);self.assertEqual(events[0]['reason'],'save_failed');self.assertEqual(self.a.state,before);self.assertEqual(self.db.load(self.a.id),before)

 async def test_full_collection_rejection_does_not_emit_capture_audio(self):
  self.w.s=dataclasses.replace(self.s,max_owned=1);b=await self.wild();self.drain(self.a)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'capture','item':'pokeball'})
  self.assertFalse(self.drain(self.a));self.assertEqual(b.audio_revision,0)

 async def test_failed_capture_then_attack_are_in_server_resolution_order(self):
  b=await self.wild('fr_1',50);self.drain(self.a);self.c.rng.random=lambda:.999
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'capture','item':'pokeball'})
  cues=self.cues(self.battle_events(self.drain(self.a)));self.assertEqual(cues[:2],['capture_throw','capture_fail']);self.assertIn('move',cues[2:]);self.assertNotIn('capture_success',cues)

 async def test_moves_report_move_type_and_actual_effectiveness(self):
  b=await self.wild();self.deterministic_attacks(b);self.drain(self.a)
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'attack','slot':0})
  events=self.battle_events(self.drain(self.a));move=next(e for e in events if e['cue']=='move' and e['side']=='you');hit=next(e for e in events if e['cue']=='hit' and e['side']=='opponent')
  self.assertEqual(move['move'],52);self.assertEqual(move['moveType'],10);self.assertEqual(hit['effectiveness'],2);self.assertFalse(hit['critical']);self.assertGreater(hit['damage'],0)
  self.assertLess(events.index(move),events.index(hit))

 async def test_immune_move_has_no_hit_cue(self):
  b=await self.wild('fr_74');self.deterministic_attacks(b,move=84);self.drain(self.a)
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'attack','slot':0})
  events=self.battle_events(self.drain(self.a));self.assertIn('no_effect',self.cues(events));self.assertFalse(any(e['cue']=='hit' and e['side']=='opponent' for e in events))

 async def test_stat_status_and_recovery_audio_match_applied_effects(self):
  b=await self.wild();self.deterministic_attacks(b,move=45);self.drain(self.a)
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'attack','slot':0})
  self.assertIn('stat_down',self.cues(self.battle_events(self.drain(self.a))));self.assertEqual(b.tiers(b.mon(1))[1],-1)
  b.mon(0)['moves']=[{'id':79,'pp':20}]
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'attack','slot':0})
  events=self.battle_events(self.drain(self.a));self.assertTrue(any(e['cue']=='status' and e['status']=='sleep' for e in events));self.assertEqual(b.mon(1)['status'],'sleep')
  b.mon(0)['hp']=1
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'item','item':'potion'})
  events=self.battle_events(self.drain(self.a));self.assertTrue(any(e['cue']=='recover' and e.get('item')=='potion' for e in events));self.assertGreater(b.mon(0)['hp'],1)

 async def test_faint_rewards_and_level_up_only_after_commit(self):
  b=await self.wild('fr_1',50);self.deterministic_attacks(b);b.mon(1)['hp']=1;b.mon(1)['status']='sleep';b.mon(1)['sleep']=10;self.drain(self.a)
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'attack','slot':0})
  events=self.battle_events(self.drain(self.a));cues=self.cues(events)
  for cue in ('faint','experience','level_up','battle_end'):self.assertIn(cue,cues)
  self.assertLess(cues.index('faint'),cues.index('experience'));self.assertLess(cues.index('experience'),cues.index('level_up'));self.assertEqual(events[-1]['result'],'won')
  self.assertGreater(self.db.load(self.a.id)['creatures'][0]['level'],5)

 async def test_duel_results_are_viewer_relative_and_do_not_spend_items(self):
  before_a=copy.deepcopy(self.a.state);before_b=copy.deepcopy(self.b.state);b=await self.duel();self.drain(self.a);self.drain(self.b)
  await self.w.dispatch(self.a,{'op':'battle','id':b.id,'action':'run'})
  a=self.battle_events(self.drain(self.a));other=self.battle_events(self.drain(self.b));self.assertEqual(a[-1]['result'],'lost');self.assertEqual(other[-1]['result'],'won')
  self.assertEqual(a[0]['side'],'you');self.assertEqual(other[0]['side'],'opponent');self.assertEqual([e['id'] for e in a],[e['id'] for e in other]);self.assertEqual(self.a.state,before_a);self.assertEqual(self.b.state,before_b)

 async def test_disconnect_result_does_not_replay_prior_turn(self):
  b=await self.duel();old={e['id'] for e in b.view(0)['audio']['events']};self.drain(self.a);self.drain(self.b)
  await self.w.leave(self.b);events=self.battle_events(self.drain(self.a));self.assertEqual(self.cues(events),['battle_end']);self.assertEqual(events[0]['result'],'won');self.assertFalse(old.intersection(e['id'] for e in events))

 async def test_trade_completion_emits_only_after_atomic_commit_for_both_owners(self):
  t=await self.trade();self.drain(self.a);self.drain(self.b);actual=self.db.trade
  def commit(*args):
   for p in (self.a,self.b):self.assertFalse(any(packet['type']=='audio' for packet in p.queue._queue))
   return actual(*args)
  with patch.object(self.db,'trade',side_effect=commit):await self.finish_trade(t)
  for p in (self.a,self.b):
   packets=self.drain(p);events=self.field_events(packets);self.assertEqual(self.cues(events),['trade_complete']);self.assertEqual(events[0]['trade'],t['id']);self.assertEqual(self.db.load(p.id),p.state)

 async def test_trade_cancel_and_database_rollback_emit_no_completion(self):
  t=await self.trade();self.drain(self.a);self.drain(self.b)
  with patch.object(self.db,'trade',side_effect=RuntimeError('injected trade rollback')):
   with self.assertLogs('nxt.world',level='ERROR'):await self.finish_trade(t)
  for p in (self.a,self.b):self.assertFalse(self.field_events(self.drain(p)))
  t=await self.trade();await self.w.dispatch(self.a,{'op':'trade','id':t['id'],'action':'cancel'})
  for p in (self.a,self.b):self.assertFalse(self.field_events(self.drain(p)))

 async def test_movement_rejections_distinguish_bumps_from_rate_and_replays(self):
  await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':'right'});accepted=next(p for p in self.drain(self.a) if p['type']=='move')
  self.assertTrue(accepted['accepted']);self.assertEqual(accepted['movement'],'step');self.assertIsInstance(accepted['terrain'],int)
  await self.w.dispatch(self.a,{'op':'move','seq':2,'direction':'right'});rate=next(p for p in self.drain(self.a) if p['type']=='move');self.assertEqual(rate['reason'],'rate')
  await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':'right'});stale=next(p for p in self.drain(self.a) if p['type']=='move');self.assertEqual(stale['reason'],'stale')
  self.a.state.update(x=2,y=2);self.a.last_move=0
  await self.w.dispatch(self.a,{'op':'move','seq':3,'direction':'left'});blocked=next(p for p in self.drain(self.a) if p['type']=='move');self.assertFalse(blocked['accepted']);self.assertEqual(blocked['reason'],'blocked')

 async def test_map_transition_and_surf_metadata_are_authoritative(self):
  await self.w.dispatch(self.a,{'op':'travel','map':'johto_3_0'});m=next(p for p in self.drain(self.a) if p['type']=='map');self.assertEqual(m['transition'],'travel')
  await self.w.dispatch(self.a,{'op':'surf'});events=self.field_events(self.drain(self.a));self.assertEqual(self.cues(events),['surf']);self.assertEqual(events[0]['source'],'johto');self.assertTrue(events[0]['enabled'])
  await self.w.dispatch(self.a,{'op':'unstuck'});m=next(p for p in self.drain(self.a) if p['type']=='map');self.assertEqual(m['transition'],'home');self.assertFalse(m['entity']['surf']);self.assertFalse(self.a.state['surf'])


if __name__=='__main__':unittest.main()
