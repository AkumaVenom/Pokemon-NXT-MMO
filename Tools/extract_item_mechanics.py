#!/usr/bin/env python3
"""Statically recover Sigma item records and the *referenced* TM/HM table.

Requires the exact user-supplied Sigma 1.5.0 ROM only during extraction. Builds
and runtime use the resulting JSON and never execute or distribute ROM bytes.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
try:
    from .extract_adventure_data import Rom, text, normalize
    from .item_rules import build_rules
except ImportError:
    from extract_adventure_data import Rom, text, normalize
    from item_rules import build_rules
ROOT=Path(__file__).resolve().parents[1]
SHA='62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64'

def extract(path,root=ROOT):
    r=Rom(path)
    if len(r.b)!=17632785 or hashlib.sha256(r.b).hexdigest()!=SHA:raise ValueError('Unreviewed Sigma ROM revision')
    world=json.loads((root/'Server/data/world.json').read_text(encoding='utf-8'))
    # Ignore our explicitly crafted extension when reproducing extraction.
    items={k:v for k,v in world['items'].items() if k!='fastball'}
    manifest=json.loads((root/'Tools/extraction_manifest.json').read_text(encoding='utf-8'))
    battle=json.loads((root/'Server/data/battle_mechanics.json').read_text(encoding='utf-8'))
    item_table=r.ptr(0x1c8);machine_table=r.ptr(0x125a8c);compat_table=r.ptr(0x43c68)
    if (item_table,machine_table,compat_table)!=(0x3db028,0x45a80c,0xa91d80) or r.ptr(0x43c80)!=compat_table:raise ValueError('Reviewed table references changed')
    native={};machines={}
    for key,item in items.items():
        sid=item.get('sourceId')
        if not isinstance(sid,int):continue
        off=item_table+sid*44;raw=r.raw(off,44)
        ptr=r.ptr(off+20);end=r.b.find(b'\xff',ptr,min(len(r.b),ptr+512))
        if end<0:raise ValueError('Unterminated item description: '+key)
        description=text(r.raw(ptr,end-ptr).replace(b'\xfe',b' ').replace(b'\xfa',b' ').replace(b'\xfb',b' '))
        native[key]={'sourceId':sid,'offset':hex(off),'name':text(raw[:14]),'storedId':r.u16(off+14),'price':r.u16(off+16),'holdEffect':raw[18],'holdParameter':raw[19],
                     'description':description,'descriptionOffset':hex(ptr),'importance':raw[24],'pocket':raw[26],'type':raw[27],
                     'fieldFunction':hex(r.u32(off+28)),'battleUsage':raw[32],'battleFunction':hex(r.u32(off+36)),'secondaryId':r.u32(off+40)}
        if key.startswith(('tm','hm')) and 289<=sid<=347:
            idx=sid-289;mid=r.u16(machine_table+idx*2)
            alias=world.get('learnsets',{}).get('moveIdAliases',{}).get('johto',{}).get(str(mid),mid)
            if str(alias) not in world['moves']:raise ValueError('Unpublished machine move: '+key)
            machines[key]={'index':idx,'sourceMoveId':mid,'move':alias,'moveName':world['moves'][str(alias)]['name'],'offset':hex(machine_table+idx*2)}
    byname={}
    for sid,s in manifest['catalogs']['johto'].items():byname.setdefault(normalize(s['name']),[]).append(int(sid))
    species={}
    for key,s in world['species'].items():
        candidates=byname.get(normalize(s['name']),[])
        # Shared canonical species use the lowest exact native-name match;
        # Sigma-only species retain their own original native species index.
        sid=int(s['sourceId']) if s['source']=='johto' else min(candidates) if candidates else None
        if sid is None:raise ValueError('No Sigma compatibility identity: '+key)
        off=compat_table+sid*8;bits=struct.unpack('<Q',r.raw(off,8))[0]
        eligible=[k for k,m in machines.items() if bits & (1<<m['index'])]
        raw=bytes.fromhex(battle['species'][key]['baseStatsRawHex']);ev=struct.unpack_from('<H',raw,10)[0]
        species[key]={'sigmaSpeciesId':sid,'compatibilityOffset':hex(off),'compatibilityHex':r.raw(off,8).hex(),'machines':eligible,
                      'evYield':[(ev>>(i*2))&3 for i in range(6)],'evSource':battle['species'][key]['source'],'evOffset':hex(int(battle['species'][key]['baseStatsOffset'],16)+10)}
    # Recover Sigma's item evolution alternatives for shared canonical species,
    # too. The previous publisher retained only FireRed evolution rules there.
    target_keys={normalize(s['name']):key for key,s in world['species'].items()}
    source_to_key={int(sid):target_keys[normalize(s['name'])] for sid,s in manifest['catalogs']['johto'].items() if normalize(s['name']) in target_keys}
    item_by_id={v.get('sourceId'):k for k,v in items.items() if v.get('evolutionStone')}
    evolutions={};rejected=[]
    for key,profile in species.items():
        sid=profile['sigmaSpeciesId'];entries=[]
        for slot in range(8):
            off=0xbfffc0+(sid*8+slot)*8;method,param,target,pad=struct.unpack('<HHHH',r.raw(off,8))
            if method!=7 or param not in item_by_id:continue
            dest=source_to_key.get(target)
            if pad or not dest or dest==key:
                rejected.append({'species':key,'offset':hex(off),'item':item_by_id[param],'reason':'invalid target or padding'});continue
            entries.append({'source':'johto','sourceSpeciesId':sid,'rawMethod':method,'rawParameter':param,'targetSourceId':target,'offset':hex(off),
                            'target':dest,'method':'stone','item':item_by_id[param],'itemSourceRule':True,
                            'migrateGrowth':world['species'][key]['growth']!=world['species'][dest]['growth']})
        if entries:evolutions[key]=entries
    map_flags={}
    for key,m in world['maps'].items():
        if key.startswith('johto_') and m.get('sourceHeader'):
            header=int(m['sourceHeader'],16);flag=r.raw(header+0x19,1)[0]
            map_flags[key]={'escapeAllowed':bool(flag&1),'offset':hex(header+0x19),'raw':flag}
    rules=build_rules(items,native,machines)
    result={'format':1,'sourceSha256':SHA,'sourceBytes':len(r.b),'nativeItems':native,'machines':machines,'species':species,'rules':rules,'evolutions':evolutions,'rejectedEvolutions':rejected,'mapFlags':map_flags,
            'references':{'itemTable':hex(item_table),'machineTable':hex(machine_table),'machinePointerOffset':'0x125a8c','compatibilityTable':hex(compat_table),'compatibilityPointerOffsets':['0x43c68','0x43c80']},
            'policy':'Native records are evidence, not executable mechanics. Explicit NXT adapters are marked per item. Machine compatibility is taken from the supplied Sigma table, including unusual assignments. The stale vanilla table at 0x45a5a4 is not used.'}
    out=root/'Server/data/item_mechanics.json';out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Extracted',len(rules),'item contracts,',len(machines),'machines and',len(species),'species profiles')
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('rom',type=Path);parser.add_argument('--root',type=Path,default=ROOT);args=parser.parse_args();extract(args.rom,args.root)
