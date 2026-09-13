"""ROM-free parser, provenance, identity, and exhaustive shipped-list checks."""
from pathlib import Path
import copy
import hashlib
import json
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
from extract_adventure_data import Rom
from extract_learnsets import (PROFILES, RECOVERIES, RENAMED_SIGMA_MOVES,
                              entry_flags, packed_entries, parse_learnset,
                              recover_reviewed_prefix)


def fake_rom(data):
    rom = Rom.__new__(Rom)
    rom.b = bytearray(data)
    return rom


class PackedLearnsetTests(unittest.TestCase):
    def test_same_level_moves_and_repeated_moves_keep_source_order(self):
        entries = [[1, 279], [1, 4], [26, 9], [26, 8], [26, 7], [26, 9]]
        parsed = parse_learnset(fake_rom(packed_entries(entries)), 0)
        self.assertEqual(parsed['status'], 'validated')
        self.assertEqual(parsed['learnset'], entries)
        self.assertIn('repeated-levels', entry_flags(entries))
        self.assertIn('repeated-level-and-move', entry_flags(entries))

    def test_missing_level_one_is_a_valid_native_list(self):
        entries = [[10, 31], [15, 116], [20, 41]]
        parsed = parse_learnset(fake_rom(packed_entries(entries)), 0)
        self.assertEqual(parsed['status'], 'validated')
        self.assertEqual(parsed['learnset'], entries)
        self.assertIn('no-level-one-entry', entry_flags(entries))

    def test_descending_levels_are_preserved(self):
        entries = [[1, 4], [13, 228], [66, 183], [26, 7], [26, 8], [26, 9], [50, 68]]
        parsed = parse_learnset(fake_rom(packed_entries(entries)), 0)
        self.assertEqual(parsed['status'], 'validated')
        self.assertEqual(parsed['learnset'], entries)
        self.assertIn('descending-native-levels', entry_flags(entries))

    def test_empty_native_list_does_not_invent_tackle(self):
        parsed = parse_learnset(fake_rom(b'\xff\xff'), 0)
        self.assertEqual(parsed['status'], 'validated')
        self.assertEqual(parsed['learnset'], [])

    def test_terminator_is_checked_before_level_and_move_masks(self):
        self.assertEqual(parse_learnset(fake_rom(b'\xff\xff'), 0)['terminatorOffset'], '0x0')

    def test_invalid_levels_and_unsupported_moves_fail_without_partial_publication(self):
        for level, move, reason in [(0, 33, 'invalid-level'), (101, 33, 'invalid-level'),
                                    (1, 355, 'unsupported-move'), (1, 0, 'unsupported-move')]:
            with self.subTest(level=level, move=move):
                data = packed_entries([[1, 33], [level, move]])
                parsed = parse_learnset(fake_rom(data), 0)
                self.assertEqual(parsed['status'], 'unsupported')
                self.assertEqual(parsed['reason'], reason)
                self.assertEqual(parsed['decodedPrefix'], [[1, 33]])
                self.assertNotIn('learnset', parsed)

    def test_missing_terminator_and_rom_range_are_bounded(self):
        parsed = parse_learnset(fake_rom(packed_entries([[1, 33]] * 128, False)), 0)
        self.assertEqual(parsed['reason'], 'unterminated-learnset')
        self.assertNotIn('learnset', parsed)
        parsed = parse_learnset(fake_rom(packed_entries([[1, 33]], False)), 0)
        self.assertEqual(parsed['reason'], 'record-exceeds-rom')
        self.assertEqual(parse_learnset(fake_rom(b''), -2)['reason'], 'record-exceeds-rom')

    def test_catalog_restrictions_are_honored(self):
        parsed = parse_learnset(fake_rom(packed_entries([[1, 33], [5, 52]])), 0, {'33'})
        self.assertEqual(parsed['reason'], 'unsupported-move')
        self.assertEqual(parsed['decodedValue'], [5, 52])


class ShippedLearnsetAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'Server/data/learnsets.json').read_text(encoding='utf-8'))
        cls.world = json.loads((ROOT / 'Server/data/world.json').read_text(encoding='utf-8'))
        cls.manifest = json.loads((ROOT / 'Tools/extraction_manifest.json').read_text(encoding='utf-8'))

    def test_all_877_published_species_have_explicit_source_evidence(self):
        species = self.world['species']
        self.assertEqual(len(species), 877)
        self.assertEqual(set(species), set(self.data['speciesAudit']))
        self.assertEqual(set(species), set(self.data['speciesOverrides']))
        self.assertFalse(self.data['unsupported'])
        self.assertEqual(self.data['summary']['statusCounts'], {'validated': 875, 'recovered-native-prefix': 2})
        for key, current in species.items():
            with self.subTest(species=key):
                audit = self.data['speciesAudit'][key]
                provenance = self.data['speciesOverrides'][key]['learnsetProvenance']
                self.assertEqual((audit['source'], audit['sourceSpeciesId'], audit['name']),
                                 (current['source'], current['sourceId'], current['name']))
                self.assertEqual(provenance['sourceSpeciesId'], current['sourceId'])
                self.assertEqual(provenance['sha256'], PROFILES[current['source']]['sha256'])
                self.assertEqual(int(provenance['pointerOffset'], 16),
                                 PROFILES[current['source']]['table'] + current['sourceId'] * 4)

    def test_every_manifest_index_is_audited_without_extending_the_active_table(self):
        for tag, catalog in self.manifest['catalogs'].items():
            audited = self.data['sourceCatalogAudit'][tag]
            self.assertEqual(set(audited), set(catalog))
            for raw_id, record in audited.items():
                with self.subTest(source=tag, sourceSpeciesId=raw_id):
                    self.assertEqual(record['name'], catalog[raw_id]['name'])
                    if int(raw_id) >= PROFILES[tag]['tableEntries']:
                        self.assertEqual(record['reason'], 'outside-active-learnset-table')
                        self.assertNotIn('learnset', record)
                    else:
                        self.assertIn(record['status'], {'validated', 'recovered-native-prefix'})

    def test_all_decoded_native_records_reproduce_their_raw_checksums(self):
        for tag, catalog in self.data['sourceCatalogAudit'].items():
            for raw_id, record in catalog.items():
                if 'learnset' not in record:
                    continue
                with self.subTest(source=tag, sourceSpeciesId=raw_id):
                    recovered = record['status'] == 'recovered-native-prefix'
                    packed = packed_entries(record['learnset'], not recovered)
                    self.assertEqual(hashlib.sha256(packed).hexdigest(), record['rawSha256'])
                    self.assertEqual(len(packed), record['rawBytes'])
                    self.assertTrue(all(1 <= level <= 100 and 1 <= move <= 354 for level, move in record['learnset']))
                    if not recovered:
                        self.assertEqual(int(record['terminatorOffset'], 16),
                                         int(record['offset'], 16) + len(record['learnset']) * 2)

    def test_all_published_rows_match_native_rows_with_only_explicit_move_aliases(self):
        available = set(self.world['moves']) | set(self.data['moveOverrides'])
        for key, override in self.data['speciesOverrides'].items():
            with self.subTest(species=key):
                provenance = override['learnsetProvenance']
                tag, source_id = provenance['source'], provenance['sourceSpeciesId']
                record = self.data['sourceCatalogAudit'][tag][str(source_id)]
                aliases = self.data['moveIdAliases'].get(tag, {})
                expected = [[level, aliases.get(str(move), move)] for level, move in record['learnset']]
                self.assertEqual(override['learnset'], expected)
                self.assertTrue(all(str(move) in available for _, move in expected))
                if tag == 'johto':
                    self.assertEqual(provenance['rawLearnset'], record['learnset'])
                else:
                    self.assertEqual(override['learnset'], record['learnset'])

    def test_cyndaquil_ember_is_level_12_in_both_supplied_roms(self):
        for tag in ['kanto', 'johto']:
            record = self.data['sourceCatalogAudit'][tag]['155']
            self.assertIn([12, 52], record['learnset'])
            self.assertNotIn([10, 52], record['learnset'])
        self.assertEqual(self.data['sharedSpeciesComparisons']['fr_155']['result'], 'identical')

    def test_native_missing_level_one_and_order_survive_publication(self):
        self.assertEqual(self.data['speciesOverrides']['sg_465']['learnset'][0], [10, 71])
        riolu = self.data['speciesOverrides']['sg_500']['learnset']
        self.assertLess(riolu.index([66, 1207]), riolu.index([26, 7]))
        self.assertEqual([entry for entry in riolu if entry[0] == 26], [[26, 7], [26, 8], [26, 9]])
        self.assertEqual(self.data['summary']['flagCounts']['no-level-one-entry'], 11)
        self.assertEqual(self.data['summary']['flagCounts']['descending-native-levels'], 15)

    def test_recoveries_require_complete_native_duplicates_and_independent_script_boundaries(self):
        for raw_id, repair in RECOVERIES.items():
            key = f'sg_{raw_id}'
            override = self.data['speciesOverrides'][key]
            self.assertEqual(override['learnsetSource'], 'rom-recovered-prefix')
            provenance = override['learnsetProvenance']
            recovered = provenance['recovery']
            reference = self.data['sourceCatalogAudit']['johto'][str(recovered['referenceSpeciesId'])]
            self.assertEqual(provenance['rawLearnset'], reference['learnset'])
            self.assertEqual(reference['status'], 'validated')
            self.assertEqual(len(reference['learnset']), repair['entries'])
            self.assertEqual(int(recovered['stopOffset'], 16), repair['offset'] + repair['entries'] * 2)
            self.assertEqual(recovered['boundaryEvidence']['scriptOffset'], recovered['stopOffset'])
            self.assertEqual(recovered['boundaryEvidence']['eventPointerOffset'], hex(repair['eventPointerOffset']))
            self.assertNotIn('terminatorOffset', provenance)

    def test_shared_species_comparisons_do_not_apply_sigma_changes_to_firered(self):
        self.assertEqual(self.data['summary']['sharedComparisonCounts'],
                         {'identical': 173, 'order-only': 131, 'different-entries': 82})
        for key, comparison in self.data['sharedSpeciesComparisons'].items():
            source_id = str(comparison['sourceSpeciesId'])
            native = self.data['sourceCatalogAudit']['kanto'][source_id]['learnset']
            self.assertEqual(self.data['speciesOverrides'][key]['learnset'], native)
            self.assertEqual(comparison['canonicalSource'], 'kanto')

    def test_renamed_sigma_moves_have_separate_identity_and_raw_definitions(self):
        self.assertEqual(set(self.data['moveOverrides']), {str(1024 + move) for move in RENAMED_SIGMA_MOVES})
        self.assertNotIn('185', self.data['moveIdAliases']['johto'])
        for raw_id in RENAMED_SIGMA_MOVES:
            variant = self.data['moveOverrides'][str(1024 + raw_id)]
            raw = self.data['moveDefinitionDifferences'][str(raw_id)]['johto']
            self.assertEqual(variant['source'], 'johto')
            self.assertEqual(variant['sourceMoveId'], raw_id)
            for field in ['power', 'accuracy', 'pp', 'chance', 'priority', 'effect', 'target']:
                self.assertEqual(variant[field], raw[field])
            self.assertEqual(variant['sourceType'], raw['type'])
            self.assertEqual(variant['sourceCategory'], raw['categoryByte'])
            self.assertEqual(variant['moveProvenance']['rawHex'], raw['rawHex'])

    def test_name_collisions_and_placeholder_aliases_are_visible(self):
        groups = self.data['identityAliases']['johto']
        nidoran = next(group for group in groups if group['normalizedName'] == 'nidoran')
        self.assertEqual(nidoran['sourceSpeciesIds'], [29, 32])
        self.assertGreater(nidoran['distinctValidatedLearnsets'], 1)
        self.assertEqual(self.data['speciesAudit']['fr_29']['sourceSpeciesId'], 29)
        self.assertIn('placeholder-source-identity', self.data['speciesAudit']['sg_971']['flags'])


class RecoveryGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'Server/data/learnsets.json').read_text(encoding='utf-8'))

    def fixture(self):
        repair = RECOVERIES[933]
        rom = fake_rom(bytes(repair['offset'] + repair['entries'] * 2 + 32))
        reference = copy.deepcopy(self.data['sourceCatalogAudit']['johto']['76'])
        entries = reference['learnset']
        rom.b[repair['referenceOffset']:repair['referenceOffset'] + len(entries) * 2 + 2] = packed_entries(entries)
        rom.b[repair['offset']:repair['offset'] + len(entries) * 2] = packed_entries(entries, False)
        stop = repair['offset'] + len(entries) * 2
        prefix = bytes.fromhex(repair['eventScriptPrefix'])
        rom.b[stop:stop + len(prefix)] = prefix
        struct.pack_into('<I', rom.b, repair['eventPointerOffset'], 0x8000000 + stop)
        record = {'sourceSpeciesId': 933, 'offset': hex(repair['offset']), 'status': 'unsupported'}
        return rom, record, {76: reference}

    def test_repair_accepts_only_reviewed_native_prefix_with_event_boundary(self):
        rom, record, records = self.fixture()
        result = recover_reviewed_prefix(rom, 933, record, records)
        self.assertEqual(result['status'], 'recovered-native-prefix')
        self.assertEqual(result['learnset'], records[76]['learnset'])

    def test_similar_unreviewed_species_is_not_automatically_repaired(self):
        rom, record, records = self.fixture()
        self.assertEqual(recover_reviewed_prefix(rom, 935, record, records), record)

    def test_changed_prefix_or_script_pointer_cannot_be_published(self):
        for change in ['prefix', 'event-pointer']:
            with self.subTest(change=change):
                rom, record, records = self.fixture()
                offset = RECOVERIES[933]['offset'] if change == 'prefix' else RECOVERIES[933]['eventPointerOffset']
                rom.b[offset] ^= 1
                with self.assertRaises(ValueError):
                    recover_reviewed_prefix(rom, 933, record, records)


if __name__ == '__main__':
    unittest.main()
