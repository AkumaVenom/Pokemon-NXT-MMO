"""Regression coverage for ROM-backed Gen-III battle mechanics."""
from __future__ import annotations
import copy, json, random, sys, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'))
from nxt.combat import Battle, MIMIC_BANNED
from nxt.ai_trainers import AutonomousTrainers
from nxt.content import Content
from nxt.varieties import Varieties

FIRERED_SHA='729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059'
SIGMA_SHA='62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64'

class BattleRomMechanicTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.base=Content(ROOT/'Server/data/world.json')
  cls.audit=json.loads((ROOT/'Server/data/battle_mechanics.json').read_text(encoding='utf-8'))

 def content(self,seed=680):
  c=copy.copy(self.base);c.moves=dict(self.base.moves);c.species=dict(self.base.species);c.rng=random.Random(seed);c.varieties=Varieties(c);return c

 def battle(self,move=33,enemy_move=150,kind='duel',terrain='plain',level=50,enemy_level=50,extra0=None,extra1=None):
  c=self.content(move+enemy_move+level+enemy_level)
  a=c.new_mon('fr_4',level);b=c.new_mon('fr_7',enemy_level)
  a['heldItemId']=b['heldItemId']=0
  a['moves']=[{'id':move,'pp':c.moves[str(move)]['pp']}]+copy.deepcopy(extra0 or [])
  b['moves']=[{'id':enemy_move,'pp':c.moves[str(enemy_move)]['pp']}]+copy.deepcopy(extra1 or [])
  # A roomy deterministic combat fixture prevents ordinary damage from ending
  # most tests while leaving move-specific fixed/OHKO behavior intact.
  auid,buid=a['uid'],b['uid']
  c.stats=lambda m:[2000,120,120,140 if m['uid']==auid else 80,120,120]
  a['hp']=b['hp']=2000
  return c,Battle(c,kind,[1,2],['Trainer','Opponent'],[[a],[b]],[{},{}],terrain=terrain)

 def execute(self,b,side,mid):
  return b._execute_move(side,mid,b.c.moves[str(mid)],{'action':'attack','slot':0},0)

 def test_published_audit_is_hash_pinned_and_complete(self):
  a=self.audit
  self.assertEqual(a['sources']['kanto']['sha256'],FIRERED_SHA)
  self.assertEqual(a['sources']['johto']['sha256'],SIGMA_SHA)
  self.assertEqual(a['audit']['moveRecords'],361)
  self.assertEqual(a['audit']['effectIds'],198)
  self.assertEqual(a['audit']['speciesRecords'],877)
  self.assertEqual(a['audit']['unknownSigmaWeights'],491)
  self.assertEqual(len(a['moves']),361);self.assertEqual(len(a['species']),877)
  self.assertEqual({int(k) for k in a['moves'] if int(k)<1024},set(range(1,355)))
  self.assertEqual({int(k) for k in a['moves'] if int(k)>=1024},{1207,1234,1261,1318,1319,1321,1370})
  for mid,row in a['moves'].items():
   self.assertIn(row['source'],('kanto','johto'));self.assertEqual(len(row['rawHex']),24)
   self.assertEqual(row['sourceSha256'],a['sources'][row['source']]['sha256'])
   runtime=self.base.moves[mid]
   self.assertEqual(runtime['flags'],row['flags'])
   self.assertEqual(runtime['battleEffectName'],row['effectName'])
   self.assertEqual(runtime['battleProvenance']['sha256'],row['sourceSha256'])
   self.assertEqual(runtime['battleProvenance']['sourceMoveId'],row['sourceMoveId'])

 def test_autonomous_attack_selection_uses_transformed_move_view(self):
  # Ditto has one persistent move (Transform), while the transformed battle
  # view can expose all four moves of the opponent. The autonomous selector
  # must index the Battle override, not the shorter saved creature move list.
  c=self.content(681);ditto=c.new_mon('fr_132',30);foe=c.new_mon('fr_6',30)
  self.assertEqual([q['id'] for q in ditto['moves']],[144])
  self.assertEqual(len(foe['moves']),4)
  b=Battle(c,'wild',[1,None],['NXTestBot','Wild foe'],[[ditto],[foe]],[{},{}])
  ai=object.__new__(AutonomousTrainers);ai.c=c
  b._transform(0)
  self.assertEqual(len(b.mon(0)['moves']),1)
  self.assertEqual(len(b._moves(b.mon(0))),4)
  self.assertEqual(b.usable(b.mon(0)),[0,1,2,3])
  slot=ai._best_attack(b,0)
  self.assertIn(slot,b.usable(b.mon(0)))
  b.choose(0,{'action':'attack','slot':slot})
  self.assertEqual(b.choice[0]['slot'],slot)

 def test_every_published_move_can_resolve_a_complete_turn(self):
  for key in sorted(self.base.moves,key=int):
   mid=int(key)
   with self.subTest(move=mid,name=self.base.moves[key]['name']):
    c,b=self.battle(mid)
    self.assertEqual(b.usable(b.mon(0)),[0])
    b.choose(0,{'action':'attack','slot':0});b.choose(1,{'action':'attack','slot':0})
    b.resolve()
    self.assertGreaterEqual(b.turn,1)
    self.assertTrue(any(e['cue']=='move' and e.get('move')==mid for e in b.audio_events) or b.ended)

 def test_psywave_uses_firered_rejection_steps(self):
  c,b=self.battle(149);seen=[]
  class R:
   def __init__(self):self.q=[15,10]
   def randrange(self,n):
    seen.append(n);return self.q.pop(0)
  c.rng=R();damage=[];b._deal_fixed=lambda s,t,d,m:damage.append(d)
  b._damaging_move(0,149,c.moves['149'],88,0)
  self.assertEqual(seen,[16,16]);self.assertEqual(damage,[75])

 def test_present_uses_exact_byte_thresholds_and_heal_branch(self):
  for roll,power in ((0,40),(101,40),(102,80),(177,80),(178,120),(203,120)):
   with self.subTest(roll=roll):
    c,b=self.battle(217);c.rng.randrange=lambda n,r=roll:r
    typ,p=b._power_type(0,c.moves['217'],122);self.assertEqual(p,power);self.assertEqual(typ,c.moves['217']['type'])
  c,b=self.battle(217);b.mon(1)['hp']=1000;c.rng.randrange=lambda n:204
  typ,p=b._power_type(0,c.moves['217'],122)
  self.assertIsNone(p);self.assertEqual(b.mon(1)['hp'],1500)
  c,b=self.battle(217);c.rng.randrange=lambda n:255
  b._power_type(0,c.moves['217'],122);self.assertIn('But it failed!',b.logs)

 def test_ohko_level_rule_and_firered_strict_threshold(self):
  # Lower-level OHKO attacks always fail before the random check.
  c,b=self.battle(32,level=49,enemy_level=50);calls=[];c.rng.randrange=lambda n:calls.append(n) or 0
  b._ohko(0,c.moves['32']);self.assertEqual(calls,[]);self.assertEqual(b.mon(1)['hp'],2000)
  # At equal level a final roll of 100 does not satisfy FireRed's strict < threshold.
  c,b=self.battle(32);c.moves['32']=dict(c.moves['32'],accuracy=100);c.rng.randrange=lambda n:99
  b._ohko(0,c.moves['32']);self.assertEqual(b.mon(1)['hp'],2000);self.assertIn('The attack missed!',b.logs)
  c,b=self.battle(32);c.moves['32']=dict(c.moves['32'],accuracy=100);c.rng.randrange=lambda n:98
  b._ohko(0,c.moves['32']);self.assertEqual(b.mon(1)['hp'],0)

 def test_wild_roar_uses_level_check_and_ends_only_on_success(self):
  c,b=self.battle(46,kind='wild',level=40,enemy_level=50);c.rng.randrange=lambda n:0
  b._force_switch(1,0,c.moves['46']);self.assertFalse(b.ended);self.assertIn('But it failed!',b.logs)
  c,b=self.battle(46,kind='wild',level=40,enemy_level=50);c.rng.randrange=lambda n:255
  b._force_switch(1,0,c.moves['46']);self.assertTrue(b.ended);self.assertIsNone(b.winner);self.assertTrue(any(e['cue']=='escape' for e in b.audio_events))
  c,b=self.battle(46,kind='wild',level=50,enemy_level=50);c.rng.randrange=lambda n:(_ for _ in ()).throw(AssertionError('equal-level Roar must not roll'))
  b._force_switch(1,0,c.moves['46']);self.assertTrue(b.ended)

 def test_nature_power_uses_firered_terrain_move_table(self):
  expected={'grass':78,'long_grass':75,'sand':89,'underwater':56,'water':57,'pond':61,'mountain':157,'cave':247,'building':129,'plain':129}
  for terrain,called in expected.items():
   with self.subTest(terrain=terrain):
    c,b=self.battle(267,terrain=terrain);got=[];b._execute_called=lambda side,mid,depth:got.append(mid)
    self.execute(b,0,267);self.assertEqual(got,[called])

 def test_camouflage_uses_terrain_type_table(self):
  expected={'grass':12,'long_grass':12,'sand':4,'underwater':11,'water':11,'pond':11,'mountain':5,'cave':5,'building':0,'plain':0}
  for terrain,typ in expected.items():
   with self.subTest(terrain=terrain):
    c,b=self.battle(293,terrain=terrain);b._camouflage(0);self.assertEqual(b.types(b.mon(0)),[typ])

 def test_secret_power_terrain_secondary_payloads(self):
  cases={'grass':('status','poison'),'long_grass':('status','sleep'),'sand':('stage',(0,-1)),'underwater':('stage',(2,-1)),'water':('stage',(1,-1)),'pond':('stage',(3,-1)),'mountain':('volatile','confusionTurns'),'cave':('volatile','flinch'),'building':('status','paralysis'),'plain':('status','paralysis')}
  for terrain,(kind,value) in cases.items():
   with self.subTest(terrain=terrain):
    c,b=self.battle(290,terrain=terrain);c.rng.random=lambda:0.0;c.rng.randint=lambda a,z:a
    b._secret_power_secondary(0,c.moves['290']);enemy=b.mon(1)
    if kind=='status':self.assertEqual(enemy['status'],value)
    elif kind=='stage':self.assertEqual(b.tiers(enemy)[value[0]],value[1])
    else:self.assertIn(value,b.vol(enemy))

 def test_sleep_talk_excludes_firered_forbidden_effect_families(self):
  c,b=self.battle(214);m=b.mon(0);m['status']='sleep';m['sleep']=3
  bad_effects={9,26,39,75,83,97,145,151,155,159,170,180}
  bad=[]
  for effect in sorted(bad_effects):
   mid=next(int(k) for k,v in c.moves.items() if v['effect']==effect);bad.append({'id':mid,'pp':c.moves[str(mid)]['pp']})
  m['moves']=[{'id':214,'pp':10},{'id':33,'pp':35},*bad]
  pools=[];c.rng.choice=lambda seq:pools.append(list(seq)) or 33;b._execute_called=lambda side,mid,depth:None
  self.execute(b,0,214);self.assertEqual(pools,[[33]])

 def test_copy_moves_enforce_source_restrictions(self):
  c,b=self.battle(102);b.last_move[1]=118;before=copy.deepcopy(b.mon(0)['moves']);b._mimic(0,c.moves['102'])
  self.assertEqual(b.mon(0)['moves'],before);self.assertIn(118,MIMIC_BANNED);self.assertIn('But it failed!',b.logs)
  c,b=self.battle(166);b.last_move[0]=166;b.last_move[1]=166;before=copy.deepcopy(b.mon(0)['moves']);b._sketch(0)
  self.assertEqual(b.mon(0)['moves'],before);self.assertIn('But it failed!',b.logs)

 def test_disable_encore_and_spite_use_actual_last_move_and_pp(self):
  for op in ('disable','encore','spite'):
   with self.subTest(op=op):
    c,b=self.battle(50 if op=='disable' else 227 if op=='encore' else 180,enemy_move=33);b.last_move[1]=33;b.mon(1)['moves'][0]['pp']=10;c.rng.randint=lambda a,z:4
    getattr(b,'_'+op)(0);v=b.vol(b.mon(1))
    if op=='disable':self.assertEqual((v['disabledMove'],v['disableTurns']),(33,4))
    elif op=='encore':self.assertEqual((v['encoreMove'],v['encoreTurns']),(33,4))
    else:self.assertEqual(b.mon(1)['moves'][0]['pp'],6)

 def test_protect_and_endure_chain_caps_denominator_at_eight(self):
  for method in ('_protect','_endure'):
   with self.subTest(method=method):
    c,b=self.battle(182 if method=='_protect' else 203);b.vol(b.mon(0))['protectChain']=5;seen=[];c.rng.randrange=lambda n:seen.append(n) or 0
    getattr(b,method)(0);self.assertEqual(seen,[8]);self.assertEqual(b.vol(b.mon(0))['protectChain'],6)

 def test_charge_survives_end_turn_for_next_electric_attack(self):
  c,b=self.battle(268,extra0=[{'id':85,'pp':15}])
  # Use Thunderbolt's actual PP rather than a hard-coded substitute.
  b.mon(0)['moves'][1]={'id':85,'pp':c.moves['85']['pp']}
  b.choose(0,{'action':'attack','slot':0});b.choose(1,{'action':'attack','slot':0});b.resolve()
  self.assertEqual(b.vol(b.mon(0)).get('chargeElectric'),1)
  charged_before=b.mon(1)['hp'];b.choose(0,{'action':'attack','slot':1});b.choose(1,{'action':'attack','slot':0});b.resolve();charged=charged_before-b.mon(1)['hp']
  c2,clean=self.battle(85);clean.choose(0,{'action':'attack','slot':0});clean.choose(1,{'action':'attack','slot':0});clean.resolve();plain=2000-clean.mon(1)['hp']
  self.assertGreater(charged,plain);self.assertNotIn('chargeElectric',b.vol(b.mon(0)))

 def test_thunder_secondary_paralysis_and_substitute_untraps(self):
  c,b=self.battle(87);c.rng.random=lambda:0.0;c.rng.randrange=lambda n:0;c.rng.randint=lambda a,z:z
  b._damaging_move(0,87,c.moves['87'],152,0);self.assertEqual(b.mon(1)['status'],'paralysis')
  c,b=self.battle(164);v=b.vol(b.mon(0));v.update(wrapTurns=3,trappedBy='x',wrappedBy='x');b._substitute(0)
  self.assertNotIn('wrapTurns',v);self.assertNotIn('trappedBy',v);self.assertNotIn('wrappedBy',v);self.assertGreater(v.get('substituteHp',0),0)

 def test_role_play_skill_swap_imprison_and_wish_fail_guards(self):
  c,b=self.battle(272);b.vol(b.mon(1))['ability']=25;self.execute(b,0,272);self.assertIn('But it failed!',b.logs);self.assertNotIn('ability',b.vol(b.mon(0)))
  c,b=self.battle(285);b.vol(b.mon(1))['ability']=25;self.execute(b,0,285);self.assertIn('But it failed!',b.logs)
  c,b=self.battle(286);self.execute(b,0,286);self.assertNotIn('imprison',b.vol(b.mon(0)));self.assertIn('But it failed!',b.logs)
  c,b=self.battle(286,extra0=[{'id':33,'pp':35}],extra1=[{'id':33,'pp':35}]);self.execute(b,0,286);self.assertTrue(b.vol(b.mon(0)).get('imprison'))
  c,b=self.battle(273);self.execute(b,0,273);self.execute(b,0,273);self.assertEqual(len(b.wishes),1);self.assertIn('But it failed!',b.logs)

 def test_dynamic_hidden_power_type_reaches_color_change(self):
  c,b=self.battle(237);b.vol(b.mon(1))['ability']=16;c.rng.randrange=lambda n:0;c.rng.randint=lambda a,z:z
  typ,_=b._power_type(0,c.moves['237'],135);self.assertNotEqual(typ,c.moves['237']['type'])
  b._damaging_move(0,237,c.moves['237'],135,0);self.assertEqual(b.types(b.mon(1)),[typ])

 def test_pressure_consumes_two_pp_and_doubles_only_moves_fail_cleanly(self):
  c,b=self.battle(33);b.vol(b.mon(1))['ability']=46;before=b.mon(0)['moves'][0]['pp'];b.choose(0,{'action':'attack','slot':0});b.choose(1,{'action':'attack','slot':0});b.resolve();self.assertEqual(b.mon(0)['moves'][0]['pp'],before-2)
  for mid in (266,270):
   with self.subTest(move=mid):
    c,b=self.battle(mid);self.execute(b,0,mid);self.assertIn('But it failed!',b.logs)

if __name__=='__main__':unittest.main()
