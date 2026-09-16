#!/usr/bin/env python3
"""Audit ROM warp events, recover referenced maps, and publish safe portal metadata.

Warp events are destination records; their presence alone does not make floor
walkable or turn an ordinary tile into a teleporter. No ROM scripts are executed.
"""
from __future__ import annotations
import argparse, collections, copy, hashlib, json, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = ('up', 'down', 'left', 'right')
# FireRed-layout behavior values decoded from the supplied map metatile tables.
# Ordinary floor / water / placeholder events are intentionally not triggers.
ENTRY = {value: DIRECTIONS for value in range(0x60, 0x72)}
ENTRY.update({0x60: ('up',), 0x62: ('right',), 0x63: ('left',),
              0x64: ('up',), 0x65: ('down',), 0x69: ('up',)})
FACING = {0x60:(0,1), 0x62:(-1,0), 0x63:(1,0), 0x64:(0,1),
          0x65:(0,-1), 0x69:(0,1)}
WATER = frozenset(range(16,28))
SOLID_OBJECTS = frozenset((95,96,97))

# Script-selected return portals whose raw destination bytes are placeholders.
# These are reviewed individually rather than treating every 0/0 destination as
# dynamic. Goldenrod Department Store's elevator exit is a classic example:
# the ROM script selects the floor before the warp runs, while the raw event
# itself points at bank/map 0/0. NXT does not execute that script, so the safe
# MMO contract is to return the owner to the exact floor/door they entered from.
SCRIPT_DYNAMIC_RETURNS = {
    ('johto_34_27', 0): {
        'target': 'johto_0_0',
        'targetIndex': 0,
        'kind': 'elevator-return',
        'evidence': 'Goldenrod Department Store elevator uses a script-selected destination; raw 0/0 is a placeholder, not Battle Frontier.',
    },
}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')


def inside(m, x, y):
    return 0 <= x < m['width'] and 0 <= y < m['height']


def standable(m, x, y):
    if not inside(m,x,y): return False
    j=y*m['width']+x
    return (m['collision'][j] == 0 and m['behavior'][j] not in WATER and
            not any(o['x']==x and o['y']==y and o['graphics'] in SOLID_OBJECTS for o in m['objects']))


def arrival(m, warp):
    """Use the ROM landing event, stepping off directional door/exit tiles."""
    x,y=warp['x'],warp['y']
    if not inside(m,x,y): return None
    b=m['behavior'][y*m['width']+x]
    if b in FACING:
        dx,dy=FACING[b]
        if standable(m,x+dx,y+dy): return [x+dx,y+dy]
    if standable(m,x,y): return [x,y]
    # Never relocate to a distant spawn or a different room behind a wall.
    candidates=[(x+dx,y+dy) for dx,dy in ((0,1),(0,-1),(-1,0),(1,0))]
    return next(([xx,yy] for xx,yy in candidates if standable(m,xx,yy)),None)


def raw_events(r, m):
    hp=int(m['sourceHeader'],16); result=[]
    if not r.validptr(hp+4): return result
    ep=r.ptr(hp+4); count=r.b[ep+1]
    if not count or not r.validptr(ep+8): return result
    wp=r.ptr(ep+8)
    # Count is a byte (up to255), not128. A valid Sigma map has147 events.
    r.raw(wp,count*8)
    tag=m['id'].split('_')[0]
    for index in range(count):
        q=wp+index*8; x,y=struct.unpack_from('<hh',r.b,q)
        result.append({'x':x,'y':y,'elevation':r.b[q+4],'index':index,
                       'targetIndex':r.b[q+5],'target':f'{tag}_{r.b[q+7]}_{r.b[q+6]}'})
    return result


def raw_objects(r, m):
    """Recover original event actors even when regenerating an already-published pack."""
    hp=int(m['sourceHeader'],16);objects=[]
    if not r.validptr(hp+4):return objects
    ep=r.ptr(hp+4);count=r.b[ep]
    if not count or not r.validptr(ep+4):return objects
    op=r.ptr(ep+4);r.raw(op,count*24)
    for index in range(count):
        q=op+index*24;x,y=struct.unpack_from('<hh',r.b,q+4)
        if inside(m,x,y):objects.append({'id':r.b[q],'sourceLocalId':r.b[q],'sourceObjectIndex':index,
            'graphics':r.b[q+1],'x':x,'y':y,'movement':r.b[q+9],'trainerType':r.u16(q+12)})
    return objects


def recover_map(r, key, assets):
    """Decode one referenced map directly; an earlier invalid sibling is irrelevant."""
    import numpy as np
    from PIL import Image
    tag,bank,index=key.split('_');bank,index=int(bank),int(index)
    if not(0<=bank<43 and 0<=index<256): raise ValueError('Unsupported map address')
    table=r.map_table();gp=r.ptr(table+bank*4)
    # For original contiguous groups never walk into the next group's table.
    groups=[r.ptr(table+g*4) for g in range(43)]
    boundary=min((p for p in groups if p>gp),default=gp+1024)
    if gp+index*4>=boundary: raise ValueError('Outside map pointer group')
    hp=r.ptr(gp+index*4);lp=r.ptr(hp);width,height=r.u32(lp),r.u32(lp+4)
    if not(1<=width<=256 and 1<=height<=256 and width*height<=50000): raise ValueError('Invalid map dimensions')
    tilemap=r.ptr(lp+12);primary=r.ptr(lp+16);secondary=r.ptr(lp+20)
    if r.b[primary] not in (0,1) or r.b[primary+1]!=0 or r.b[secondary] not in (0,1) or r.b[secondary+1]!=1: raise ValueError('Invalid tilesets')
    grid=np.frombuffer(r.raw(tilemap,width*height*2),dtype='<u2').reshape(height,width);ids=grid&1023
    tiles,attrs=r.metatiles(primary,secondary)
    composite=tiles[ids].transpose(0,2,1,3,4).reshape(height*16,width*16,4)
    ground=composite.copy();overlay=np.zeros_like(composite)
    for mid in np.unique(ids):
        if ((attrs[mid]>>29)&3)==2:
            for yy,xx in np.argwhere(ids==mid):
                overlay[yy*16:yy*16+16,xx*16:xx*16+16]=r.meta_upper[mid]
                ground[yy*16:yy*16+16,xx*16:xx*16+16]=r.meta_lower[mid]
    folder=assets/'maps'/tag;folder.mkdir(parents=True,exist_ok=True)
    Image.fromarray(composite).save(folder/f'{bank}_{index}.png')
    Image.fromarray(ground).save(folder/f'{bank}_{index}_ground.png')
    over=bool(overlay[:,:,3].any())
    if over:Image.fromarray(overlay).save(folder/f'{bank}_{index}_over.png')
    objects=[];connections=[]
    if r.validptr(hp+4):
        ep=r.ptr(hp+4);count=r.b[ep]
        if count and r.validptr(ep+4):
            op=r.ptr(ep+4);r.raw(op,count*24)
            for n in range(count):
                q=op+n*24;x,y=struct.unpack_from('<hh',r.b,q+4)
                if 0<=x<width and 0<=y<height:objects.append({'id':r.b[q],'sourceLocalId':r.b[q],'sourceObjectIndex':n,'graphics':r.b[q+1], 'x':x,'y':y,'movement':r.b[q+9],'trainerType':r.u16(q+12)})
    if r.validptr(hp+12):
        cp=r.ptr(hp+12);count=r.u32(cp)
        if 0<count<=16:
            p=r.ptr(cp+4)
            for n in range(count):
                q=p+n*12;connections.append({'direction':r.b[q],'offset':struct.unpack_from('<i',r.b,q+4)[0], 'target':f'{tag}_{r.b[q+8]}_{r.b[q+9]}'})
    _,names=r.region_table();section=r.b[hp+20]
    m={'id':key,'region':'Kanto' if tag=='kanto' else 'Johto / Sigma','name':names.get(section,f'Sigma Area {bank}-{index}'),
       'bank':bank,'map':index,'width':width,'height':height,'mapType':r.b[hp+23],'section':section,
       'image':f'maps/{tag}/{bank}_{index}.png','ground':f'maps/{tag}/{bank}_{index}_ground.png',
       'overlay':f'maps/{tag}/{bank}_{index}_over.png' if over else None,'collision':((grid>>10)&3).astype(int).flatten().tolist(),
       'elevation':(grid>>12).astype(int).flatten().tolist(),'behavior':(attrs[ids]&511).astype(int).flatten().tolist(),
       'warps':[],'connections':connections,'objects':objects,'sourceHeader':hex(hp),'musicId':r.u16(hp+16),'encounterSource':'not-populated-interior-recovery','encounters':{}}
    m['warps']=raw_events(r,m)
    blocked={(a['x'],a['y']) for a in m['warps']}
    safe=[(abs(x-width//2)+abs(y-height//2),x,y) for y in range(height) for x in range(width)
          if standable(m,x,y) and (x,y) not in blocked and m['behavior'][y*width+x] not in ENTRY]
    m['playable']=bool(safe);m['spawn']=list(min(safe)[1:]) if safe else [0,0]
    return m


def audit(world, roms, assets):
    maps=copy.deepcopy(world['maps']);recovered={key:maps[key] for key in world.get('interiors',{}).get('recoveredMaps',[]) if key in maps};event_updates={};failed={};processed=set()
    for key,m in recovered.items():m['objects']=raw_objects(roms[key.split('_')[0]],m)
    for key,m in maps.items():
        events=raw_events(roms[key.split('_')[0]],m)
        if events!=m['warps']: event_updates[key]=events;m['warps']=events
    # Follow native links recursively, not an invented numeric map list.
    while True:
        missing={e['target'] for m in maps.values() for e in m['warps']+m['connections'] if e['target'] not in maps and not e['target'].endswith('_127_127')}-processed
        if not missing:break
        for key in sorted(missing):
            processed.add(key)
            try:
                m=recover_map(roms[key.split('_')[0]],key,assets)
                maps[key]=m;recovered[key]=m
            except (ValueError,IndexError,KeyError,struct.error,TypeError) as exc:failed[key]=str(exc)
    # Sigma's compound Center upstairs return has its bank/map bytes swapped.
    # Repair only an absent target with one exact inverse event, never a guessed
    # numeric neighbor or a visually similar replacement interior.
    reciprocal_repairs=[]
    for key,m in maps.items():
        for warp in m['warps']:
            if warp['target'] in maps or warp['target'].endswith('_127_127'):continue
            candidates=[(target['id'],rev) for target in maps.values() for rev in target['warps']
                        if rev['target']==key and rev['targetIndex']==warp['index'] and rev['index']==warp['targetIndex']]
            if len(candidates)==1:
                target,reverse=candidates[0]
                old=warp['target'];warp['target']=target
                reciprocal_repairs.append({'map':key,'index':warp['index'],'originalTarget':old,'target':target,
                                           'targetIndex':warp['targetIndex'],'evidence':'unique exact inverse ROM event'})
                event_updates[key]=copy.deepcopy(m['warps'])
    changes={};inactive=[];active=collections.Counter();dynamic=[]
    for key,m in maps.items():
        rules={}
        for warp in m['warps']:
            x,y=warp['x'],warp['y'];why=None
            if not inside(m,x,y):why='event-outside-map'
            else:
                behavior=m['behavior'][y*m['width']+x]
                if behavior not in ENTRY:why='not-a-warp-metatile'
                elif m['collision'][y*m['width']+x]!=0 and behavior!=0x69:why='solid-non-door-tile'
                elif (special := SCRIPT_DYNAMIC_RETURNS.get((key,warp['index']))) is not None:
                    if warp['target'] != special['target'] or warp['targetIndex'] != special['targetIndex']:
                        why='reviewed-dynamic-return-source-changed'
                    else:
                        rules[str(warp['index'])]={'directions':list(ENTRY[behavior]),'dynamic':True,'kind':special['kind']}
                        dynamic.append([key,warp['index']]);active['dynamic']+=1
                elif warp['target'].endswith('_127_127') and warp['targetIndex']==127:
                    rules[str(warp['index'])]={'directions':list(ENTRY[behavior]),'dynamic':True,'kind':'return'};dynamic.append([key,warp['index']]);active['dynamic']+=1
                else:
                    target=maps.get(warp['target'])
                    if target is None:why='missing-target-map'
                    elif not target.get('playable',True):why='unplayable-target-map'
                    elif not 0<=warp['targetIndex']<len(target['warps']):why='target-event-out-of-range'
                    else:
                        dest=target['warps'][warp['targetIndex']];point=arrival(target,dest)
                        if point is None:why='no-safe-adjacent-arrival'
                        else:
                            rules[str(warp['index'])]={'directions':list(ENTRY[behavior]),'arrival':point,
                                'kind':'door' if behavior==0x69 else 'warp'};active['static']+=1
                            if m['collision'][y*m['width']+x]:active['solidDoors']+=1
            if why:inactive.append({'map':key,'index':warp['index'],'reason':why,'target':warp['target']})
        changes[key]=rules
    report={'format':1,'sources':{tag:{'sha256':hashlib.sha256(r.b).hexdigest(),'size':len(r.b)} for tag,r in roms.items()},
            'mapCount':len(maps),'recoveredMaps':sorted(recovered),'eventUpdates':event_updates,'rules':changes,
            'counts':dict(active),'inactive':inactive,'unresolvedMaps':failed,'reciprocalRepairs':reciprocal_repairs,
            'scriptDynamicReturns':[{'map':key,'index':index,**copy.deepcopy(meta)} for (key,index),meta in SCRIPT_DYNAMIC_RETURNS.items()],
            'semantics':'Warp event targetIndex is zero-based. Only matching warp-behavior tiles trigger; normal floor records are inert. Dynamic returns belong to the entering player; reviewed script-selected placeholder returns never use their raw placeholder map as a real destination.'}
    return report,recovered


def apply(world, root=ROOT):
    """Idempotent content transform used before repacking client/server content."""
    root=Path(root);report=json.loads((root/'Server/data/interior_repairs.json').read_text(encoding='utf-8'))
    recovered=json.loads((root/'Server/data/interior_maps.json').read_text(encoding='utf-8'))
    for key,m in recovered.items():world['maps'].setdefault(key,copy.deepcopy(m))
    for key,events in report['eventUpdates'].items():world['maps'][key]['warps']=copy.deepcopy(events)
    for key,rules in report['rules'].items():
        if key not in world['maps']:continue
        for warp in world['maps'][key]['warps']:
            warp.pop('access',None)
            access=rules.get(str(warp['index']))
            if access:warp['access']=copy.deepcopy(access)
    world['interiors']={'format':1,'recoveredMaps':report['recoveredMaps'],'counts':report['counts']}
    return world


def prepare_navigation(world, roms, assets):
    """Author only the audited gym blockers, using the ROM's open-gate graphics."""
    from PIL import Image
    navigation={'format':1,'adaptation':'Gym puzzle gates are pre-opened for the MMO challenge. Native script puzzles are not executed.', 'maps':{}}
    source_scripts={'kanto_9_6':(0x16b78f,0x16b7e9), 'kanto_12_0':(0x16e18f,0x16e2ea)}
    for key in ['kanto_9_6','kanto_12_0','johto_34_46','johto_34_54']:
        m=world['maps'][key];tag,bank,index=key.split('_');r=roms[tag];hp=int(m['sourceHeader'],16);lp=r.ptr(hp);gp=r.ptr(lp+12)
        tiles,attrs=r.metatiles(r.ptr(lp+16),r.ptr(lp+20));patches=[]
        if key in source_scripts:
            lo,hi=source_scripts[key]
            for q in range(lo,hi):
                if r.b[q]!=0xa2:continue
                x,y,mid,collision=struct.unpack_from('<HHHH',r.b,q+1)
                if not(inside(m,x,y) and mid<1024 and collision in (0,1)):continue
                original=r.u16(gp+2*(y*m['width']+x))
                patches.append({'x':x,'y':y,'fromMetatile':original&1023,'metatile':mid,'collision':collision,
                                'elevation':original>>12,'behavior':int(attrs[mid]&511),'sourceScript':hex(q)})
        else:
            # One snow-bank choke point separates the native north ladder from
            # Pryce's ice room. The exact neighboring source floor opens it.
            x,y,source_x,source_y=(5,33,5,32) if key=='johto_34_46' else (8,5,7,5);original=r.u16(gp+2*(y*m['width']+x));floor=r.u16(gp+2*(source_y*m['width']+source_x));mid=floor&1023
            patches.append({'x':x,'y':y,'fromMetatile':original&1023,'metatile':mid,'collision':0,
                            'elevation':floor>>12,'behavior':int(attrs[mid]&511),'sourceFloor':[source_x,source_y]})
        base=f'maps/{tag}/{bank}_{index}'
        native=assets/(base+'.png');native_ground=assets/(base+'_ground.png');native_overlay=assets/(base+'_over.png')
        composite=Image.open(native).convert('RGBA');ground=Image.open(native_ground).convert('RGBA')
        overlay=Image.open(native_overlay).convert('RGBA') if native_overlay.exists() else Image.new('RGBA',composite.size)
        for patch in patches:
            x,y,mid=patch['x'],patch['y'],patch['metatile'];point=(x*16,y*16);image=Image.fromarray(tiles[mid])
            composite.paste(image,point)
            if ((int(attrs[mid])>>29)&3)==2:
                ground.paste(Image.fromarray(r.meta_lower[mid]),point);overlay.paste(Image.fromarray(r.meta_upper[mid]),point)
            else:
                ground.paste(image,point);overlay.paste(Image.new('RGBA',(16,16)),point)
        outputs={'image':base+'_adventure.png','ground':base+'_adventure_ground.png','overlay':None}
        composite.save(assets/outputs['image']);ground.save(assets/outputs['ground'])
        if overlay.getbbox():outputs['overlay']=base+'_adventure_over.png';overlay.save(assets/outputs['overlay'])
        navigation['maps'][key]={'tiles':patches,'assets':outputs,'nativeImage':base+'.png',
                                 'nativeImageSha256':hashlib.sha256(native.read_bytes()).hexdigest()}
    for key,points in {'johto_1_88':[(8,20),(8,15)]}.items():
        navigation['maps'][key]={'clearObjects':[{'x':x,'y':y,'graphics':97} for x,y in points],
                                'reason':'Pre-cleared Strength boulders preserve the native gym floor and make its leader reachable.'}
    return navigation


def apply_navigation(world, root=ROOT):
    """Apply AFTER normalized ROM objects and Center object patches, before pack."""
    root=Path(root);nav=json.loads((root/'Server/data/interior_navigation.json').read_text(encoding='utf-8'))
    for key,change in nav['maps'].items():
        m=world['maps'][key]
        for p in change.get('tiles',[]):
            j=p['y']*m['width']+p['x']
            m['collision'][j]=p['collision'];m['behavior'][j]=p['behavior'];m['elevation'][j]=p['elevation']
        for obj in change.get('clearObjects',[]):
            m['objects']=[o for o in m['objects'] if not all(o.get(field)==obj[field] for field in ('x','y','graphics'))]
        m.update(change.get('assets',{}));m['navigationAdaptation']='Open gym challenge passages'
    world.setdefault('interiors',{})['gymNavigationMaps']=list(nav['maps'])
    return world


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--firered',type=Path,required=True);p.add_argument('--sigma',type=Path,required=True);p.add_argument('--root',type=Path,default=ROOT);args=p.parse_args()
    from extract_assets import Rom
    root=args.root;world=json.loads((root/'Server/data/world.json').read_text(encoding='utf-8'))
    roms={'kanto':Rom(args.firered),'johto':Rom(args.sigma)}
    report,recovered=audit(world,roms,root/'Client/app/assets')
    dump(root/'Server/data/interior_repairs.json',report);dump(root/'Server/data/interior_maps.json',recovered)
    navigation_world=apply(copy.deepcopy(world),root)
    dump(root/'Server/data/interior_navigation.json',prepare_navigation(navigation_world,roms,root/'Client/app/assets'))
    print(json.dumps({'maps':report['mapCount'],'recovered':len(recovered),'counts':report['counts'],'unresolved':len(report['unresolvedMaps'])},indent=2))

if __name__=='__main__':main()
