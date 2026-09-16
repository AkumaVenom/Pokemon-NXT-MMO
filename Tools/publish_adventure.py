#!/usr/bin/env python3
"""Assemble audited adventure metadata using bundled data only (no ROM required)."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

try:
    from .repair_interiors import apply as apply_interiors
    from .repair_interiors import apply_navigation
    from .prepare_centers import apply_centers
    from .publish_learnsets import apply as apply_learnsets, extend_audio as extend_move_audio
except ImportError:
    from repair_interiors import apply as apply_interiors
    from repair_interiors import apply_navigation
    from prepare_centers import apply_centers
    from publish_learnsets import apply as apply_learnsets, extend_audio as extend_move_audio


def read(root, name):
    return json.loads((root / 'Server/data' / (name + '.json')).read_text(encoding='utf-8'))


def assemble(world: dict, root: Path) -> None:
    """Deterministic additive content upgrade; never reads or edits player saves."""
    root = Path(root)
    apply_interiors(world, root)
    recovered = read(root, 'interior_maps')
    for key, native in recovered.items():
        # Older staged packs may already contain recovered rooms without music metadata.
        if 'musicId' in native:
            world['maps'][key]['musicId'] = native['musicId']
    native = read(root, 'adventure_rom')
    if native.get('format') != 1 or set(native['normalizedObjects']) != set(world['maps']):
        raise ValueError('Adventure NPC audit must cover every world map')
    for key, objects in native['normalizedObjects'].items():
        world['maps'][key]['objects'] = copy.deepcopy(objects)
    apply_centers(world, read(root, 'centers'))
    apply_navigation(world, root)
    world['adventureRom'] = {k: copy.deepcopy(v) for k, v in native.items()
                             if k not in ('normalizedObjects', 'speciesOverrides')}
    world['adventure'] = read(root, 'adventure')
    for key, item in world['adventure'].get('keyItems', {}).items():
        required = {'name', 'price', 'keyItem', 'buyable', 'tradable', 'description'}
        if set(item) != required or item['price'] != 0 or item['keyItem'] is not True or item['buyable'] is not False or item['tradable'] is not False:
            raise ValueError('Invalid story key item: ' + key)
        if key in world['items'] and world['items'][key] != item:
            raise ValueError('Story key item conflicts with an existing item: ' + key)
        world['items'][key] = copy.deepcopy(item)
    for event in world['adventure'].get('storyEvents', []):
        m = world['maps'].get(event.get('map'))
        if not m:
            raise ValueError('Story event has no map: ' + str(event.get('id')))
        obj = next((o for o in m.get('objects', []) if o.get('id') == event.get('npc')), None)
        if not obj or obj.get('graphics') != event.get('graphics'):
            raise ValueError('Story event object binding mismatch: ' + str(event.get('id')))
        if 'storyEvent' in obj and obj['storyEvent'] != event['id']:
            raise ValueError('Story object already has another event: ' + m['id'])
        obj['storyEvent'] = event['id']
    for key, fields in native.get('speciesOverrides', {}).items():
        if key not in world['species'] or set(fields) - {'learnset', 'learnsetSource', 'learnsetProvenance'}:
            raise ValueError('Invalid ROM species override: ' + key)
        world['species'][key].update(copy.deepcopy(fields))
    for key, item in native.get('items', {}).items():
        # Stock and prices are explicit MMO rules, not extracted original shop scripts.
        price = 2100 if key in {'firestone', 'waterstone', 'thunderstone', 'leafstone'} else 4000
        world['items'][key] = {**copy.deepcopy(item), 'price': price, 'priceSource': 'mmo-adventure'}
    additions = read(root, 'species_additions')
    if additions.get('format') != 1:
        raise ValueError('Unsupported additive species catalog')
    for key, profile in additions['species'].items():
        if key in world['species'] and (world['species'][key]['source'], world['species'][key]['sourceId']) != (profile['source'], profile['sourceId']):
            raise ValueError('Additive species identity conflict: ' + key)
        world['species'].setdefault(key, copy.deepcopy(profile))
    apply_learnsets(world, root)
    world['version'] = '0.6.5-alpha'
    validate(world)
    extend_audio(world, root)


def validate(world: dict) -> None:
    maps, species, moves = world['maps'], world['species'], world['moves']
    native = world['adventureRom']
    for key, m in maps.items():
        ids = [o['id'] for o in m.get('objects', [])]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate visible NPC identity: ' + key)
    for key, trainer in native['trainers'].items():
        m = maps.get(trainer['map'])
        if m is None or trainer['npc'] not in {o['id'] for o in m.get('objects', [])}:
            raise ValueError('Trainer has no visible NPC: ' + key)
        if not 1 <= len(trainer['team']) <= 6:
            raise ValueError('Invalid trainer party: ' + key)
        for mon in trainer['team']:
            if mon['species'] not in species or not 1 <= mon['level'] <= 100:
                raise ValueError('Invalid trainer Pokemon: ' + key)
            if any(str(move) not in moves for move in mon.get('moves', [])):
                raise ValueError('Unsupported trainer move: ' + key)
    gyms = native['gyms']
    if len(gyms) != 16 or {(g['source'], g['order']) for g in gyms} != {
            (region, order) for region in ('kanto', 'johto') for order in range(1, 9)}:
        raise ValueError('Expected eight ordered gyms in each region')
    for gym in gyms:
        trainer = native['trainers'].get(gym['trainer'])
        if not trainer or (trainer['map'], trainer['npc']) != (gym['map'], gym['npc']):
            raise ValueError('Gym leader binding mismatch: ' + gym['name'])
    story = world.get('adventure', {}).get('storyEvents', [])
    ids = [event.get('id') for event in story]
    if len(ids) != len(set(ids)) or any(not isinstance(event_id, str) or not event_id for event_id in ids):
        raise ValueError('Story event ids must be unique non-empty strings')
    badges = world.get('adventure', {}).get('badgeNames', {})
    for event in story:
        m = maps.get(event.get('map'));obj = next((o for o in (m or {}).get('objects', []) if o.get('id') == event.get('npc')), None)
        if not obj or obj.get('graphics') != event.get('graphics') or obj.get('storyEvent') != event['id']:
            raise ValueError('Invalid published story object: ' + event['id'])
        if event.get('species') not in species or not 1 <= event.get('level', 0) <= 100:
            raise ValueError('Invalid story encounter Pokemon: ' + event['id'])
        if event.get('requiredBadge') not in badges:
            raise ValueError('Invalid story badge requirement: ' + event['id'])
        item = world['items'].get(event.get('requiredItem'))
        if not item or not item.get('keyItem') or item.get('buyable', True) or item.get('tradable', True):
            raise ValueError('Invalid story key-item binding: ' + event['id'])
        if any(str(move) not in moves for move in event.get('moves', [])) or len(event.get('moves', [])) > 4:
            raise ValueError('Invalid story encounter moves: ' + event['id'])
    for key, choices in native['evolutions'].items():
        if key not in species:
            raise ValueError('Unknown evolving species: ' + key)
        for choice in choices:
            if choice['target'] not in species:
                raise ValueError('Unknown evolution target: ' + key)
            if choice['method'] == 'level' and not 1 <= choice['level'] <= 100:
                raise ValueError('Invalid evolution level: ' + key)
            if choice['method'] == 'stone' and choice['item'] not in world['items']:
                raise ValueError('Missing evolution item: ' + key)


def extend_audio(world: dict, root: Path) -> None:
    path = root / 'Client/app/assets/audio/catalog.json'
    catalog = json.loads(path.read_text(encoding='utf-8'))
    changed = extend_move_audio(world, catalog)
    for key, banks in read(root, 'species_additions').get('audio', {}).items():
        for bank, clip in banks.items():
            if bank not in ('cries', 'reverseCries') or key not in world['species'] or clip not in catalog['clips']:
                raise ValueError('Invalid restored species audio binding: ' + key)
            changed |= catalog[bank].get(key) != clip
            catalog[bank][key] = clip
    for key, m in world['maps'].items():
        if key in catalog['mapMusic'] and key in catalog['mapModes'] and 'musicId' not in m:
            continue
        if 'musicId' not in m:
            raise ValueError('Missing native map music metadata: ' + key)
        song = m['musicId']
        mode = 'inherit' if song == 65535 else 'silence' if song == 0 else 'song'
        clip = None if mode != 'song' else f"{key.split('_')[0]}.song.{song}"
        if clip is not None and clip not in catalog['clips']:
            raise ValueError(f'Unrendered native map music: {key}: {clip}')
        changed |= catalog['mapMusic'].get(key) != clip or catalog['mapModes'].get(key) != mode
        catalog['mapMusic'][key], catalog['mapModes'][key] = clip, mode
    if changed:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            json.dump(catalog, stream, ensure_ascii=False, separators=(',', ':'))
            temporary = Path(stream.name)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
