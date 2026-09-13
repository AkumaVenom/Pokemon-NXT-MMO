"""Owner-only growth transforms, durable choices and ROM-condition validation."""
from __future__ import annotations
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
from nxt.content import Content
from nxt.growth import Growth
from nxt.security import RequestError
from nxt.config import Settings
from nxt.store import Store

class GrowthTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.base=Content(ROOT/'Server/data/world.json')
 def setUp(self):
  self.c=copy.copy(self.base);self.c.data=dict(self.base.data);self.c.species=dict(self.base.species);self.c.items=copy.deepcopy(self.base.items);self.c.growth=Growth(self.c)
  self.c.data['adventureRom']={'evolutions':{
   'fr_1':[{'method':'level','level':16,'target':'fr_2'}],
   'fr_2':[{'method':'level','level':32,'target':'fr_3'}],
   'fr_63':[{'method':'level','level':16,'target':'fr_64'}],
   'fr_64':[{'method':'trade','target':'fr_65'}],
   'fr_25':[{'method':'stone','item':'thunderstone','target':'fr_26'}]}}
  self.c.items['thunderstone']={'name':'Thunder Stone','price':2100,'evolutionStone':True}
  self.g=self.c.growth
 def state(self,key='fr_1',level=5):
  m=self.c.new_mon(key,level,'Akumavenom');return {'format':1,'revision':3,'creatures':[m],'party':[m['uid']],'items':{'thunderstone':1},'money':3000,'home':'Johto','map':'johto_3_0','x':7,'y':8}
 def level_to(self,m,level):return self.c.gain_xp(m,self.c.xp(level,self.c.species[m['species']]['growth'])-m['exp'])
 def pending(self):
  s=self.state(level=10);self.level_to(s['creatures'][0],25);return s
 def test_new_mon_has_distinct_ids_and_independent_growth_containers(self):
  a=self.state()['creatures'][0];b=self.state()['creatures'][0];a['pendingLearn'].append({'move':33});self.assertNotEqual(a['uid'],b['uid']);self.assertEqual(b['pendingLearn'],[])
 def test_all_starters_keep_species_and_original_moves_through_growth(self):
  for key in self.c.data['starters']:
   with self.subTest(starter=key):
    m=self.c.new_mon(key,10);old=copy.deepcopy(m['moves']);self.level_to(m,50)
    self.assertEqual(m['species'],key);self.assertEqual(m['moves'][:len(old)],old);self.assertLessEqual(len(m['moves']),4)
    ids=[v['move'] for v in m['pendingLearn']];self.assertEqual(len(ids),len(set(ids)));self.assertFalse(set(ids)&{v['id'] for v in m['moves']})
 def test_multi_level_overflow_preserves_every_existing_move_and_pp(self):
  s=self.state(level=10);m=s['creatures'][0];m['moves'][0]['pp']=1;before=copy.deepcopy(m['moves']);self.assertEqual(len(before),4)
  self.level_to(m,25);self.assertEqual(m['moves'],before);self.assertEqual([v['move'] for v in m['pendingLearn']],[77,79,75,230]);self.assertEqual([v['level'] for v in m['pendingLearn']],[15,15,20,25])
 def test_free_slots_learn_automatically_without_replacing(self):
  m=self.state()['creatures'][0];old=[v['id'] for v in m['moves']];self.level_to(m,10);self.assertEqual([v['id'] for v in m['moves']],old+[73,22]);self.assertEqual(m['pendingLearn'],[])
 def test_replace_is_explicit_and_changes_only_chosen_slot(self):
  state=self.pending();before=copy.deepcopy(state);m=state['creatures'][0];move=m['pendingLearn'][0]['move'];changed=self.g.learn(state,m['uid'],move,2);cm=changed['creatures'][0]
  self.assertEqual(state,before);self.assertEqual(cm['moves'][2],{'id':move,'pp':self.c.moves[str(move)]['pp']});self.assertEqual([cm['moves'][i] for i in (0,1,3)],[m['moves'][i] for i in (0,1,3)]);self.assertEqual(len(cm['moves']),4);self.assertEqual(len(cm['pendingLearn']),3)
 def test_decline_removes_one_choice_without_changing_moves(self):
  s=self.pending();m=s['creatures'][0];out=self.g.learn(s,m['uid'],m['pendingLearn'][0]['move'],None);self.assertEqual(out['creatures'][0]['moves'],m['moves']);self.assertEqual(len(out['creatures'][0]['pendingLearn']),3)
 def test_replay_wrong_queue_entry_and_fabricated_move_rejected(self):
  s=self.pending();m=s['creatures'][0];first=m['pendingLearn'][0]['move'];done=self.g.learn(s,m['uid'],first,0)
  for state,move in ((done,first),(s,230),(s,9999),(s,True)):
   with self.subTest(move=move),self.assertRaises(RequestError):self.g.learn(state,m['uid'],move,0)
 def test_invalid_slots_never_mutate_source(self):
  s=self.pending();before=copy.deepcopy(s);m=s['creatures'][0]
  for slot in (-1,4,True,'0',0.5,{},[]):
   with self.subTest(slot=slot),self.assertRaises(RequestError):self.g.learn(s,m['uid'],m['pendingLearn'][0]['move'],slot)
   self.assertEqual(s,before)
 def test_all_growth_actions_reject_another_owners_uid(self):
  a=self.pending();b=self.state();uid=b['creatures'][0]['uid'];before=copy.deepcopy(a)
  for action in (lambda:self.g.learn(a,uid,77,0),lambda:self.g.evolve(a,uid,'fr_2'),lambda:self.g.defer_evolution(a,uid,'fr_2'),lambda:self.g.resume_evolution(a,uid,'fr_2')):
   with self.assertRaises(RequestError):action()
   self.assertEqual(a,before)
 def test_learnset_must_authorize_saved_pending_entry(self):
  s=self.pending();m=s['creatures'][0];m['pendingLearn'][0]['level']=1
  with self.assertRaises(RequestError):self.g.learn(s,m['uid'],77,0)
 def test_level_evolution_preserves_identity_exp_damage_and_moves(self):
  s=self.state(level=16);m=s['creatures'][0];m['hp']-=4;old=copy.deepcopy(m);result=self.g.evolve(s,m['uid'],'fr_2');new=result['creatures'][0]
  for key in ('uid','level','exp','ivs','nature','originalTrainer','shiny','status','sleep'):self.assertEqual(new[key],old[key])
  self.assertEqual(new['species'],'fr_2');self.assertEqual(new['moves'],old['moves']);self.assertEqual(self.c.stats(new)[0]-new['hp'],4);self.assertEqual(new['evolutionHistory'],['fr_1']);self.assertEqual(s['creatures'][0],old)
 def test_level_and_target_cannot_be_forged(self):
  for level,target in ((5,'fr_2'),(16,'fr_3'),(16,'fr_4'),(16,{})):
   s=self.state(level=level)
   with self.subTest(level=level,target=target),self.assertRaises(RequestError):self.g.evolve(s,s['party'][0],target)
 def test_evolution_choices_can_be_deferred_and_resumed_after_reload(self):
  s=self.state(level=16);uid=s['party'][0];deferred=self.g.defer_evolution(s,uid,'fr_2');reloaded=json.loads(json.dumps(deferred));self.assertTrue(self.g.options(reloaded['creatures'][0])[0]['deferred'])
  with self.assertRaises(RequestError):self.g.evolve(reloaded,uid,'fr_2')
  resumed=self.g.resume_evolution(reloaded,uid,'fr_2');self.assertEqual(self.g.evolve(resumed,uid,'fr_2')['creatures'][0]['species'],'fr_2')
 def test_stone_is_required_consumed_exactly_once_and_replay_rejected(self):
  s=self.state('fr_25',10);uid=s['party'][0];result=self.g.evolve(s,uid,'fr_26');self.assertEqual(result['items']['thunderstone'],0);self.assertEqual(s['items']['thunderstone'],1)
  with self.assertRaises(RequestError):self.g.evolve(result,uid,'fr_26')
  s['items']['thunderstone']=0
  with self.assertRaises(RequestError):self.g.evolve(s,uid,'fr_26')
 def test_trade_evolution_requires_durable_server_trade_trigger(self):
  s=self.state('fr_64',20);uid=s['party'][0]
  with self.assertRaises(RequestError):self.g.evolve(s,uid,'fr_65')
  transferred=copy.deepcopy(s);self.g.mark_trade(transferred['creatures'][0]);self.g.mark_trade(transferred['creatures'][0]);self.assertEqual(len(transferred['creatures'][0]['pendingEvolution']),1)
  loaded=json.loads(json.dumps(transferred));self.assertEqual(self.g.evolve(loaded,uid,'fr_65')['creatures'][0]['species'],'fr_65');self.assertEqual(s['creatures'][0]['pendingEvolution'],[])
 def test_fainted_creature_stays_fainted_after_growth_and_evolution(self):
  s=self.state(level=10);m=s['creatures'][0];m['hp']=0;self.level_to(m,16);self.assertEqual(m['hp'],0);self.assertEqual(self.g.evolve(s,m['uid'],'fr_2')['creatures'][0]['hp'],0)
 def test_pending_original_species_moves_remain_earned_after_evolution(self):
  s=self.pending();m=s['creatures'][0];evolved=self.g.evolve(s,m['uid'],'fr_2');result=self.g.learn(evolved,m['uid'],77,0);self.assertEqual(result['creatures'][0]['moves'][0]['id'],77)
 def test_evolved_species_current_level_move_is_queued_without_replacement(self):
  self.c.species['fr_2']=copy.deepcopy(self.c.species['fr_2']);self.c.species['fr_2']['learnset'].append([16,52]);s=self.state(level=16);m=s['creatures'][0];result=self.g.evolve(s,m['uid'],'fr_2');self.assertEqual(result['creatures'][0]['moves'],m['moves']);self.assertEqual(result['creatures'][0]['pendingLearn'],[{'move':52,'species':'fr_2','level':16}])
 def test_unsupported_rom_conditions_and_mismatched_growth_are_not_guessed(self):
  self.c.data['adventureRom']['evolutions']['fr_1']=[{'method':'friendship','target':'fr_2'},{'method':'level_attack_greater','level':1,'target':'fr_3'}];s=self.state(level=100);self.assertEqual(self.g.options(s['creatures'][0]),[])
  self.c.data['adventureRom']['evolutions']['fr_1']=[{'method':'level','level':1,'target':'fr_2'}];self.c.species['fr_2']=dict(self.c.species['fr_2'],growth=5)
  with self.assertRaises(RequestError):self.g.evolve(s,s['party'][0],'fr_2')
 def test_old_save_migration_is_additive_idempotent_and_does_not_relearn(self):
  s=self.state(level=50);m=s['creatures'][0]
  for key in ('pendingLearn','pendingEvolution','evolutionDeferred','evolutionHistory'):m.pop(key)
  original=copy.deepcopy(s);migrated=self.g.migrate(s);self.assertEqual(s,original);self.assertEqual(self.g.migrate(migrated),migrated)
  for key,value in original['creatures'][0].items():self.assertEqual(migrated['creatures'][0][key],value)
  self.assertEqual(migrated['creatures'][0]['pendingLearn'],[])
 def test_growth_choices_are_owner_only_in_public_payload(self):
  m=self.pending()['creatures'][0];private=self.c.public_mon(m);public=self.c.public_mon(m,False);self.assertTrue(private['pendingLearn']);self.assertIn('evolutions',private)
  for key in ('pendingLearn','evolutions','exp','moves','evolutionHistory'):self.assertNotIn(key,public)
 def test_growth_and_pending_choices_survive_database_close_reopen(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'config.ini';path.write_bytes((ROOT/'Build/config_templates/Server/config.ini').read_bytes());settings=Settings.load(path);settings.config.set('database','backend','sqlite');db=Store(settings);db.acquire_lease()
   original=self.pending();other=self.state('fr_4');aid=db.create('Akumavenom','test-hash',original);bid=db.create('Spidermight','test-hash',other)
   evolved=self.g.evolve(original,original['party'][0],'fr_2');learned=self.g.learn(evolved,evolved['party'][0],77,0);learned['revision']+=1;db.save_many([(aid,learned)]);db.close()
   reopened=Store(settings)
   try:self.assertEqual(reopened.load(aid),learned);self.assertEqual(reopened.load(bid),other)
   finally:reopened.close()
 def test_experience_caps_at_maximum_without_duplicate_move_choices(self):
  s=self.pending();m=s['creatures'][0];self.c.gain_xp(m,10**12);self.assertEqual(m['level'],100);self.assertEqual(m['exp'],self.c.xp(100,self.c.species[m['species']]['growth']));pending=copy.deepcopy(m['pendingLearn']);self.c.gain_xp(m,100);self.assertEqual(m['pendingLearn'],pending);self.assertEqual(len(m['moves']),4)

if __name__=='__main__':unittest.main()
