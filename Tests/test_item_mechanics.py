"""Executable item acceptance against the shipped pack; no invented stub items."""
import asyncio,copy,dataclasses,json,random,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
from nxt.content import Content
from nxt.combat import Battle
from nxt.config import Settings
from nxt.store import Store
from nxt.world import World
from nxt.items import ItemSystem,replace_held
from nxt.security import RequestError

class ItemMechanicsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=Content(ROOT/'Server/data/world.json');cls.i=cls.c.item_system;cls.audit=json.loads((ROOT/'Server/data/item_mechanics.json').read_text())
 def setUp(self):
  original=self.c.rng;self.c.rng=random.Random(61240);self.addCleanup(setattr,self.c,'rng',original)
 def mon(self,species='fr_4',level=40):
  mon=self.c.new_mon(species,level);replace_held(mon,{'heldItemId':0});mon['moves']=[{'id':33,'pp':2,'ppUps':0}];return mon
 def state(self,mon=None):
  mon=mon or self.mon();return {'creatures':[mon],'party':[mon['uid']],'items':{k:5 for k in self.c.items},'money':20000,'coins':0,'heldReserve':{},'pokeblocks':[],'repelSteps':0}
 def battle(self,mon=None,foe=None,kind='wild'):
  return Battle(self.c,kind,[1,None],['Owner','Wild'],[[mon or self.mon()],[foe or self.mon('fr_7')]], [{k:5 for k in self.c.items},{}])
 def held(self,mon,key):
  replace_held(mon,{'heldItemId':self.c.items[key]['sourceId'],'heldItemSource':'johto','heldItemKey':key});return mon
 def test_all_125_pickup_identities_have_explicit_actions_and_valid_provenance(self):
  keys={p['item'] for p in self.c.data['adventureRom']['itemPickups'].values()};self.assertEqual(len(keys),125);self.assertEqual(len(self.audit['rules']),128)
  for key in keys:
   with self.subTest(key=key):
    r=self.i.rule(key);self.assertNotEqual(r['effect'],'unavailable');self.assertTrue(r.get('field') or r.get('battle') or r.get('held') or r.get('sellPrice'));self.assertTrue(r['description']);self.assertEqual(self.audit['nativeItems'][key]['sourceId'],self.c.items[key]['sourceId'])
 def test_timer_ball_completed_turns_and_cap(self):
  b=self.battle()
  for turn,expected in [(1,1),(2,1.1),(10,1.9),(30,3.9),(31,4),(150,4)]:
   b.turn=turn;self.assertEqual(self.i.multiplier('timerball',b,0),expected)
  self.assertEqual(b.view(0)['captureModifiers']['timerball'],4)
 def test_all_capture_balls_throw_consume_and_preserve_capture_identity(self):
  for key,item in self.c.items.items():
   if self.i.rule(key)['effect']!='capture':continue
   with self.subTest(key=key):
    b=self.battle();b.mon(1)['hp']=1;b.mon(1)['status']='sleep'
    with patch.object(self.c.rng,'randrange',return_value=0):b.choose(0,{'action':'capture','item':key});b.resolve()
    self.assertEqual(b.items[0][key],4);self.assertTrue(b.ended);self.assertEqual(b.caught['captureBall'],key);self.assertEqual(b.caught['originalTrainer'],'Owner')
 def test_failed_capture_uses_one_ball_not_the_stack(self):
  b=self.battle(foe=self.mon('fr_150'));before=b.items[0]['timerball']
  with patch.object(self.c.rng,'randrange',return_value=65535):b._capture(0,'timerball')
  self.assertIsNone(b.caught);self.assertFalse(b.ended);self.assertEqual(b.items[0]['timerball'],before-1)
 def test_special_ball_conditions_and_master_trainer_rejection(self):
  b=self.battle();self.assertEqual(self.i.multiplier('netball',b,0),3);self.assertEqual(self.i.multiplier('diveball',b,0),1);b.terrain='underwater';self.assertEqual(self.i.multiplier('diveball',b,0),3.5)
  b.mon(1)['level']=5;self.assertEqual(self.i.multiplier('nestball',b,0),3.5);b.mon(1)['level']=50;self.assertEqual(self.i.multiplier('nestball',b,0),1)
  self.assertEqual(self.i.multiplier('repeatball',b,0),1);b.caught_species[0].add(b.mon(1)['species']);self.assertEqual(self.i.multiplier('repeatball',b,0),3)
  with self.assertRaises(RequestError):self.battle(kind='trainer').choose(0,{'action':'capture','item':'masterball'})
  with self.assertRaises(RequestError):b.choose(0,{'action':'capture','item':'flameball'})
 def test_every_medicine_and_revive_has_a_real_targeted_effect(self):
  for key in self.c.items:
   r=self.i.rule(key)
   if r['effect'] not in ('medicine','revive'):continue
   with self.subTest(key=key):
    m=self.mon();m['hp']=0 if r['effect']=='revive' else 1
    m['status']=(r.get('cure') or ['burn'])[0];m['status']='poison' if m['status'] in ('all','confusion') else m['status']
    b=self.battle(m);b.vol(b.mon(0))['confusionTurns']=3;before=copy.deepcopy(b.mon(0));self.i.battle_action(b,0,key,{'uid':m['uid']})
    self.assertTrue(b.mon(0)!=before or not b.vol(b.mon(0)).get('confusionTurns'));self.assertEqual(b.items[0][key],5 if r.get('reusable') else 4)
    if r.get('heal'):self.assertGreater(b.mon(0)['hp'],1)
    if r['effect']=='revive':self.assertEqual(b.mon(0)['hp'],max(1,int(self.c.stats(m)[0]*r['fraction'])))
    if r.get('cure'):self.assertFalse(b.vol(b.mon(0)).get('confusionTurns') if key=='yellowflute' else b.mon(0)['status'])
 def test_no_effect_medicine_never_spends_or_queues(self):
  b=self.battle();before=copy.deepcopy(b.items)
  with self.assertRaisesRegex(RequestError,'no effect'):b.choose(0,{'action':'item','item':'potion'})
  self.assertEqual(b.items,before);self.assertNotIn(0,b.choice)
 def test_bench_healing_and_reviving_use_uid_not_lead(self):
  b=self.battle();bench=self.mon('fr_1');bench['hp']=0;b.rosters[0].append(bench);lead=copy.deepcopy(b.mon(0));self.i.battle_action(b,0,'revive',{'uid':bench['uid']})
  self.assertGreater(bench['hp'],0);self.assertEqual(b.mon(0),lead)
  with self.assertRaisesRegex(RequestError,'battle party'):self.i.battle_action(b,0,'potion',{'uid':'foreign'})
 def test_every_pp_item_and_upgrades_respects_current_maximum(self):
  for key in ['ether','maxether','elixir','maxelixir']:
   m=self.mon();m['moves']=[{'id':33,'pp':0,'ppUps':3},{'id':45,'pp':0,'ppUps':0}];s=self.state(m);out=self.i.field_use(s,key,{'uid':m['uid'],'slot':0,'expectedMove':33});r=self.i.rule(key)
   for index in range(2 if r['allMoves'] else 1):self.assertEqual(out['creatures'][0]['moves'][index]['pp'],min(r['pp'],self.c.pp_max(m['moves'][index])))
   self.assertEqual(s['creatures'][0]['moves'][0]['pp'],0)
  for key,ups in [('ppup',1),('ppmax',3)]:
   s=self.state();m=s['creatures'][0];before=self.c.pp_max(m['moves'][0]);out=self.i.field_use(s,key,{'uid':m['uid'],'slot':0});q=out['creatures'][0]['moves'][0];self.assertEqual(q['ppUps'],ups);self.assertEqual(q['pp'],2+self.c.pp_max(q)-before);self.c.heal(out['creatures'][0]);self.assertEqual(q['pp'],self.c.pp_max(q))
  with self.assertRaises(RequestError):self.i.field_use(out,'ppmax',{'uid':m['uid'],'slot':0})
 def test_all_vitamins_raise_correct_ev_and_obey_caps(self):
  for key in ['hpup','protein','iron','carbos','calcium','zinc']:
   s=self.state();m=s['creatures'][0];r=self.i.rule(key);out=self.i.field_use(s,key,{'uid':m['uid']});self.assertEqual(out['creatures'][0]['evs'][r['stat']],10);self.assertGreater(out['creatures'][0]['friendship'],m['friendship']);m['evs'][r['stat']]=100
   with self.assertRaises(RequestError):self.i.field_use(s,key,{'uid':m['uid']})
  s=self.state();m=s['creatures'][0];m['evs']=[0,255,255,0,0,0]
  with self.assertRaises(RequestError):self.i.field_use(s,'hpup',{'uid':m['uid']})
 def test_rare_candy_progression_level_cap_and_pending_choices(self):
  s=self.state(self.mon('fr_4',15));m=s['creatures'][0];out=self.i.field_use(s,'rarecandy',{'uid':m['uid']});q=out['creatures'][0];self.assertEqual(q['level'],16);self.assertTrue(any(o['target']=='fr_5' for o in self.c.growth.options(q)))
  q['level']=100;q['exp']=self.c.xp(100,self.c.species[q['species']]['growth'])
  with self.assertRaises(RequestError):self.i.field_use(out,'rarecandy',{'uid':q['uid']})
 def test_skill_capsule_switches_two_real_regular_abilities(self):
  species=next(k for k,s in self.c.species.items() if len(s.get('abilities',[]))>1 and s['abilities'][0] and s['abilities'][1] and s['abilities'][0]!=s['abilities'][1]);s=self.state(self.mon(species));m=s['creatures'][0];old=self.i.ability_slot(m);out=self.i.field_use(s,'skillcapsule',{'uid':m['uid']});self.assertEqual(self.i.ability_slot(out['creatures'][0]),1-old);self.assertNotEqual(self.battle(m).ability(m),self.battle(out['creatures'][0]).ability(out['creatures'][0]))
 def test_every_machine_uses_sigma_move_compatibility_and_consumption(self):
  expected={'tm01':276,'tm02':29,'tm05':46,'tm12':230,'tm17':182,'tm21':250,'tm36':188,'tm48':85,'hm09':47}
  for key,mid in expected.items():
   with self.subTest(key=key):
    species=next(k for k,s in self.c.species.items() if key in s['machines']);state=self.state(self.mon(species));m=state['creatures'][0];out=self.i.field_use(state,key,{'uid':m['uid'],'slot':0,'expectedMove':33});self.assertEqual(out['creatures'][0]['moves'],[{'id':mid,'pp':self.c.moves[str(mid)]['pp'],'ppUps':0}]);self.assertEqual(out['items'][key],5 if key.startswith('hm') else 4)
    with self.assertRaises(RequestError):self.i.field_use(out,key,{'uid':m['uid'],'slot':0})
    bad=next(k for k,s in self.c.species.items() if key not in s['machines']);state=self.state(self.mon(bad))
    with self.assertRaises(RequestError):self.i.field_use(state,key,{'uid':state['party'][0],'slot':0})
 def test_every_evolution_item_has_a_working_owned_species_edge(self):
  for key in self.c.items:
   r=self.i.rule(key)
   if r['effect']!='evolution':continue
   with self.subTest(key=key):
    token=r.get('evolutionAlias',key);source,rule=next((s,e) for s,rows in self.audit['evolutions'].items() for e in rows if e['item']==token);state=self.state(self.mon(source));m=state['creatures'][0];out=self.i.field_use(state,key,{'uid':m['uid'],'target':rule['target']});self.assertEqual(out['creatures'][0]['species'],rule['target']);self.assertEqual(out['items'][key],4);self.assertEqual(state['items'][key],5)
    if token!=key:self.assertEqual(out['items'][token],state['items'][token])
 def test_give_take_every_held_item_roundtrips_without_losing_inventory(self):
  for key in self.c.items:
   r=self.i.rule(key)
   if not r.get('held'):continue
   with self.subTest(key=key):
    state=self.state();uid=state['party'][0];equipped=self.i.equip(state,{'uid':uid,'item':key});m=equipped['creatures'][0];self.assertEqual(self.i.held_key(m),key);self.assertEqual(self.i.held(m),r['held']);self.assertEqual(equipped['items'][key],4);back=self.i.equip(equipped,{'uid':uid},take=True);self.assertEqual(back['items'],state['items']);self.assertEqual(back['creatures'][0]['heldItemId'],0)
 def test_sigma_held_ids_cannot_activate_unrelated_firered_effects(self):
  sigma=self.held(self.mon(),'upgrade');native=self.mon();replace_held(native,{'heldItemId':44,'heldItemSource':'kanto'});self.assertEqual(self.i.held_code(sigma),0);self.assertEqual(self.i.held_code(native),44)
  state=self.state(native);out=self.i.equip(state,{'uid':native['uid']},take=True);self.assertEqual(out['heldReserve']['kanto:44']['quantity'],1);out=self.i.equip(out,{'uid':native['uid'],'reserve':'kanto:44'});self.assertEqual(self.i.held_code(out['creatures'][0]),44);self.assertEqual(out['heldReserve']['kanto:44']['quantity'],0)
 def test_full_return_stack_and_stale_held_state_leave_input_unchanged(self):
  state=self.state(self.held(self.mon(),'flameball'));state['items']['flameball']=999;before=copy.deepcopy(state)
  with self.assertRaises(RequestError):self.i.equip(state,{'uid':state['party'][0]},take=True)
  with self.assertRaises(RequestError):self.i.equip(state,{'uid':state['party'][0],'item':'smokeball','expectedHeld':0})
  self.assertEqual(state,before)
 def test_held_type_boosters_change_damage_and_choice_scarf_locks_moves(self):
  m=self.mon();m['moves']=[{'id':52,'pp':25},{'id':33,'pp':35}];b=self.battle(m);move=self.c.moves['52'];self.c.rng=random.Random(101);rng=self.c.rng.getstate();without=b._calculate_damage(0,move,100,10,move['effect'])[0];self.c.rng.setstate(rng);self.held(b.mon(0),'flameball');with_item=b._calculate_damage(0,move,100,10,move['effect'])[0];self.assertGreater(with_item,without)
  self.held(b.mon(0),'choicescarf');speed=self.c.stats(b.mon(0))[3];self.assertEqual(b._stat(0,3),speed*3//2);b._attack_action(0,{'slot':0});self.assertEqual(b.usable(b.mon(0)),[0])
 def test_lucky_egg_and_training_held_items_affect_earned_rewards(self):
  for key in ['luckyegg','machobrace','poweranklet','powerband','powerlens']:
   m=self.held(self.mon(),key);r=self.i.held(m);before=m['exp'];actual,_=self.i.award_experience(m,'fr_1',100);self.assertEqual(actual,150 if key=='luckyegg' else 100);self.assertEqual(m['exp']-before,actual);y=list(self.c.species['fr_1']['evYield']);
   if 'evStat' in r:y[r['evStat']]+=4
   self.assertEqual(m['evs'],[q*r.get('evMultiplier',1) for q in y])
 def test_held_berries_trigger_and_consume_without_altering_other_namespace(self):
  for key in ['lumberry','sitrusberry']:
   b=self.battle(self.held(self.mon(),key));m=b.mon(0);m['hp']=1;m['status']='poison';b._consume_item_if_needed(0);self.assertEqual(m['heldItemId'],0)
   if key=='lumberry':self.assertEqual(m['status'],'')
   else:self.assertEqual(m['hp'],31)
 def test_smoke_ball_escapes_trapping_and_is_not_consumed(self):
  b=self.battle(self.held(self.mon(),'smokeball'));b.vol(b.mon(0))['trappedBy']=b.mon(1)['uid'];self.assertTrue(b._trapped(0));self.assertTrue(b.view(0)['canRun']);b.choose(0,{'action':'run'});b.resolve();self.assertTrue(b.ended);self.assertEqual(self.i.held_key(b.mon(0)),'smokeball')
 def test_every_x_item_guard_spec_and_dire_hit_have_battle_effects(self):
  for key in ['xattack','xdefend','xspeed','xspecial','xaccuracy']:
   b=self.battle();r=self.i.rule(key);self.i.battle_action(b,0,key,{});self.assertEqual(b.tiers(b.mon(0))[r['stat']],1);b.tiers(b.mon(0))[r['stat']]=6
   with self.assertRaises(RequestError):self.i.battle_action(b,0,key,{})
  b=self.battle();self.i.battle_action(b,0,'guardspec',{});self.assertEqual(b.side[0]['mist'],5);b._change_stage(0,1,-1,source_side=1);self.assertEqual(b.tiers(b.mon(0))[1],0);self.i.battle_action(b,0,'direhit',{});self.assertTrue(b.vol(b.mon(0))['focusEnergy'])
 def test_tera_adapter_changes_defense_and_stab_without_spending_orb(self):
  b=self.battle();b.choose(0,{'action':'attack','slot':0,'tera':True});b.resolve();self.assertTrue(b.tera_used[0]);self.assertEqual(b.types(b.mon(0)),[10]);self.assertEqual(b.items[0]['teraorb'],5);self.assertFalse(b.view(0)['canTera'])
  with self.assertRaises(RequestError):b.choose(0,{'action':'attack','slot':0,'tera':True})
 def test_sacred_ash_pokeflute_and_repel_do_not_touch_stored_creatures(self):
  state=self.state();m=state['creatures'][0];m['hp']=0;stored=self.mon();stored['hp']=0;state['creatures'].append(stored);out=self.i.field_use(state,'sacredash',{});self.assertGreater(out['creatures'][0]['hp'],0);self.assertEqual(out['creatures'][1]['hp'],0)
  out['creatures'][0]['status']='sleep';out=self.i.field_use(out,'pokeflute',{});self.assertEqual(out['creatures'][0]['status'],'');self.assertEqual(out['items']['pokeflute'],5)
  for key,steps in [('repel',100),('superrepel',200),('maxrepel',250)]:
   out=self.i.field_use(state,key,{});self.assertEqual(out['repelSteps'],steps)
   with self.assertRaises(RequestError):self.i.field_use(out,key,{})
 def test_all_valuables_sell_for_authoritative_prices_and_quantities(self):
  for key in self.c.items:
   if self.i.rule(key)['effect']!='valuable':continue
   s=self.state();out=self.i.sell(s,key,3);self.assertEqual(out['items'][key],2);self.assertEqual(out['money'],s['money']+3*self.i.rule(key)['sellPrice'])
  for n in [True,0,-1,6,999999]:
   with self.assertRaises(RequestError):self.i.sell(s,'nugget',n)
 def test_services_craft_exchange_blend_feed_and_do_not_consume_cases(self):
  s=self.state();out=self.i.service(s,'whtapricorn',{'action':'craft'});self.assertEqual(out['items']['whtapricorn'],4);self.assertEqual(out['items']['fastball'],6)
  out=self.i.service(s,'coincase',{'action':'buycoins','quantity':500});self.assertEqual(out['money'],10000);self.assertEqual(out['coins'],500);out=self.i.service(out,'coincase',{'action':'prize','reward':'timerball'});self.assertEqual(out['coins'],400);self.assertEqual(out['items']['timerball'],6);self.assertEqual(out['items']['coincase'],5)
  out=self.i.service(s,'pokeblockcas',{'action':'blend','berry':'sitrusberry','_blockId':'server-block'});out=self.i.service(out,'pokeblockcas',{'action':'feed','block':'server-block','uid':out['party'][0]});self.assertEqual(out['pokeblocks'],[]);self.assertEqual(out['creatures'][0]['condition'],{'beauty':20,'sheen':10});self.assertEqual(out['items']['pokeblockcas'],5)
 def test_luxury_ball_friendship_bonus_is_durable(self):
  ordinary=self.mon();luxury=copy.deepcopy(ordinary);luxury['captureBall']='luxuryball';self.i.positive_friendship(ordinary);self.i.positive_friendship(luxury);self.assertEqual(luxury['friendship'],ordinary['friendship']+1)
 def test_skill_capsule_unsupported_destination_is_rejected_without_spending(self):
  species=next(k for k,sp in self.c.species.items() if len(sp.get('abilities',[]))>=2 and sp['abilities'][0]>0 and sp['abilities'][1]>77 and sp['abilities'][0]!=sp['abilities'][1]);state=self.state(self.mon(species));state['creatures'][0]['abilitySlot']=0;before=copy.deepcopy(state)
  with self.assertRaisesRegex(RequestError,'not consumed'):self.i.field_use(state,'skillcapsule',{'uid':state['party'][0]})
  self.assertEqual(state,before)
 def test_focus_band_can_preserve_a_holder_already_at_one_hp(self):
  b=self.battle(foe=self.held(self.mon('fr_7'),'focusband'));b.mon(1)['hp']=1
  with patch.object(self.c.rng,'random',return_value=0):damage=b._damage(0,1,99,move=self.c.moves['33'],physical=True)
  self.assertEqual(damage,0);self.assertEqual(b.mon(1)['hp'],1);self.assertEqual(self.i.held_key(b.mon(1)),'focusband');self.assertTrue(any('Focus Band' in line for line in b.logs))
 def test_accuracy_and_sigma_evasion_items_change_hit_thresholds(self):
  b=self.battle();move={**self.c.moves['33'],'accuracy':80};b.ability=lambda mon:0
  with patch.object(self.c.rng,'randrange',return_value=85):
   self.assertFalse(b._accuracy(0,move,move['effect']));self.held(b.mon(0),'widelens');self.assertTrue(b._accuracy(0,move,move['effect']))
  replace_held(b.mon(0),{'heldItemId':0});move['accuracy']=100
  for key in ('roseincense','oddincense'):
   self.held(b.mon(1),key)
   with patch.object(self.c.rng,'randrange',return_value=95):self.assertFalse(b._accuracy(0,move,move['effect']))
 def test_sigma_species_specific_held_effects_apply_only_to_correct_species(self):
  for key,name,index,factor in [('stickybarb','Clamperl',5,2),('enigmastone','Latios',4,1.5),('enigmastone','Latias',5,1.5)]:
   species=next(k for k,sp in self.c.species.items() if sp['name']==name);b=self.battle(self.mon(species));base=b._stat(0,index);self.held(b.mon(0),key);self.assertEqual(b._stat(0,index),int(base*factor))
   wrong=self.battle();base=wrong._stat(0,index);self.held(wrong.mon(0),key);self.assertEqual(wrong._stat(0,index),base)
 def test_training_items_also_reduce_speed_without_changing_persistent_base_stats(self):
  for key in ('machobrace','poweranklet','powerband','powerlens'):
   b=self.battle();before=self.c.stats(b.mon(0));speed=b._stat(0,3);self.held(b.mon(0),key);self.assertEqual(b._stat(0,3),max(1,speed//2));self.assertEqual(self.c.stats(b.mon(0)),before)
 def test_selling_cannot_generate_buy_sell_arbitrage(self):
  for key,item in self.c.items.items():
   if item.get('buyable',True):self.assertLessEqual(self.i.rule(key).get('sellPrice',0)*2,item['price'])
 def test_every_held_type_booster_changes_real_published_move_damage(self):
  original_rng=self.c.rng;self.c.rng=random.Random(4091);self.addCleanup(setattr,self.c,'rng',original_rng)
  for key,item in self.c.items.items():
   held=item['mechanics'].get('held',{})
   if 'boostType' not in held:continue
   with self.subTest(key=key):
    move=next(v for v in self.c.moves.values() if v['type']==held['boostType'] and v.get('power',0)>0);b=self.battle(foe=self.mon('fr_19'));before_rng=self.c.rng.getstate();before=b._calculate_damage(0,move,100,move['type'],move['effect'])[0];self.c.rng.setstate(before_rng);self.held(b.mon(0),key);after=b._calculate_damage(0,move,100,move['type'],move['effect'])[0];self.assertGreater(after,before)
  self.assertEqual(self.i.rule('destinyknot')['held']['boostType'],self.c.moves['1319']['type'])
 def test_publication_namespaces_remain_private_and_compatible(self):
  m=self.held(self.mon(),'flameball');public=self.c.public_mon(m,False);private=self.c.public_mon(m);self.assertNotIn('evs',public);self.assertNotIn('heldItemKey',public);self.assertEqual(private['heldItemName'],'Flame Ball');self.assertEqual(private['moves'],m['moves']);self.assertEqual(self.c.pp_max(private['moves'][0]),35)

class DurableItemTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();cfg=Path(self.tmp.name)/'config.ini';cfg.write_bytes((ROOT/'Build/config_templates/Server/config.ini').read_bytes());settings=Settings.load(cfg);settings.config.set('database','backend','sqlite');self.s=dataclasses.replace(settings,encounter_chance=0);self.c=Content(ROOT/'Server/data/world.json');self.db=Store(self.s);self.db.acquire_lease();self.w=World(self.c,self.db,self.s)
  self.a=await self.add('ItemsOwner');self.b=await self.add('ItemsPeer')
 async def add(self,name):
  s=self.w.initial(name,'Kanto','fr_4',0);s['items'].update({k:5 for k in self.c.items});s['creatures'][0]['hp']=1;s['money']=50000;uid=self.db.create(name,'unused',s);return await self.w.join(uid,name,s,asyncio.Queue(maxsize=4096))
 async def asyncTearDown(self):self.w.players.clear();self.db.close();self.tmp.cleanup()
 async def test_use_receipt_replay_owner_isolation_and_relogin(self):
  before=copy.deepcopy(self.b.state);d={'op':'use','item':'potion','uid':self.a.state['party'][0],'requestId':'qa-1'};await self.w.dispatch(self.a,d);saved=copy.deepcopy(self.db.load(self.a.id));await self.w.dispatch(self.a,d);self.assertEqual(self.db.load(self.a.id),saved);self.assertEqual(self.a.state['items']['potion'],4);self.assertEqual(self.b.state,before)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{**d,'item':'superpotion'})
  old=self.a;self.w.players.pop(old.id);self.a=await self.w.join(old.id,old.username,saved,asyncio.Queue(maxsize=4096));await self.w.dispatch(self.a,d);self.assertEqual(self.a.state['items']['potion'],4)
 async def test_invalid_target_and_injected_storage_failure_are_atomic(self):
  before=copy.deepcopy(self.a.state)
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'use','item':'potion','uid':self.b.state['party'][0]})
  with patch.object(self.db,'save_many',side_effect=OSError('injected storage failure')):
   with self.assertLogs('nxt.world',level='ERROR'):
    with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'use','item':'potion','uid':self.a.state['party'][0],'requestId':'fail-1'})
  self.assertEqual(self.a.state,before);self.assertEqual(self.db.load(self.a.id),before)
 async def test_give_take_and_machine_changes_persist(self):
  uid=self.a.state['party'][0];await self.w.dispatch(self.a,{'op':'item.give','item':'flameball','uid':uid});self.assertEqual(self.db.load(self.a.id)['creatures'][0]['heldItemKey'],'flameball');await self.w.dispatch(self.a,{'op':'item.take','uid':uid});self.assertEqual(self.db.load(self.a.id)['items']['flameball'],5)
  mon=self.a.state['creatures'][0];machine=next(k for k in self.c.species[mon['species']]['machines'] if self.c.items[k]['mechanics']['move'] not in [m['id'] for m in mon['moves']]);await self.w.dispatch(self.a,{'op':'use','item':machine,'uid':uid,'slot':0});saved=self.db.load(self.a.id);self.assertEqual(saved['creatures'][0]['moves'][0]['id'],self.c.items[machine]['mechanics']['move'])
 async def test_mart_and_kurt_location_checks_reject_remote_services(self):
  self.s.config.set('gameplay','enable_alpha_atlas','false')
  self.assertFalse(self.w.item_context(self.a.state)['apricorn'])
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'item.service','item':'whtapricorn','action':'craft'})
  with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'use','item':'escaperope'})
 async def test_recorded_escape_is_atomic_and_preserves_inventory_and_flags(self):
  outside=copy.deepcopy(self.a.state);key=next(k for k,m in self.c.maps.items() if k.startswith('johto_') and self.w.escape_allowed(m) and m.get('playable',True));candidate=self.w.relocation_state(self.a,key);await self.w.commit(self.a,candidate);self.assertTrue(self.a.state.get('escapeAnchor'));await self.w.dispatch(self.a,{'op':'use','item':'escaperope'});saved=self.db.load(self.a.id);self.assertEqual(saved['map'],outside['map']);self.assertEqual(saved['items']['escaperope'],4);self.assertNotIn('escapeAnchor',saved)
 async def test_repel_successful_step_decrements_and_blocked_step_does_not(self):
  m=self.c.maps[self.a.state['map']];pair=next((x,y,dx,dy,dr) for y in range(m['height']) for x in range(m['width']) for dx,dy,dr in [(1,0,'right'),(-1,0,'left'),(0,1,'down'),(0,-1,'up')] if self.w.walkable(m,x,y,state=self.a.state) and self.w.walkable(m,x+dx,y+dy,state=self.a.state) and not any(w.get('x')==x+dx and w.get('y')==y+dy for w in m.get('warps',[])))
  x,y,dx,dy,dr=pair;s=copy.deepcopy(self.a.state);s.update(x=x,y=y,repelSteps=2);await self.w.commit(self.a,s);await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':dr});self.assertEqual(self.a.state['repelSteps'],1)
  self.a.last_move=0
  with patch.object(self.w,'walkable',return_value=False):await self.w.dispatch(self.a,{'op':'move','seq':2,'direction':dr})
  self.assertEqual(self.a.state['repelSteps'],1)

if __name__=='__main__':unittest.main()
