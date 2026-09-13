#!/usr/bin/env python3
"""Audit ROM healing counters and publish a deterministic, ROM-free center registry.

Normal builds use the committed registry. Regeneration requires the two exact
source ROMs; no ARM/event script execution or ROM redistribution is involved.
"""
from __future__ import annotations
import argparse, collections, copy, hashlib, json, struct, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
 'kanto': {'sha256': '729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059', 'tileset': 0x2d4c54, 'heal': 0x1a65f0},
 'johto': {'sha256': '62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64', 'tileset': 0x2d4be4, 'heal': 0x1a6578},
}
# These custom reception layouts were checked against their native map images.
SPECIAL_RECEPTIONS = {'kanto_2_10': 'healing-station', 'johto_2_10': 'healing-station', 'johto_34_10': 'pokemon-center'}
NON_CENTER_NURSES = {'johto_34_20', 'johto_34_26', 'johto_34_36', 'johto_34_40'}
WATER = {16, 17, 18, 19, 21, 26, 27}


def passable(m, x, y):
 if not (0 <= x < m['width'] and 0 <= y < m['height']): return False
 j = y*m['width']+x
 return m['collision'][j] == 0 and m['behavior'][j] not in WATER and not any(o['x'] == x and o['y'] == y for o in m['objects'])


def reachable(m, start):
 """Conservative standing-floor flood fill, including elevation transitions."""
 if not passable(m, *start): return set()
 seen = {tuple(start)}; todo = collections.deque(seen)
 while todo:
  x, y = todo.popleft(); elevation = m['elevation'][y*m['width']+x]
  for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
   nx, ny = x+dx, y+dy
   if (nx, ny) in seen or not passable(m, nx, ny): continue
   target = m['elevation'][ny*m['width']+nx]
   if elevation not in (0, 15) and target not in (0, 15, elevation): continue
   seen.add((nx, ny)); todo.append((nx, ny))
 return seen


def counter_access(m, nurse):
 # The source counters face south. Never choose the inaccessible staff floor
 # simply because it is nearer to the NPC than the reception standing tile.
 front = (nurse['x'], nurse['y']+2)
 if not passable(m, *front): raise ValueError(f"No clear south-facing counter tile: {m['id']}:{nurse['id']}")
 floor = reachable(m, front)
 exits = [p['index'] for p in m['warps'] if (p['x'], p['y']) in floor]
 if not exits: raise ValueError(f"Counter has no floor path to a source doorway/stair: {m['id']}:{nurse['id']}")
 return list(front), exits


def apply_centers(world, registry):
 """Apply checked NPC corrections and metadata; safe to call more than once."""
 if registry.get('format') != 1: raise ValueError('Unsupported center registry format')
 for patch in registry.get('objectPatches', []):
  m = world['maps'][patch['map']]
  if patch['operation'] == 'add':
   existing = [o for o in m['objects'] if o['id'] == patch['object']['id']]
   if existing:
    if len(existing) != 1 or any(existing[0].get(k) != v for k, v in patch['object'].items()):
     raise ValueError('Center NPC addition conflicts with an existing object')
   else: m['objects'].append(copy.deepcopy(patch['object']))
  else: raise ValueError('Unknown center object correction')
 world['centers'] = copy.deepcopy(registry['centers'])
 for key, center in world['centers'].items():
  m = world['maps'][key]; objects = m['objects']; region = key.split('_')[0]
  if center['source']['region'] != region: raise ValueError('Center uses another region source')
  for npc in center['nurseNpcIds']:
   nurses = [o for o in objects if o['id'] == npc]
   if len(nurses) != 1 or nurses[0]['graphics'] != 64: raise ValueError(f'Invalid registered nurse {key}:{npc}')
   spot, _ = counter_access(m, nurses[0])
   if center['respawnByNpc'][str(npc)] != spot: raise ValueError('Center counter geometry changed')
  if not passable(m, *center['respawn']): raise ValueError('Unsafe center respawn')
 return world


def native_objects(rom, m):
 header = int(m['sourceHeader'], 16)
 if not rom.validptr(header+4): return []
 events = rom.ptr(header+4); count = rom.b[events]
 if not count: return []
 table = rom.ptr(events+4); result = []
 for index in range(count):
  p = table+index*24
  result.append({'id': rom.b[p], 'graphics': rom.b[p+1], 'x': struct.unpack_from('<h', rom.b, p+4)[0],
   'y': struct.unpack_from('<h', rom.b, p+6)[0], 'script': rom.ptr(p+16) if rom.validptr(p+16) else None,
   'event': p, 'flag': rom.u16(p+20), 'sourceObjectIndex': index})
 return result


def generate(world, rom_paths, assets):
 from extract_assets import Rom
 from extract_adventure_data import normalize_objects
 centers = {}; sources = {}; excluded = []; candidate_rooms = []; patches = []
 # This intact source reception has an empty object table. Its healing machine,
 # counter and south-facing nurse tile match the other Sigma center receptions.
 patches.append({'map': 'johto_8_0', 'operation': 'add',
  'object': {'id': 1, 'graphics': 64, 'x': 7, 'y': 2, 'movement': 8, 'trainerType': 0, 'addedBy': 'adventure-center-coverage'},
  'reason': 'Verified empty Sigma Lavender reception: add the region-native Nurse Joy at its existing healing desk.'})
 patches.append({'map': 'johto_1_58', 'operation': 'add',
  'object': {'id': 29, 'graphics': 64, 'x': 76, 'y': 2, 'movement': 8, 'trainerType': 0, 'addedBy': 'adventure-center-coverage'},
  'reason': 'Verified seventh healing reception in the recovered Sigma multiroom map has a desk but no nurse.'})
 working = copy.deepcopy(world)
 for region, path in rom_paths.items():
  r = Rom(path); profile = PROFILES[region]; digest = hashlib.sha256(r.b).hexdigest()
  if digest != profile['sha256']: raise ValueError(f'Wrong {region} ROM; exact audited source required')
  for key, m in working['maps'].items():
   if key.startswith(region+'_'): m['objects'] = normalize_objects(r, m)
  apply_centers(working, {'format': 1, 'objectPatches': [p for p in patches if p['map'].startswith(region+'_')], 'centers': {}})
  nurse_image = assets/'objects'/region/'64.png'
  # Decode from this region's ROM and compare exact output. This catches an
  # accidentally copied FireRed sheet in Sigma even when graphics IDs coincide.
  with tempfile.TemporaryDirectory(prefix='nxt-nurse-audit-') as tmp:
   metadata = r.objects(region, Path(tmp))
   decoded = Path(tmp)/metadata['64']['image']
   if decoded.read_bytes() != nurse_image.read_bytes(): raise ValueError(f'{region} nurse art does not match the source ROM')
  sources[region] = {'sha256': digest, 'nurseImage': f'objects/{region}/64.png',
   'nurseImageSha256': hashlib.sha256(nurse_image.read_bytes()).hexdigest(),
   'centerTileset': hex(profile['tileset']), 'commonHealScript': hex(profile['heal'])}
  prefix = b'\x6a\x5a\x04'+struct.pack('<I', profile['heal']+0x8000000)+b'\x6c\x02'
  for key, original in world['maps'].items():
   if not key.startswith(region+'_'): continue
   m = working['maps'][key]; hp = int(m['sourceHeader'], 16); layout = r.ptr(hp)
   secondary = r.ptr(layout+20); grid = r.ptr(layout+12)
   native = native_objects(r, original)
   native_nurses = [o for o in native if o['graphics'] == 64 and o['script'] is not None and r.raw(o['script'], len(prefix)) == prefix]
   desks = [(i % m['width'], i // m['width']) for i in range(m['width']*m['height'])
    if secondary == profile['tileset'] and r.u16(grid+i*2) & 1023 == 0x290]
   if secondary == profile['tileset']: candidate_rooms.append(key)
   if key in NON_CENTER_NURSES:
    excluded.append({'map': key, 'nurseNpcIds': [o['id'] for o in native_nurses], 'reason': 'Native hidden placeholder on non-center scenery; no healing desk.'}); continue
   if not desks and key not in SPECIAL_RECEPTIONS: continue
   nurses = [o for o in m['objects'] if o['graphics'] == 64]
   if not nurses: raise ValueError(f'Missing Nurse Joy at a verified center: {key}')
   inherited = [o for o in nurses if o.get('addedBy') != 'adventure-center-coverage']
   if {o['sourceObjectIndex'] for o in inherited} != {o['sourceObjectIndex'] for o in native_nurses}:
    raise ValueError(f'Unknown center nurse script: {key}')
   if key not in SPECIAL_RECEPTIONS and sorted(desks) != sorted((o['x'], o['y']) for o in nurses):
    raise ValueError(f'Nurse positions do not match native healing desks: {key}')
   positions = {}; exits = {}; evidence = []
   for nurse in nurses:
    front, access = counter_access(m, nurse); positions[str(nurse['id'])] = front; exits[str(nurse['id'])] = access
    source = next((o for o in native_nurses if o['sourceObjectIndex'] == nurse.get('sourceObjectIndex')), None)
    evidence.append({'npcId': nurse['id'], 'position': [nurse['x'], nurse['y']],
     'script': hex(source['script']) if source else None, 'event': hex(source['event']) if source else None,
     'origin': 'source-event' if source else 'verified-empty-reception'})
   centers[key] = {'name': m['name'], 'kind': SPECIAL_RECEPTIONS.get(key, 'pokemon-center'),
    'nurseNpcIds': [o['id'] for o in nurses], 'pcNpcIds': [], 'nursePcAccess': True,
    'respawn': positions[str(nurses[0]['id'])], 'respawnByNpc': positions, 'accessibleWarpsByNpc': exits,
    'source': {'region': region, 'header': m['sourceHeader'], 'secondaryTileset': hex(secondary), 'nurses': evidence}}
 registry = {'format': 1, 'sources': sources, 'centers': centers, 'objectPatches': patches,
  'audit': {'centerTilesetRooms': candidate_rooms, 'excludedNonCenterNurses': excluded,
   'coverage': {region: {'centerMaps': sum(k.startswith(region+'_') and v['kind']=='pokemon-center' for k,v in centers.items()),
    'healingStations': sum(k.startswith(region+'_') and v['kind']=='healing-station' for k,v in centers.items()),
    'nurses': sum(len(v['nurseNpcIds']) for k,v in centers.items() if k.startswith(region+'_'))} for region in rom_paths}}}
 apply_centers(working, registry)
 return registry


def main():
 parser = argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--firered', required=True); parser.add_argument('--sigma', required=True)
 parser.add_argument('--world', type=Path, default=ROOT/'Server/data/world.json')
 parser.add_argument('--output', type=Path, default=ROOT/'Server/data/centers.json')
 args = parser.parse_args(); world = json.loads(args.world.read_text(encoding='utf-8'))
 # Always derive source declarations from the committed raw extraction rather
 # than already patched runtime NPCs when regenerating this audit.
 raw = json.loads((ROOT/'Tools/extraction_manifest.json').read_text(encoding='utf-8'))
 world['maps'] = raw['maps']
 recovered = ROOT/'Server/data/interior_maps.json'
 if recovered.exists(): world['maps'].update(json.loads(recovered.read_text(encoding='utf-8')))
 registry = generate(world, {'kanto': args.firered, 'johto': args.sigma}, ROOT/'Client/app/assets')
 args.output.write_text(json.dumps(registry, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
 print(json.dumps(registry['audit']['coverage'], indent=2))


if __name__ == '__main__': main()
