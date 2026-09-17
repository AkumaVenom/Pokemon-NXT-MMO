"""ROM-independent reader and shipped adventure-data regression checks."""
from pathlib import Path
import json, struct, sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Tools'))
from extract_adventure_data import Rom, field_item_script, first_battles, normalize_object_list, trainer

def encode(value):return bytes(0xbb+ord(c)-65 for c in value)

def fake_rom(data=None,size=512):
 r=Rom.__new__(Rom);r.b=bytearray(size) if data is None else bytearray(data);return r

def pointer(value):return struct.pack('<I',0x8000000+value)

def battle(tid=414):return b'\x5c\x00'+struct.pack('<HH',tid,0)+pointer(400)+pointer(410)

class ScriptReaderTests(unittest.TestCase):
 def test_direct_battle(self):
  r=fake_rom();r.b[:14]=battle();found,stops=first_battles(r,0)
  self.assertEqual([x['trainerId'] for x in found],[414]);self.assertFalse(stops)

 def test_message_pointer_is_data_not_script(self):
  r=fake_rom();r.b[:7]=b'\x0f\x00'+pointer(100)+b'\x02';r.b[100:114]=battle()
  self.assertEqual(first_battles(r,0)[0],[])

 def test_calls_return_before_battle(self):
  r=fake_rom();r.b[:5]=b'\x04'+pointer(50);r.b[5:19]=battle();r.b[50:53]=b'\x6a\x5a\x03'
  self.assertEqual(first_battles(r,0)[0][0]['trainerId'],414)

 def test_conditional_teams_are_retained_for_ambiguity_detection(self):
  r=fake_rom();r.b[:6]=b'\x06\x01'+pointer(50);r.b[6:20]=battle(414);r.b[50:64]=battle(415)
  self.assertEqual({x['trainerId'] for x in first_battles(r,0)[0]},{414,415})

 def test_unknown_opcode_stops_before_battle(self):
  r=fake_rom();r.b[:15]=b'\xff'+battle()
  found,stops=first_battles(r,0);self.assertFalse(found);self.assertEqual(stops,{'opcode-ff':1})

 def test_operand_bytes_cannot_become_battle_opcodes(self):
  r=fake_rom();r.b[:10]=b'\x13\x5c'+pointer(50)+b'\x30\x32\x35\x02';r.b[50:64]=battle()
  self.assertFalse(first_battles(r,0)[0])

 def test_invalid_pointer_and_loop_are_bounded(self):
  r=fake_rom();r.b[:5]=b'\x05'+pointer(0)
  self.assertFalse(first_battles(r,0)[0])
  r.b[:5]=b'\x05'+pointer(999999)
  self.assertEqual(first_battles(r,0)[1],{'invalid-instruction':1})

 def test_field_item_reader_accepts_only_bounded_linear_standard_give(self):
  direct=b'\x1a\x00\x80\x0d\x00\x1a\x01\x80\x03\x00\x09\x01\x02'
  r=fake_rom(size=128);r.b[:len(direct)]=direct
  self.assertEqual(field_item_script(r,0)['sourceItemId'],13);self.assertEqual(field_item_script(r,0)['quantity'],3)
  r=fake_rom(size=128);r.b[:3+len(direct)]=b'\x29\x43\x02'+direct
  self.assertEqual(field_item_script(r,0)['sourceItemId'],13)

 def test_field_item_reader_never_scans_past_end_or_branch_into_adjacent_bytes(self):
  direct=b'\x1a\x00\x80\x0d\x00\x1a\x01\x80\x01\x00\x09\x01\x02'
  r=fake_rom(size=128);r.b[:1+len(direct)]=b'\x02'+direct
  self.assertIsNone(field_item_script(r,0))
  r=fake_rom(size=128);r.b[:6+len(direct)]=b'\x06\x01'+pointer(64)+direct
  self.assertIsNone(field_item_script(r,0))

class ObjectIdentityTests(unittest.TestCase):
 def test_hidden_duplicate_does_not_renumber_visible_npc(self):
  raw=[{'id':5,'movement':76,'sourceObjectIndex':0},{'id':5,'movement':0,'sourceObjectIndex':3}]
  self.assertEqual(normalize_object_list(raw),[{'id':5,'movement':0,'sourceObjectIndex':3,'sourceLocalId':5}])

 def test_visible_duplicates_get_unused_ids_and_preserve_source_identity(self):
  raw=[{'id':5,'sourceObjectIndex':3},{'id':5,'sourceObjectIndex':4},{'id':2,'sourceObjectIndex':5}]
  normalized=normalize_object_list(raw)
  self.assertEqual([x['id'] for x in normalized],[5,1,2]);self.assertEqual(normalized[1]['sourceLocalId'],5)
  self.assertEqual(normalized[1]['sourceObjectIndex'],4);self.assertEqual(raw[1]['id'],5)
  self.assertEqual(normalize_object_list(normalized),normalized)

class TrainerReaderTests(unittest.TestCase):
 def fixture(self,flags=3):
  r=fake_rom();q=40;r.b[q]=flags;r.b[q+1]=84;r.b[q+4:q+10]=encode('BROCK')+b'\xff';r.b[q+32]=1;r.b[q+36:q+40]=pointer(100)
  struct.pack_into('<HHHHHHHH',r.b,100,255,14,95,93,33,20,317,0)
  return r,{'trainerTable':0}

 def test_custom_moves_and_held_item_fields_are_not_confused(self):
  r,p=self.fixture();t=trainer(r,p,1,{95:'fr_95'},{str(m):{} for m in (33,20,317)})
  self.assertEqual(t['team'][0]['moves'],[33,20,317]);self.assertEqual(t['team'][0]['heldItemId'],93)
  self.assertEqual(t['team'][0]['iv'],255);self.assertEqual(t['team'][0]['level'],14)

 def test_unknown_species_and_moves_are_rejected(self):
  r,p=self.fixture()
  with self.assertRaises(ValueError):trainer(r,p,1,{}, {})
  with self.assertRaises(ValueError):trainer(r,p,1,{95:'fr_95'},{'33':{}})

class ShippedAdventureDataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=json.loads((ROOT/'Server/data/adventure_rom.json').read_text())
  cls.world=json.loads((ROOT/'Server/data/world.json').read_text())

 def test_every_trainer_binds_one_visible_normalized_npc(self):
  for key,t in self.data['trainers'].items():
   with self.subTest(key=key):
    objects=self.data['normalizedObjects'][t['map']]
    matching=[o for o in objects if o['id']==t['npc']]
    self.assertEqual(len(matching),1);self.assertEqual(matching[0]['sourceObjectIndex'],t['sourceObjectIndex'])
    self.assertEqual([matching[0]['x'],matching[0]['y']],[t['x'],t['y']]);self.assertNotEqual(matching[0]['movement'],76)
    self.assertTrue(1<=len(t['team'])<=6);self.assertFalse(t['doubleBattle'])
    for mon in t['team']:
     self.assertIn(mon['species'],self.world['species']);self.assertTrue(all(str(v) in self.world['moves'] for v in mon['moves']))

 def test_sixteen_actual_gym_parties_and_locations(self):
  for region,names in [('Kanto',['Brock','Misty','Lt. Surge','Erika','Koga','Sabrina','Blaine','Giovanni']),('Johto',['Falkner','Bugsy','Whitney','Morty','Chuck','Jasmine','Pryce','Clair'])]:
   gyms=[g for g in self.data['gyms'] if g['region']==region]
   self.assertEqual([g['order'] for g in gyms],list(range(1,9)));self.assertEqual([g['name'] for g in gyms],names)
   self.assertTrue(all(g['trainer'] in self.data['trainers'] for g in gyms))
  brock=self.data['trainers']['kanto_6_2:1']['team'];falkner=self.data['trainers']['johto_34_8:7']['team']
  self.assertEqual([(m['species'],m['level']) for m in brock],[('fr_74',12),('fr_95',14)])
  self.assertEqual([(m['species'],m['level']) for m in falkner],[('fr_16',10),('fr_17',12),('fr_164',14)])
  self.assertEqual(next(g for g in self.data['gyms'] if g['name']=='Chuck')['map'],'johto_1_88')

 def test_no_duplicate_visible_ids_in_any_map(self):
  for key,objects in self.data['normalizedObjects'].items():
   with self.subTest(map=key):self.assertEqual(len(objects),len({o['id'] for o in objects}))

 def test_evolution_targets_items_and_experience_curves_are_valid(self):
  for key,rules in self.data['evolutions'].items():
   for rule in rules:
    with self.subTest(species=key,target=rule['target']):
     self.assertIn(rule['target'],self.world['species']);self.assertEqual(rule['source'],self.world['species'][key]['source'])
     self.assertEqual(self.world['species'][key]['growth'],self.world['species'][rule['target']]['growth'])
     self.assertIn(rule['method'],['level','trade','stone'])
     if rule['method']=='stone':self.assertTrue(self.data['items'][rule['item']]['evolutionStone'])
  self.assertEqual(self.data['evolutions']['fr_4'][0]['target'],'fr_5')
  self.assertEqual(self.data['evolutions']['fr_152'][0]['target'],'fr_153')

 def test_sigma_field_item_balls_are_fully_audited_and_bound(self):
  audit=self.data['itemPickupAudit'];pickups=self.data['itemPickups']
  self.assertEqual((audit['scannedPokeballObjects'],audit['verifiedPickups'],audit['excludedLookalikes'],audit['uniqueItems']),(386,361,25,125))
  self.assertEqual(len(pickups),361);self.assertEqual(len({p['item'] for p in pickups.values()}),125);self.assertTrue(any(p['quantity']>1 for p in pickups.values()))
  excluded={(p['map'],p['npc']) for p in audit['excluded']}
  self.assertEqual(len(excluded),25)
  for map_id,npc in excluded:
   obj=next((o for o in self.world['maps'][map_id]['objects'] if o['id']==npc),None)
   if obj is not None:self.assertNotIn('itemPickup',obj)
  for pickup_id,pickup in pickups.items():
   with self.subTest(pickup=pickup_id):
    self.assertEqual(pickup['id'],pickup_id);self.assertTrue(1<=pickup['quantity']<=999);self.assertIn(pickup['item'],self.data['items'])
    extracted=next(o for o in self.data['normalizedObjects'][pickup['map']] if o['id']==pickup['npc'])
    published=next(o for o in self.world['maps'][pickup['map']]['objects'] if o['id']==pickup['npc'])
    self.assertEqual(extracted['graphics'],92);self.assertEqual(extracted['sourceObjectIndex'],pickup['sourceObjectIndex']);self.assertEqual(published['itemPickup'],pickup_id)
    self.assertNotIn((pickup['map'],pickup['npc']),excluded)

 def test_sigma_field_item_catalog_preserves_core_mmo_item_mechanics(self):
  self.assertEqual(self.world['items']['pokeball']['capture'],1);self.assertEqual(self.world['items']['greatball']['capture'],1.5);self.assertEqual(self.world['items']['ultraball']['capture'],2)
  self.assertEqual(self.world['items']['potion']['heal'],20);self.assertEqual(self.world['items']['superpotion']['heal'],50)
  self.assertFalse(self.world['items']['choicescarf']['buyable']);self.assertTrue(self.world['items']['choicescarf']['tradable']);self.assertTrue(self.world['items']['coincase']['keyItem']);self.assertFalse(self.world['items']['coincase']['tradable'])
  self.assertEqual(self.world['items']['pokeball']['sourceId'],4);self.assertEqual(self.world['items']['pokeball']['sourcePrice'],300)

 def test_sigma_learnsets_keep_source_order_and_valid_moves(self):
  self.assertGreater(len(self.data['speciesOverrides']),450)
  for key,override in self.data['speciesOverrides'].items():
   with self.subTest(species=key):
    self.assertEqual(self.world['species'][key]['source'],'johto');self.assertEqual(override['learnsetSource'],'rom')
    levels=[v[0] for v in override['learnset']];self.assertEqual(levels,sorted(levels));self.assertEqual(levels[0],1)
    self.assertTrue(all(str(v[1]) in self.world['moves'] for v in override['learnset']))
    self.assertEqual(override['learnsetProvenance']['table'],'0xa74f64')

if __name__=='__main__':unittest.main()
