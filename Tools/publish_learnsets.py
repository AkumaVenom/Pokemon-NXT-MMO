"""Apply the bundled, ROM-audited learnsets without reading player saves or ROMs."""
from __future__ import annotations

import copy
import json
from pathlib import Path


def apply(world: dict, root: Path) -> None:
    data = json.loads((Path(root) / 'Server/data/learnsets.json').read_text(encoding='utf-8'))
    overrides = data.get('speciesOverrides', {})
    if data.get('format') != 1 or set(overrides) != set(world['species']):
        raise ValueError('Native learnset audit must cover every published species')
    if data.get('unsupported'):
        raise ValueError('Native learnset audit contains unsupported published species')
    for key, move in data.get('moveOverrides', {}).items():
        if int(key) != move['id'] or move['id'] != 1024 + move['sourceMoveId'] or move['source'] != 'johto':
            raise ValueError('Invalid namespaced native move: ' + key)
        world['moves'][key] = copy.deepcopy(move)
    for key, fields in overrides.items():
        if set(fields) - {'learnset', 'learnsetSource', 'learnsetProvenance'}:
            raise ValueError('Unexpected native species override fields: ' + key)
        species = world['species'][key]
        provenance = fields['learnsetProvenance']
        if (provenance['source'], provenance['sourceSpeciesId']) != (species['source'], species['sourceId']):
            raise ValueError('Native learnset source identity changed: ' + key)
        if fields['learnsetSource'] not in {'rom', 'rom-recovered-prefix'}:
            raise ValueError('Learnset must have native provenance: ' + key)
        for level, move in fields['learnset']:
            if not 1 <= level <= 100 or str(move) not in world['moves']:
                raise ValueError('Invalid native learnset entry: ' + key)
        species.update(copy.deepcopy(fields))
    # Shared FireRed species retain their stable canonical profile in either region.
    # Explicit Sigma-only trainer moves use the same identity namespace as players.
    aliases = data.get('moveIdAliases', {})
    for trainer in world.get('adventureRom', {}).get('trainers', {}).values():
        for mon in trainer['team']:
            source = world['species'][mon['species']]['source']
            mapping = aliases.get(source, {})
            mon['moves'] = [mapping.get(str(move), move) for move in mon.get('moves', [])]
    world['learnsets'] = {key: copy.deepcopy(data[key]) for key in ('format', 'sources', 'policy', 'summary', 'moveIdAliases')}


def extend_audio(world: dict, catalog: dict) -> bool:
    """Bind variants to Sigma's existing native move scripts in either region."""
    changed = False
    for source, aliases in world.get('learnsets', {}).get('moveIdAliases', {}).items():
        for native_id, published_id in aliases.items():
            native = catalog['moveSounds'][source][native_id]
            for bank in catalog['moveSounds'].values():
                key = str(published_id)
                changed |= bank.get(key) != native
                bank[key] = copy.deepcopy(native)
    return changed
