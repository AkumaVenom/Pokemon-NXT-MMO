#!/usr/bin/env python3
"""Publish an edited native content pack. No ROM, Pillow, numpy or server dependencies.
Stop the world before publishing, then deploy matching Server and Client packs.
Stable map/species/item keys are persistence contracts: do not rename live IDs.
"""
from __future__ import annotations
import argparse,hashlib,json,os,tempfile
from pathlib import Path
try:
 from .verify_audio import verify as verify_audio
 from .publish_adventure import assemble as assemble_adventure
 from .publish_dialogue import assemble as assemble_dialogue
 from .publish_encounters import assemble as assemble_encounters
 from .publish_varieties import assemble as assemble_varieties
 from .publish_battle_mechanics import assemble as assemble_battle_mechanics
except ImportError:
 from verify_audio import verify as verify_audio
 from publish_adventure import assemble as assemble_adventure
 from publish_dialogue import assemble as assemble_dialogue
 from publish_encounters import assemble as assemble_encounters
 from publish_varieties import assemble as assemble_varieties
 from publish_battle_mechanics import assemble as assemble_battle_mechanics
ROOT=Path(__file__).resolve().parents[1]
def write_json(path:Path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f:
  json.dump(value,f,ensure_ascii=False,separators=(',',':'));tmp=Path(f.name)
 try:os.replace(tmp,path)
 finally:tmp.unlink(missing_ok=True)
def publish(world:dict,root:Path=ROOT):
 assemble_adventure(world,root)
 assemble_dialogue(world,root)
 assemble_encounters(world,root)
 assemble_varieties(world,root)
 # Adventure/learnset publishers rebuild move records, so bind reviewed battle
 # fields last before hashing/publishing the matching server/client pack.
 assemble_battle_mechanics(world,root)
 assets=root/'Client/app/assets'
 if world.get('format')!=1:raise ValueError('Unsupported world format')
 def asset(path):
  p=(assets/path).resolve()
  if not p.is_relative_to(assets.resolve()) or not p.is_file():raise ValueError('Missing or unsafe asset: '+str(path))
 for key,m in world['maps'].items():
  if key!=m['id'] or m['width']<1 or m['height']<1:raise ValueError('Invalid map ID/dimensions: '+key)
  for field in ('collision','elevation','behavior'):
   if len(m[field])!=m['width']*m['height']:raise ValueError('Invalid '+field+' grid: '+key)
  for field in ('image','ground','overlay'):
   if m.get(field):asset(m[field])
  if m.get('playable',True):
   x,y=m['spawn']
   if not(0<=x<m['width'] and 0<=y<m['height'])or m['collision'][y*m['width']+x]!=0:raise ValueError('Invalid safe spawn: '+key)
  for rows in m.get('encounters',{}).values():
   for row in rows:
    if row['species'] not in world['species'] or not 1<=row['min']<=row['max']<=100:raise ValueError('Invalid encounter: '+key)
 for key,s in world['species'].items():
  if key!=s['key']:raise ValueError('Mismatched species key: '+key)
  for field in ('front','back','shiny','backShiny','icon'):asset(s[field])
  for level,move in s['learnset']:
   if not 1<=level<=100 or str(move) not in world['moves']:raise ValueError('Invalid learnset: '+key)
 for entries in world['objects'].values():
  for sprite in entries.values():asset(sprite['image'])
 for key in world['homes'].values():
  if key not in world['maps']:raise ValueError('Invalid home')
 for key in world['starters']:
  if key not in world['species']:raise ValueError('Invalid starter')
 digest=hashlib.sha256();count=0
 for path in sorted(assets.rglob('*.png')):
  name=path.relative_to(assets).as_posix().encode();digest.update(len(name).to_bytes(4,'big'));digest.update(name);digest.update(hashlib.sha256(path.read_bytes()).digest());count+=1
 audio=verify_audio(root,world=world)
 world.pop('pack',None);world['assetDigest']=digest.hexdigest();world['audio']=audio
 world['pack']=hashlib.sha256(json.dumps(world,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()[:24]
 write_json(root/'Server/data/world.json',world)
 for k,m in world['maps'].items():write_json(assets/'world/maps'/f'{k}.json',{a:v for a,v in m.items() if a not in ('encounters','encounterSource','sourceHeader','encounterZones','encounterTerrain','encounterRates','encounterBinding')})
 client={k:world[k] for k in ('version','pack','assetDigest','audio','species','moves','objects','homes','starters','items','varietyPolicy')}
 fields=('id','name','region','width','height','mapType','spawn','bank','map','section','playable')
 client['maps']={k:{a:m[a] for a in fields} for k,m in world['maps'].items()}
 write_json(assets/'world/client.json',client)
 report=root/'Docs/ASSET_REPORT.json'
 if report.exists():
  r=json.loads(report.read_text(encoding='utf-8'));r.update({'pack':world['pack'],'assetDigest':world['assetDigest'],'assetPngFiles':count,'maps':len(world['maps']),'catalogEntries':len(world['species']),'mapsWithWalkableSpawn':sum(m.get('playable',True) for m in world['maps'].values())});write_json(report,r)
 print(f"Published pack {world['pack']}: {len(world['maps'])} maps, {len(world['species'])} catalog entries, {count} PNG assets, {audio['clipCount']} verified audio clips.")
 return world['pack']
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);args=p.parse_args();root=args.root.resolve();publish(json.loads((root/'Server/data/world.json').read_text(encoding='utf-8')),root)
if __name__=='__main__':main()
