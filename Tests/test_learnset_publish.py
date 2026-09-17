"""Bounded release checks for the actual server/client learnset publication.

These inspect JSON bindings only. Audio decoding and whole-bundle asset hashes
have separate release gates and are deliberately not repeated here.
"""
from pathlib import Path
import copy
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
from publish_learnsets import apply
from publish_battle_mechanics import assemble as apply_battle_mechanics


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


class PublishedLearnsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = read('Server/data/world.json')
        cls.audit = read('Server/data/learnsets.json')
        cls.adventure = read('Server/data/adventure_rom.json')
        cls.client = read('Client/app/assets/world/client.json')
        cls.audio = read('Client/app/assets/audio/catalog.json')

    def test_all_877_server_profiles_equal_the_audited_canonical_overrides(self):
        species = self.world['species']
        self.assertEqual(len(species), 877)
        self.assertEqual(set(species), set(self.audit['speciesOverrides']))
        self.assertEqual(self.world['learnsets']['summary'], self.audit['summary'])
        self.assertEqual(self.world['learnsets']['policy'], self.audit['policy'])
        for key, override in self.audit['speciesOverrides'].items():
            with self.subTest(species=key):
                published = species[key]
                source = override['learnsetProvenance']
                self.assertEqual(published['key'], key)
                self.assertEqual((published['source'], published['sourceId']),
                                 (source['source'], source['sourceSpeciesId']))
                self.assertEqual(published['name'], self.audit['speciesAudit'][key]['name'])
                for field in ['learnset', 'learnsetSource', 'learnsetProvenance']:
                    self.assertEqual(published[field], override[field])
                native = self.audit['sourceCatalogAudit'][published['source']][str(published['sourceId'])]
                self.assertEqual([level for level, _ in published['learnset']],
                                 [level for level, _ in native['learnset']])
                self.assertTrue(all(str(move) in self.world['moves'] for _, move in published['learnset']))

    def test_all_28_previous_sigma_fallbacks_are_native_or_explicitly_recovered(self):
        previous = self.adventure['unsupported']['johto']['learnsets']
        keys = {entry['species'] for entry in previous}
        self.assertEqual(len(keys), 28)
        recovered = set()
        for key in sorted(keys):
            with self.subTest(species=key):
                published = self.world['species'][key]
                self.assertIn(published['learnsetSource'], {'rom', 'rom-recovered-prefix'})
                self.assertNotIn('template', published['learnsetSource'])
                self.assertEqual(published['learnset'], self.audit['speciesOverrides'][key]['learnset'])
                self.assertTrue(published['learnsetProvenance']['rawLearnset'])
                if published['learnsetSource'] == 'rom-recovered-prefix':
                    recovered.add(key)
                    self.assertTrue(published['learnsetProvenance']['recovery']['nativeTerminatorMissing'])
        self.assertEqual(recovered, {'sg_933', 'sg_943'})
        self.assertEqual(self.world['species']['sg_465']['learnset'][0], [10, 71])
        riolu = self.world['species']['sg_500']['learnset']
        self.assertLess(riolu.index([66, 1207]), riolu.index([26, 7]))
        self.assertFalse(any('template' in value['learnsetSource'] for value in self.world['species'].values()))

    def test_shared_firered_profiles_keep_raw_native_moves_in_both_regions(self):
        for key, published in self.world['species'].items():
            if published['source'] != 'kanto':
                continue
            with self.subTest(species=key):
                native = self.audit['sourceCatalogAudit']['kanto'][str(published['sourceId'])]
                self.assertEqual(published['learnset'], native['learnset'])
                self.assertFalse(any(move >= 1024 for _, move in published['learnset']))
        self.assertIn([12, 52], self.world['species']['fr_155']['learnset'])
        self.assertNotIn([10, 52], self.world['species']['fr_155']['learnset'])

    def test_explicit_trainer_moves_use_the_species_source_namespace(self):
        published = self.world['adventureRom']['trainers']
        native = self.adventure['trainers']
        self.assertEqual(set(published), set(native))
        renamed_sigma_teams = 0
        unchanged_shared_teams = 0
        aliases = self.audit['moveIdAliases']['johto']
        for trainer_key, trainer in published.items():
            original = native[trainer_key]
            self.assertEqual(len(trainer['team']), len(original['team']))
            for index, (mon, source_mon) in enumerate(zip(trainer['team'], original['team'])):
                with self.subTest(trainer=trainer_key, teamIndex=index):
                    self.assertEqual(mon['species'], source_mon['species'])
                    self.assertEqual(mon['sourceSpeciesId'], source_mon['sourceSpeciesId'])
                    self.assertEqual(mon['sourceMoves'], source_mon['sourceMoves'])
                    raw_moves = [move for move in source_mon['sourceMoves'] if move]
                    source = self.world['species'][mon['species']]['source']
                    expected = ([aliases.get(str(move), move) for move in raw_moves]
                                if source == 'johto' else raw_moves)
                    self.assertEqual(mon['moves'], expected)
                    self.assertTrue(all(str(move) in self.world['moves'] for move in expected))
                    if source == 'johto' and expected != raw_moves:
                        renamed_sigma_teams += 1
                    if trainer['source'] == 'johto' and source == 'kanto' and any(str(move) in aliases for move in raw_moves):
                        unchanged_shared_teams += 1
                        self.assertFalse(any(move >= 1024 for move in expected))
        self.assertGreater(renamed_sigma_teams, 0)
        self.assertGreater(unchanged_shared_teams, 0)

    def test_client_and_server_publish_identical_species_and_move_definitions(self):
        self.assertEqual(self.client['species'], self.world['species'])
        self.assertEqual(self.client['moves'], self.world['moves'])
        for field in ['version', 'pack', 'assetDigest', 'audio']:
            self.assertEqual(self.client[field], self.world[field])
        self.assertEqual(len(self.world['moves']), 361)
        for key, variant in self.audit['moveOverrides'].items():
            with self.subTest(move=key):
                published = self.world['moves'][key]
                # The learnset publisher owns the recovered Sigma identity fields,
                # while v0.6.8 deliberately layers ROM-audited battle metadata
                # (flags/effect name/provenance) onto every published move.  Keep
                # the original override contract exact without rejecting those
                # additive battle fields.
                for field, value in variant.items():
                    self.assertEqual(published.get(field), value, field)
                self.assertEqual(published['flags'], variant['sourceFlags'])
                self.assertEqual(published['battleProvenance']['source'], 'johto')
                self.assertEqual(published['battleProvenance']['sourceMoveId'], variant['sourceMoveId'])
                self.assertEqual(variant['id'], 1024 + variant['sourceMoveId'])
                self.assertEqual(variant['source'], 'johto')
        # Names do not authorize a Fairy conversion absent source engine proof.
        self.assertEqual(self.world['moves']['1318']['type'], 9)
        self.assertEqual(self.world['moves']['1319']['type'], 9)

    def test_original_move_definitions_remain_the_firered_baseline(self):
        for raw_id, difference in self.audit['moveDefinitionDifferences'].items():
            baseline = difference['kanto']
            published = self.world['moves'][raw_id]
            with self.subTest(move=raw_id):
                for field in ['name', 'effect', 'power', 'type', 'accuracy', 'pp', 'chance', 'target', 'priority']:
                    self.assertEqual(published[field], baseline[field])
        self.assertEqual(self.world['moves']['183']['name'], 'Mach Punch')
        self.assertEqual(self.world['moves']['295']['name'], 'Luster Purge')

    def test_all_seven_variant_sounds_use_sigma_timelines_in_both_region_banks(self):
        sounds = self.audio['moveSounds']
        aliases = self.audit['moveIdAliases']['johto']
        self.assertEqual(len(aliases), 7)
        self.assertEqual(set(sounds), {'kanto', 'johto'})
        for raw_id, variant_id in aliases.items():
            source_sound = sounds['johto'][raw_id]
            for bank in ['kanto', 'johto']:
                with self.subTest(move=variant_id, bank=bank):
                    self.assertEqual(sounds[bank][str(variant_id)], source_sound)
                    for event in source_sound['events']:
                        self.assertIn(event['clip'], self.audio['clips'])
                    for clip in source_sound.get('reachableClips', []):
                        self.assertIn(clip, self.audio['clips'])

    def test_republication_does_not_remap_variants_a_second_time(self):
        # Exclude map grids and assets: this is an in-memory publication check.
        reduced = copy.deepcopy({key: self.world[key] for key in ['species', 'moves', 'adventureRom', 'learnsets', 'battleMechanics']})
        before = copy.deepcopy(reduced)
        apply(reduced, ROOT)
        # Normal v0.6.8 publication deliberately reapplies the ROM battle
        # layer after learnsets rebuild the Sigma alias records.  Exercise the
        # same ordered pipeline here so the idempotency contract matches the
        # actual build.
        apply_battle_mechanics(reduced, ROOT)
        self.assertEqual(reduced, before)


if __name__ == '__main__':
    unittest.main()
