#!/usr/bin/env python3
"""Audit every published learnset against the two exact, reviewed source ROMs.

This stdlib-only importer follows engine-referenced pointer tables. Source order
and repeated levels are data, not validation errors. It neither sorts native
records nor manufactures level-one moves. The two reviewed missing-terminator
repairs require an exact, complete, terminated duplicate in the same ROM.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import struct
from pathlib import Path

from extract_adventure_data import Rom, text

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'kanto': {
        'sha256': '729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059',
        'bytes': 16777216, 'table': 0x25d824, 'tableEntries': 412,
        'engineStart': 0x3e9f4, 'engineLoad': 0x3ea1c,
        'engineReferences': [0x3ea90, 0x3eb24, 0x3eb98, 0x43ddc, 0x43e34, 0x43f98],
        'bulbasaurOffset': 0x257504, 'label': 'FireRed USA/Europe Rev 1',
    },
    'johto': {
        'sha256': '62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64',
        'bytes': 17632785, 'table': 0xa74f64, 'tableEntries': 1340,
        'engineStart': 0x3e9e0, 'engineLoad': 0x3ea08,
        'engineReferences': [0x3ea7c, 0x3eb10, 0x3eb84, 0x43dc8, 0x43e20, 0x43f84],
        'bulbasaurOffset': 0x257494, 'label': 'Ultra Shiny Gold Sigma Completo 1.5.0',
    },
}
# Deliberately narrow. A matching prefix alone never enables arbitrary recovery.
RECOVERIES = {
    933: {'offset': 0xa4ae00, 'entries': 13, 'referenceSpeciesId': 76,
          'referenceOffset': 0x257acc, 'boundaryWord': 0x000f,
          'eventPointerOffset': 0x7fd530, 'eventArrayOffset': 0x7fd238,
          'eventIndex': 31, 'eventKind': 'object-script', 'eventScriptPrefix': '0f000624a508090202'},
    943: {'offset': 0xa4f448, 'entries': 14, 'referenceSpeciesId': 338,
          'referenceOffset': 0x259012, 'boundaryWord': 0x242b,
          'eventPointerOffset': 0x7e3778, 'eventArrayOffset': 0x7e372c,
          'eventIndex': 4, 'eventKind': 'coordinate-script', 'eventScriptPrefix': '2b2408070178f4a408'},
}
RENAMED_SIGMA_MOVES = (183, 210, 237, 294, 295, 297, 346)
ENCODING = {'entryBytes': 2, 'byteOrder': 'little', 'levelShift': 9,
            'moveMask': 511, 'terminator': 65535, 'maximumEntries': 128}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def packed_entries(entries, terminated=True):
    values = [(level << 9) | move for level, move in entries]
    if terminated:
        values.append(65535)
    return struct.pack('<' + 'H' * len(values), *values)


def parse_learnset(r, start, supported_moves=None, max_entries=128):
    """Decode through 0xffff, preserving native sequence and precise failure.

    A valid prefix is diagnostic only; it is never returned as a valid learnset.
    Moves outside a supplied catalog, invalid levels, invalid pointers, and a
    missing terminator fail independently of repeated/descending level order.
    """
    supported = set(range(1, 355)) if supported_moves is None else {int(v) for v in supported_moves}
    entries = []
    for index in range(max_entries):
        offset = start + index * 2
        try:
            value = r.u16(offset)
        except (ValueError, IndexError, struct.error):
            return {'status': 'unsupported', 'reason': 'record-exceeds-rom',
                    'failureOffset': hex(offset), 'failureIndex': index, 'decodedPrefix': entries}
        if value == 65535:
            return {'status': 'validated', 'learnset': entries, 'terminatorOffset': hex(offset),
                    'rawSha256': digest(r.raw(start, index * 2 + 2)), 'rawBytes': index * 2 + 2}
        level, move = value >> 9, value & 511
        if not 1 <= level <= 100 or move not in supported:
            return {'status': 'unsupported', 'reason': 'invalid-level' if not 1 <= level <= 100 else 'unsupported-move',
                    'failureOffset': hex(offset), 'failureIndex': index, 'rawWord': value,
                    'decodedValue': [level, move], 'decodedPrefix': entries}
        entries.append([level, move])
    return {'status': 'unsupported', 'reason': 'unterminated-learnset',
            'failureOffset': hex(start + max_entries * 2), 'failureIndex': max_entries,
            'decodedPrefix': entries}


def validate_profile(r, tag, manifest):
    profile = PROFILES[tag]
    actual = digest(r.b)
    expected = next(source['sha256'] for source in manifest['sources'] if source['source'] == tag)
    if actual != profile['sha256'] or actual != expected or len(r.b) != profile['bytes']:
        raise ValueError(f'{tag}: ROM differs from the reviewed source revision')
    if r.raw(profile['engineStart'], 16).hex() != 'f0b557464e464546e0b481b080460b21':
        raise ValueError(f'{tag}: learnset assignment engine signature differs')
    # Thumb LDR r0,[pc,#112], followed by species*4 and a pointer/halfword read.
    if r.raw(profile['engineLoad'], 10).hex() != '1c48a600301800680188':
        raise ValueError(f'{tag}: active table access instruction differs')
    for literal in profile['engineReferences']:
        if r.ptr(literal) != profile['table']:
            raise ValueError(f'{tag}: learnset table engine reference differs at {literal:#x}')
    table = profile['table']
    if r.ptr(table) != profile['bulbasaurOffset'] or r.ptr(table + 4) != profile['bulbasaurOffset']:
        raise ValueError(f'{tag}: species NONE/Bulbasaur table anchors differ')
    if r.raw(profile['bulbasaurOffset'], 6) != struct.pack('<HHH', 545, 2093, 3657):
        raise ValueError(f'{tag}: native Bulbasaur entry signature differs')
    if r.validptr(table + profile['tableEntries'] * 4):
        raise ValueError(f'{tag}: reviewed pointer table boundary differs')
    return {key: (hex(value) if key in {'table', 'engineStart', 'engineLoad', 'bulbasaurOffset'} else value)
            for key, value in profile.items() if key != 'engineReferences'} | {
                'engineReferences': [hex(value) for value in profile['engineReferences']],
                'encoding': ENCODING,
                'engineInitialMoves': 'Scan native order; stop at first level above the Pokemon level or 0xffff.',
            }


def entry_flags(entries):
    flags = []
    if not entries:
        flags.append('empty-native-learnset')
    elif not any(level == 1 for level, _ in entries):
        flags.append('no-level-one-entry')
    if any(left[0] > right[0] for left, right in zip(entries, entries[1:])):
        flags.append('descending-native-levels')
    if len({level for level, _ in entries}) < len(entries):
        flags.append('repeated-levels')
    if len({tuple(entry) for entry in entries}) < len(entries):
        flags.append('repeated-level-and-move')
    return flags


def recover_reviewed_prefix(r, source_id, record, all_records):
    repair = RECOVERIES.get(source_id)
    if not repair or record['status'] != 'unsupported' or int(record['offset'], 16) != repair['offset']:
        return record
    reference = all_records[repair['referenceSpeciesId']]
    if reference['status'] != 'validated' or int(reference['offset'], 16) != repair['referenceOffset']:
        raise ValueError(f'Sigma {source_id}: native recovery reference differs')
    entries = reference['learnset']
    count = repair['entries']
    if (len(entries) != count
            or r.raw(repair['referenceOffset'], count * 2 + 2) != packed_entries(entries)
            or r.raw(repair['offset'], count * 2) != packed_entries(entries, False)):
        raise ValueError(f'Sigma {source_id}: full terminated native-list prefix differs')
    boundary = repair['offset'] + count * 2
    if r.u16(boundary) != repair['boundaryWord']:
        raise ValueError(f'Sigma {source_id}: reviewed damaged boundary differs')
    prefix = bytes.fromhex(repair['eventScriptPrefix'])
    if r.ptr(repair['eventPointerOffset']) != boundary or r.raw(boundary, len(prefix)) != prefix:
        raise ValueError(f'Sigma {source_id}: independently referenced event-script boundary differs')
    matches = [i for i, other in all_records.items()
               if other['status'] == 'validated' and other['learnset'] == entries]
    return {key: value for key, value in record.items() if key not in {'decodedPrefix'}} | {
        'status': 'recovered-native-prefix', 'learnset': entries,
        'rawSha256': digest(r.raw(repair['offset'], count * 2)), 'rawBytes': count * 2,
        'recovery': {
            'method': 'terminated-native-prefix-equivalence', 'nativeTerminatorMissing': True,
            'referenceSpeciesId': repair['referenceSpeciesId'], 'referenceOffset': hex(repair['referenceOffset']),
            'referenceTerminatorOffset': reference['terminatorOffset'], 'referenceRawSha256': reference['rawSha256'],
            'matchingSourceSpeciesIds': matches, 'entries': count,
            'stopOffset': hex(boundary), 'rawBoundaryWord': repair['boundaryWord'],
            'boundaryEvidence': {'kind': repair['eventKind'],
                                 'eventPointerOffset': hex(repair['eventPointerOffset']),
                                 'eventArrayOffset': hex(repair['eventArrayOffset']),
                                 'eventIndex': repair['eventIndex'], 'scriptOffset': hex(boundary)},
            'limitation': 'The published list restores a missing terminator using an exact terminated native duplicate; the damaged original engine would overread.',
        },
    }


def read_source_catalog(r, tag, manifest, supported_moves):
    profile = PROFILES[tag]
    result = {}
    for raw_id, species in sorted(manifest['catalogs'][tag].items(), key=lambda item: int(item[0])):
        source_id = int(raw_id)
        out = {'sourceSpeciesId': source_id, 'name': species['name']}
        if not 0 < source_id < profile['tableEntries']:
            result[source_id] = out | {'status': 'unsupported', 'reason': 'outside-active-learnset-table'}
            continue
        pointer_offset = profile['table'] + source_id * 4
        out['pointerOffset'] = hex(pointer_offset)
        try:
            start = r.ptr(pointer_offset)
            out['offset'] = hex(start)
            out.update(parse_learnset(r, start, supported_moves))
        except (ValueError, IndexError, struct.error):
            out.update(status='unsupported', reason='invalid-learnset-pointer')
        result[source_id] = out
    if tag == 'johto':
        for source_id in RECOVERIES:
            result[source_id] = recover_reviewed_prefix(r, source_id, result[source_id], result)
    starts = {int(record['offset'], 16) for record in result.values() if 'offset' in record}
    for record in result.values():
        if 'learnset' not in record:
            continue
        flags = entry_flags(record['learnset'])
        if record['name'].casefold() in {'temp', 'unused', '??????????'}:
            flags.append('placeholder-source-identity')
        start = int(record['offset'], 16)
        stop = start + len(record['learnset']) * 2
        interior = [hex(value) for value in sorted(starts) if start < value < stop]
        if interior:
            flags.append('overlaps-another-native-list')
            record['interiorListPointers'] = interior
        record['flags'] = flags
    return result


def normalized_name(name):
    # Existing world importer normalization, retained ONLY to audit collisions.
    return re.sub(r'[^a-z0-9]', '', name.lower())


def identity_aliases(world, manifest, catalogs):
    published = collections.defaultdict(list)
    for key, species in world['species'].items():
        published[normalized_name(species['name'])].append(key)
    out = {}
    for tag, source in manifest['catalogs'].items():
        groups = collections.defaultdict(list)
        for raw_id, species in source.items():
            norm = normalized_name(species['name'])
            if norm in published:
                groups[norm].append(int(raw_id))
        out[tag] = []
        for norm, ids in sorted(groups.items()):
            if len(ids) < 2:
                continue
            out[tag].append({'normalizedName': norm, 'publishedKeys': published[norm],
                             'sourceSpeciesIds': sorted(ids),
                             'sourceNames': sorted({source[str(i)]['name'] for i in ids}),
                             'distinctValidatedLearnsets': len({tuple(map(tuple, catalogs[tag][i]['learnset']))
                                                               for i in ids if 'learnset' in catalogs[tag][i]}),
                             'policy': 'Canonical source and sourceSpeciesId control publication; name aliases do not replace a published identity.'})
    return out


def read_moves(r):
    names, table = r.ptr(0x148), r.ptr(0x1cc)
    records = {}
    for move in range(1, 355):
        raw = r.raw(table + move * 12, 12)
        source_name = text(r.raw(names + move * 13, 13)).strip()
        records[move] = {'id': move, 'name': source_name.title(), 'sourceName': source_name,
                         'effect': raw[0], 'power': raw[1], 'type': raw[2], 'accuracy': raw[3],
                         'pp': raw[4], 'chance': raw[5], 'target': raw[6],
                         'priority': struct.unpack('b', raw[7:8])[0], 'flags': raw[8],
                         'categoryByte': raw[10], 'rawHex': raw.hex(),
                         'offset': hex(table + move * 12), 'nameOffset': hex(names + move * 13)}
    return records


def extract(firered, sigma, root=ROOT):
    world = json.loads((root / 'Server/data/world.json').read_text(encoding='utf-8'))
    manifest = json.loads((root / 'Tools/extraction_manifest.json').read_text(encoding='utf-8'))
    out = {'format': 1, 'sources': {}, 'speciesOverrides': {}, 'speciesAudit': {},
           'sourceCatalogAudit': {}, 'sharedSpeciesComparisons': {}, 'identityAliases': {},
           'moveDefinitionDifferences': {}, 'moveOverrides': {},
           'moveIdAliases': {'johto': {str(move): 1024 + move for move in RENAMED_SIGMA_MOVES}},
           'unsupported': [], 'policy': {
               'canonicalSpecies': 'The stable published key retains its canonical ROM source and exact sourceSpeciesId in every region.',
               'nativeOrder': 'Keep native record order and repeated levels. Do not sort, deduplicate, or add invented level-one moves.',
               'recovery': 'Only two hash-pinned missing-terminator records may use a complete, byte-identical terminated native list as the boundary witness.',
               'moveDefinitions': 'The seven renamed Sigma move identities receive IDs 1024 + rawMoveId only in Sigma species learnsets. All raw numeric source rows remain in provenance. FireRed definitions remain the baseline for unchanged move identities; learnset extraction is not full Sigma battle emulation.',
               'sourceTypeNine': 'Preserve source type 9. The Sigma engine-referenced type-name table still labels slot 9 ???; modern Fairy type 18 and its matchup chart are not inferred from renamed move or species names.',
               'forms': 'Published forms use their own exact source index. Normalized-name aliases and unpublished forms are retained in the source audit without changing stable catalog identities.',
           }}
    catalogs, move_catalogs = {}, {}
    for tag, path in [('kanto', firered), ('johto', sigma)]:
        r = Rom(path)
        out['sources'][tag] = validate_profile(r, tag, manifest)
        catalogs[tag] = read_source_catalog(r, tag, manifest, world['moves'])
        move_catalogs[tag] = read_moves(r)
        out['sourceCatalogAudit'][tag] = {str(key): value for key, value in catalogs[tag].items()}
    for move in RENAMED_SIGMA_MOVES:
        native = move_catalogs['johto'][move]
        fields = {field: native[field] for field in ['name', 'effect', 'power', 'type', 'accuracy', 'pp', 'chance', 'target', 'priority']}
        fields.update(id=1024 + move, source='johto', sourceMoveId=move,
                      sourceName=native['sourceName'], sourceType=native['type'],
                      sourceCategory=native['categoryByte'], category=native['categoryByte'],
                      sourceFlags=native['flags'], moveProvenance={
                          'source': 'johto', 'sha256': PROFILES['johto']['sha256'],
                          'offset': native['offset'], 'nameOffset': native['nameOffset'],
                          'rawHex': native['rawHex']})
        out['moveOverrides'][str(1024 + move)] = fields
    for key, species in sorted(world['species'].items()):
        tag, source_id = species['source'], species['sourceId']
        record = catalogs[tag][source_id]
        if record['name'] != species['name']:
            raise ValueError(f'{key}: canonical source identity differs from the extraction manifest')
        audit = {'name': species['name'], 'source': tag, 'sourceSpeciesId': source_id,
                 'table': out['sources'][tag]['table']} | record
        audit.pop('learnset', None)
        out['speciesAudit'][key] = audit
        if record['status'] not in {'validated', 'recovered-native-prefix'}:
            out['unsupported'].append({'species': key} | audit)
            continue
        provenance = {'source': tag, 'sourceSpeciesId': source_id,
                      'table': out['sources'][tag]['table'], 'sha256': out['sources'][tag]['sha256']}
        for field in ['pointerOffset', 'offset', 'terminatorOffset', 'rawSha256', 'rawBytes', 'flags', 'recovery']:
            if field in record:
                provenance[field] = record[field]
        if tag == 'johto':
            provenance['rawLearnset'] = record['learnset']
        aliases = out['moveIdAliases'].get(tag, {})
        learnset = [[level, aliases.get(str(move), move)] for level, move in record['learnset']]
        out['speciesOverrides'][key] = {
            'learnset': learnset,
            'learnsetSource': 'rom' if record['status'] == 'validated' else 'rom-recovered-prefix',
            'learnsetProvenance': provenance,
        }
        if tag == 'kanto':
            other = catalogs['johto'].get(source_id)
            if not other or other['name'] != species['name'] or 'learnset' not in other:
                raise ValueError(f'{key}: shared-source identity unavailable; do not guess a name alias')
            equal = record['learnset'] == other['learnset']
            same_pairs = sorted(record['learnset']) == sorted(other['learnset'])
            out['sharedSpeciesComparisons'][key] = {
                'name': species['name'], 'sourceSpeciesId': source_id,
                'result': 'identical' if equal else 'order-only' if same_pairs else 'different-entries',
                'kantoOffset': record['offset'], 'johtoOffset': other['offset'],
                'canonicalSource': 'kanto', 'johtoFlags': other['flags'],
            }
    out['identityAliases'] = identity_aliases(world, manifest, catalogs)
    for move, firered_move in move_catalogs['kanto'].items():
        sigma_move = move_catalogs['johto'][move]
        name_changed = firered_move['name'].casefold() != sigma_move['name'].casefold()
        changed = [field for field in ['effect', 'power', 'type', 'accuracy', 'pp', 'chance', 'target', 'priority', 'flags', 'categoryByte']
                   if firered_move[field] != sigma_move[field]]
        if name_changed or firered_move['rawHex'] != sigma_move['rawHex']:
            out['moveDefinitionDifferences'][str(move)] = {
                'nameChanged': name_changed, 'changedFields': changed,
                'kanto': firered_move, 'johto': sigma_move,
            }
    counts = collections.Counter(record['status'] for record in out['speciesAudit'].values())
    flags = collections.Counter(flag for record in out['speciesAudit'].values() for flag in record.get('flags', []))
    comparisons = collections.Counter(record['result'] for record in out['sharedSpeciesComparisons'].values())
    out['summary'] = {'publishedSpecies': len(world['species']), 'publishedOverrides': len(out['speciesOverrides']),
                      'statusCounts': dict(sorted(counts.items())), 'flagCounts': dict(sorted(flags.items())),
                      'sharedSpecies': len(out['sharedSpeciesComparisons']), 'sharedComparisonCounts': dict(sorted(comparisons.items())),
                      'sourceCatalogEntries': {tag: len(records) for tag, records in catalogs.items()},
                      'moveDefinitionsDiffering': len(out['moveDefinitionDifferences']),
                      'moveNamesDiffering': sum(record['nameChanged'] for record in out['moveDefinitionDifferences'].values()),
                      'namespacedSigmaMoves': len(out['moveOverrides']),
                      'sigmaSpeciesUsingRenamedMoves': sum(any(move >= 1024 for _, move in record['learnset'])
                                                          for record in out['speciesOverrides'].values())}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firered', type=Path)
    parser.add_argument('sigma', type=Path)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true', help='Re-extract and compare without writing')
    args = parser.parse_args()
    result = extract(args.firered, args.sigma, args.root)
    destination = args.root / 'Server/data/learnsets.json'
    if args.check:
        existing = json.loads(destination.read_text(encoding='utf-8'))
        if existing != result:
            raise ValueError('Shipped learnset audit differs from fresh ROM extraction')
    else:
        destination.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(destination), 'checked': args.check, **result['summary']}, indent=2))


if __name__ == '__main__':
    main()
