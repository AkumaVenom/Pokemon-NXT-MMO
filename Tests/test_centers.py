"""Contract checks for every audited regional Nurse Joy reception."""
import copy, hashlib, json, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'Tools'))
from prepare_centers import apply_centers, counter_access, passable, reachable
from extract_adventure_data import normalize_object_list


class CenterCoverageTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.registry = json.loads((ROOT/'Server/data/centers.json').read_text(encoding='utf-8'))
  cls.raw = json.loads((ROOT/'Tools/extraction_manifest.json').read_text(encoding='utf-8'))
  cls.raw['maps'].update(json.loads((ROOT/'Server/data/interior_maps.json').read_text(encoding='utf-8')))
  cls.normalized = {'maps': copy.deepcopy(cls.raw['maps'])}
  for m in cls.normalized['maps'].values(): m['objects'] = normalize_object_list(m['objects'])
  cls.world = apply_centers(copy.deepcopy(cls.normalized), cls.registry)

 def test_all_firered_center_receptions_are_staffed(self):
  expected = {'5_4','6_5','7_3','8_0','9_1','10_12','11_5','12_5','13_0','14_6','16_0','21_0',
   '31_3','32_0','33_2','34_1','35_1','36_0','37_0'}
  for suffix in expected:
   with self.subTest(map=suffix):
    center = self.world['centers']['kanto_'+suffix]
    self.assertEqual(center['kind'], 'pokemon-center'); self.assertTrue(center['nurseNpcIds'])

 def test_all_sigma_johto_towns_and_route32_have_staffed_receptions(self):
  expected = {'Cherrygrove City':'32_0','Violet City':'33_2','Azalea Town':'34_1','Goldenrod City':'35_1',
   'Ecruteak City':'36_0','Olivine City':'37_0','Cianwood City':'31_3','Mahogany Town':'16_0','Blackthorn City':'21_0'}
  for city, suffix in expected.items():
   with self.subTest(city=city):
    center = self.world['centers']['johto_'+suffix]
    self.assertEqual(center['name'], city); self.assertTrue(center['nurseNpcIds'])
  for suffix in ('34_10', '34_11'):
   self.assertEqual(self.world['centers']['johto_'+suffix]['name'], 'Route 32')

 def test_every_nurse_is_unambiguous_and_reachable_at_counter(self):
  for key, center in self.world['centers'].items():
   m = self.world['maps'][key]
   for npc in center['nurseNpcIds']:
    with self.subTest(map=key, npc=npc):
     candidates = [o for o in m['objects'] if o['id'] == npc]
     self.assertEqual(len(candidates), 1); nurse = candidates[0]
     self.assertEqual(nurse['graphics'], 64)
     front, exits = counter_access(m, nurse)
     self.assertEqual(front, center['respawnByNpc'][str(npc)])
     self.assertEqual(front, [nurse['x'], nurse['y']+2])
     self.assertTrue(passable(m, *front)); self.assertTrue(exits)
     self.assertNotIn(tuple(front), {(p['x'],p['y']) for p in m['warps']})
     floor = reachable(m, front)
     self.assertTrue(any((p['x'],p['y']) in floor for p in m['warps']))

 def test_sigma_keeps_each_native_multiroom_healing_counter(self):
  self.assertEqual(self.world['centers']['johto_13_0']['nurseNpcIds'], [1, 9, 11])
  self.assertEqual(self.world['centers']['johto_34_61']['nurseNpcIds'], [5, 7])
  for key in ('johto_13_0', 'johto_34_61'):
   positions = self.world['centers'][key]['respawnByNpc']
   self.assertEqual(len({tuple(p) for p in positions.values()}), len(positions))

 def test_empty_sigma_lavender_reception_gets_sigma_nurse(self):
  self.assertEqual(self.raw['maps']['johto_8_0']['objects'], [])
  added = self.world['maps']['johto_8_0']['objects']
  self.assertEqual([(o['id'],o['graphics'],o['x'],o['y']) for o in added], [(1,64,7,2)])
  self.assertEqual(self.world['centers']['johto_8_0']['source']['region'], 'johto')

 def test_duplicate_sigma_local_id_does_not_alias_nurse(self):
  original = self.raw['maps']['johto_34_61']['objects']
  self.assertEqual(sum(o['id'] == 5 for o in original), 2)
  corrected = self.world['maps']['johto_34_61']['objects']
  self.assertEqual(sum(o['id'] == 5 for o in corrected), 1)
  self.assertEqual(corrected[3]['graphics'], 64)
  self.assertEqual(corrected[4]['id'], 1); self.assertEqual(corrected[4]['sourceLocalId'], 5)
  self.assertEqual(corrected[4]['sourceObjectIndex'], 4)
  self.assertEqual(corrected[4]['graphics'], 117)

 def test_recovered_sigma_receptions_include_all_seven_counters(self):
  center = self.world['centers']['johto_1_58']
  self.assertEqual(center['nurseNpcIds'], [1,7,9,11,18,27,29])
  self.assertEqual(center['respawnByNpc']['29'], [76,4])
  # The recovered-map sidecar may already contain materialized center additions
  # after a content rebuild. The ROM event audit is the native provenance source.
  native = json.loads((ROOT/'Server/data/adventure_rom.json').read_text(encoding='utf-8'))
  original = native['normalizedObjects']['johto_1_58']
  nurses = [o for o in original if o['graphics']==64]
  self.assertEqual(len(nurses), 6)
  self.assertEqual([o['sourceObjectIndex'] for o in nurses], [0,6,8,10,17,26])
  self.assertFalse(any(o.get('addedBy') for o in nurses))
  self.assertEqual(center['source']['region'], 'johto')

 def test_hidden_nurses_and_link_rooms_are_not_healing_services(self):
  for key in ('johto_34_20','johto_34_26','johto_34_36','johto_34_40','johto_34_32','kanto_5_5','johto_5_5'):
   with self.subTest(map=key): self.assertNotIn(key, self.world['centers'])

 def test_nurse_sprite_files_use_verified_regional_art(self):
  digests = []
  for region, source in self.registry['sources'].items():
   path = ROOT/'Client/app/assets'/source['nurseImage']
   self.assertEqual(source['nurseImage'], f'objects/{region}/64.png')
   digest = hashlib.sha256(path.read_bytes()).hexdigest()
   self.assertEqual(digest, source['nurseImageSha256']); digests.append(digest)
   extraction = next(s for s in self.raw['sources'] if s['source'] == region)
   self.assertEqual(source['sha256'], extraction['sha256'])
  self.assertEqual(len(set(digests)), 2, 'Sigma must retain its distinct Nurse Joy art')

 def test_center_pc_access_is_available_at_each_reception(self):
  for key, center in self.world['centers'].items():
   with self.subTest(map=key):
    self.assertTrue(center['nursePcAccess'] or center['pcNpcIds'])

 def test_center_patch_is_idempotent_and_rejects_conflicting_content(self):
  again = apply_centers(copy.deepcopy(self.world), self.registry)
  self.assertEqual(again, self.world)
  conflict = copy.deepcopy(self.normalized)
  conflict['maps']['johto_8_0']['objects'].append({'id':1,'graphics':19,'x':1,'y':1})
  with self.assertRaises(ValueError): apply_centers(conflict, self.registry)

 def test_center_geometry_change_fails_validation(self):
  conflict = copy.deepcopy(self.world); m = conflict['maps']['kanto_5_4']
  m['collision'][4*m['width']+7] = 1
  with self.assertRaises(ValueError): apply_centers(conflict, self.registry)


if __name__ == '__main__': unittest.main()
