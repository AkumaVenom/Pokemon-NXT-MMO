#!/usr/bin/env python3
"""Validate and bind the reviewed ROM battle sidecar into runtime content.

Normal builds never need either ROM.  `battle_mechanics.json` is the immutable,
hash-pinned output of `extract_battle_mechanics.py`; this publisher reapplies
its authoritative battle fields after the other content publishers rebuild
move/species records.
"""
from __future__ import annotations
import copy,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FIRERED_SHA='729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059'
SIGMA_SHA='62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64'
SIGMA_ALIAS_IDS={1207,1234,1261,1318,1319,1321,1370}


def assemble(world:dict,root:Path=ROOT):
 root=Path(root);path=root/'Server/data/battle_mechanics.json'
 audit=json.loads(path.read_text(encoding='utf-8'))
 if audit.get('format')!=1 or audit.get('engine')!='Gen III singles move-effect runtime':raise ValueError('Unsupported battle mechanics sidecar')
 sources=audit.get('sources',{})
 if sources.get('kanto',{}).get('sha256')!=FIRERED_SHA or sources.get('johto',{}).get('sha256')!=SIGMA_SHA:raise ValueError('Battle source provenance mismatch')
 moves=audit.get('moves',{});species=audit.get('species',{})
 if set(map(int,moves))!=set(range(1,355))|SIGMA_ALIAS_IDS:raise ValueError('Battle move audit does not cover the published move identity set')
 if set(moves)!=set(world.get('moves',{})):raise ValueError('Battle move audit/runtime catalog mismatch')
 if set(species)!=set(world.get('species',{})):raise ValueError('Battle species audit/runtime catalog mismatch')
 meta=audit.get('audit',{})
 if meta.get('moveRecords')!=361 or meta.get('effectIds')!=len({int(v['effect']) for v in moves.values()}) or meta.get('speciesRecords')!=len(species):raise ValueError('Battle audit counts are inconsistent')
 for key,rec in moves.items():
  move=world['moves'][key]
  source=rec.get('source');expected_sha=FIRERED_SHA if source=='kanto' else SIGMA_SHA if source=='johto' else None
  if rec.get('sourceSha256')!=expected_sha:raise ValueError('Move source hash mismatch: '+key)
  for field in ('effect','power','type','accuracy','pp','chance','target','priority'):
   if int(move.get(field,-9999))!=int(rec[field]):raise ValueError(f'Runtime move differs from reviewed ROM field {field}: {key}')
  move['flags']=int(rec['flags'])
  # FireRed uses the Gen-III type split. The seven Sigma aliases retain the
  # native category byte already reviewed from that hack's move table.
  move['category']=int(rec['categoryByte']) if source=='johto' else (0 if int(rec['type'])<=8 else 1)
  move['battleEffectName']=rec['effectName']
  move['battleProvenance']={'source':source,'sha256':rec['sourceSha256'],'sourceMoveId':int(rec['sourceMoveId']),'offset':rec['offset'],'rawHex':rec['rawHex']}
 for key,rec in species.items():
  mon=world['species'][key]
  if mon.get('source')!=rec.get('source') or int(mon.get('sourceId',-1))!=int(rec.get('sourceSpeciesId',-2)):raise ValueError('Battle species source mismatch: '+key)
  for field in ('genderRatio','baseFriendship','abilities','heldItems','weightHectograms','weightSource'):
   mon[field]=copy.deepcopy(rec[field])
 world['battleMechanics']={'format':1,'moveRecords':361,'effectIds':meta['effectIds'],'speciesRecords':len(species),'unknownSigmaWeights':meta.get('unknownSigmaWeights',0),'sources':{'kanto':FIRERED_SHA,'johto':SIGMA_SHA}}
 return audit
