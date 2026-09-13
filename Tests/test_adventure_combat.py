"""Trainer-party turn and EXP event contracts for the adventure release."""
from pathlib import Path
import random,sys,time,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'))
from nxt.content import Content
from nxt.combat import Battle
from nxt.security import RequestError

class AdventureCombatTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=Content(ROOT/'Server/data/world.json')
 def setUp(self):
  self.old_rng=self.c.rng;self.c.rng=random.Random(43)
  self.team=[self.c.new_mon('fr_4',25,'Trainer'),self.c.new_mon('fr_7',25,'Trainer')]
  for m in self.team:m['moves']=[{'id':129,'pp':20}]
 def tearDown(self):self.c.rng=self.old_rng
 def battle(self,kind='trainer',count=2):
  enemies=[self.c.new_mon('fr_19',2) for _ in range(count)]
  for m in enemies:m['hp']=1;m['moves']=[{'id':33,'pp':35}]
  return Battle(self.c,kind,[1,2 if kind=='duel' else None],['Trainer','Opponent'],[self.team,enemies],[{'pokeball':10},{}])
 def attack(self,b):
  b.choose(0,{'action':'attack','slot':0})
  if b.kind=='duel':b.choose(1,{'action':'attack','slot':0})
  b.resolve()
 def test_each_defeated_trainer_pokemon_emits_one_experience_event(self):
  b=self.battle();self.attack(b)
  self.assertFalse(b.ended);self.assertEqual(len(b.experience_events),1)
  self.assertEqual(b.experience_events[0]['participants'],[self.team[0]['uid']])
  self.attack(b);self.assertTrue(b.ended);self.assertEqual(len(b.experience_events),1)
  self.assertEqual(len(b.experience_awarded),2)
 def test_switch_participants_are_tracked_per_opposing_pokemon(self):
  b=self.battle();b.choose(0,{'action':'switch','uid':self.team[1]['uid']});b.resolve();self.attack(b)
  self.assertEqual(set(b.experience_events[0]['participants']),{m['uid'] for m in self.team})
  self.attack(b);self.assertEqual(b.experience_events[0]['participants'],[self.team[1]['uid']])
 def test_trainer_cannot_be_fled_or_captured(self):
  b=self.battle()
  for action in ({'action':'run'},{'action':'capture','item':'pokeball'}):
   with self.assertRaises(RequestError):b.choose(0,action)
  self.assertFalse(b.view(0)['canRun']);self.assertEqual(b.choice,{})
 def test_idle_trainer_timeout_forfeits_player_even_against_faster_opponent(self):
  b=self.battle();b.rosters[1][0]['level']=100;b.deadline=time.monotonic()-1
  self.assertTrue(b.timeout());b.resolve();self.assertTrue(b.ended);self.assertEqual(b.winner,1);self.assertEqual(b.experience_events,[])
 def test_duel_never_generates_account_experience(self):
  b=self.battle('duel',1);self.attack(b);self.assertTrue(b.ended);self.assertEqual(b.experience_events,[])
 def test_catching_a_pokemon_does_not_generate_defeat_experience(self):
  b=self.battle('wild',1);b.mon(1)['species']='fr_129';self.c.rng.random=lambda:0
  b.choose(0,{'action':'capture','item':'pokeball'});b.resolve();self.assertIsNotNone(b.caught);self.assertEqual(b.experience_events,[])
 def test_switching_clears_temporary_stat_changes_and_leech_seed(self):
  b=self.battle();lead=b.mon(0);b.tiers(lead)[1]=6;b.seeded.add(lead['uid'])
  b.choose(0,{'action':'switch','uid':self.team[1]['uid']});b.resolve()
  b.choose(0,{'action':'switch','uid':self.team[0]['uid']});b.resolve()
  self.assertEqual(b.tiers(b.mon(0))[1],0);self.assertNotIn(lead['uid'],b.seeded)

if __name__=='__main__':unittest.main()
