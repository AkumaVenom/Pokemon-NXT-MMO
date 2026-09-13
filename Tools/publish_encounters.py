"""Deterministic regional encounter publishing. No ROM or network required.

Every map must have an explicit binding (including deliberate no-encounter maps).
This runs AFTER interior/adventure assembly and BEFORE the pack hash is computed.
"""
from __future__ import annotations
import copy,hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def assemble(world,root=ROOT):
 root=Path(root);sources={};digests={}
 for game,name in [('firered','encounters_firered'),('crystal','encounters_crystal'),('bindings','encounter_bindings')]:
  raw=(root/'Server/data'/f'{name}.json').read_bytes();value=json.loads(raw)
  if value.get('format')!=1:raise ValueError('Unsupported encounter catalog: '+name)
  sources[game]=value;digests[name]=hashlib.sha256(raw).hexdigest()
 bindings=sources['bindings']['maps'];maps=world['maps']
 if set(bindings)!=set(maps):raise ValueError('Encounter bindings must cover every map: missing='+str(sorted(set(maps)-set(bindings)))+', stale='+str(sorted(set(bindings)-set(maps))))
 def resolve(binding):
  ref=binding.get('table');area={'encounters':{},'encounterTerrain':binding.get('terrain','tiles'),'encounterSource':'none','encounterBinding':ref}
  if ref:
   game,key=ref.split(':',1)
   if game not in ('firered','crystal') or key not in sources[game]['tables']:raise ValueError('Unknown encounter table '+ref)
   table=sources[game]['tables'][key];area.update(encounters=copy.deepcopy(table['encounters']),encounterSource=game,encounterTerrain=binding.get('terrain',table.get('encounterTerrain','tiles')))
   if 'rates' in table:area['encounterRates']=copy.deepcopy(table['rates'])
  return area
 for key,m in maps.items():
  for field in ('encounters','encounterSource','encounterZones','encounterTerrain','encounterRates','encounterBinding'):m.pop(field,None)
  rule=bindings[key];m.update(resolve(rule))
  if rule.get('zones'):m['encounterZones']=[dict(resolve(z),rect=z['rect']) for z in rule['zones']]
 # Import the very same validator used at server startup; no divergent rules.
 sys.path.insert(0,str(root/'Server'))
 from nxt.encounters import validate_encounter_map
 for m in maps.values():validate_encounter_map(m,world['species'])
 world['encounterPolicy']={'format':1,'sources':digests,'clock':'server-local','crystalPeriods':{'morning':[4,10],'day':[10,18],'night':[[18,24],[0,4]]},'fallback':'none','cadence':'existing configured MMO step chance; canonical ordered slot and level distributions','events':'ordinary walking and Surf pools only; special scripts/fishing/headbutt/contest not added'}
 report={'version':world['version'],'mapsAudited':len(maps),'nativeFireRedTables':len(sources['firered']['tables']),'crystalTables':len(sources['crystal']['tables']),'mapsWithPools':sum(bool(m['encounters'] or any(z['encounters'] for z in m.get('encounterZones',[]))) for m in maps.values()),'fallbackMaps':0,'sourceDigests':digests,'maps':{}}
 for key,m in maps.items():
  rule=bindings[key];report['maps'][key]={'name':m['name'],'table':rule.get('table'),'reason':rule['reason'],'zones':copy.deepcopy(rule.get('zones',[])),'methods':list(m['encounters']),'cutTrees':[{'id':o['id'],'x':o['x'],'y':o['y'],'baseCollision':m['collision'][o['y']*m['width']+o['x']]} for o in m['objects'] if o['graphics']==95]}
 report['cutTrees']=sum(len(m['cutTrees']) for m in report['maps'].values())
 (root/'Docs').mkdir(parents=True,exist_ok=True)
 (root/'Docs/ENCOUNTER_CUT_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return report
