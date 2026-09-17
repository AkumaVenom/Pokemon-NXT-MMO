#!/usr/bin/env python3
"""Extract bounded, validated FRLG adventure records; never execute ROM code.

Only the two reviewed SHA-256 ROM revisions are accepted. Trainer associations
are discovered by following known event instructions, not searching arbitrary
bytes for a battle opcode. Unsupported/ambiguous branches are reported.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, re, struct
from pathlib import Path

# Keep sidecar checks and ordinary builds independent of Pillow/numpy. Graphics
# extraction is a separate development workflow and is never imported here.
CHARS={0:' ',0xad:'.',0xae:'-',0xab:'!',0xac:'?',0xb4:"'",0xb5:'♂',0xb6:'♀',0xba:':',0xb8:',',0x1b:'é',0xb0:'…',0xf0:':',0xf1:'ä',0xf2:'ö',0xf3:'ü',0xf4:'Ä',0xf5:'Ö',0xf6:'Ü'}
CHARS.update({0xbb+i:chr(65+i) for i in range(26)})
CHARS.update({0xd5+i:chr(97+i) for i in range(26)})
CHARS.update({0xa1+i:str(i) for i in range(10)})
def text(data):return ''.join(CHARS.get(v,'?') for v in data.split(b'\xff')[0])

class Rom:
 def __init__(self,path):self.b=Path(path).read_bytes()
 def raw(self,offset,size):
  if offset<0 or size<0 or offset+size>len(self.b):raise ValueError('Range exceeds ROM')
  return self.b[offset:offset+size]
 def u16(self,offset):return struct.unpack('<H',self.raw(offset,2))[0]
 def u32(self,offset):return struct.unpack('<I',self.raw(offset,4))[0]
 def ptr(self,offset):
  target=self.u32(offset)-0x8000000
  if not 0<=target<len(self.b):raise ValueError('Invalid ROM pointer')
  return target
 def validptr(self,offset):
  try:self.ptr(offset);return True
  except (ValueError,struct.error):return False

ROOT=Path(__file__).resolve().parents[1]
PROFILES={
 'kanto':{'trainerTable':0x23eb38,'evolutionTable':0x2597c4,'evolutionSlots':5},
 'johto':{'trainerTable':0x23eac8,'evolutionTable':0xbfffc0,'evolutionSlots':8},
}
STONES={93:('sunstone','Sun Stone'),94:('moonstone','Moon Stone'),95:('firestone','Fire Stone'),96:('thunderstone','Thunder Stone'),97:('waterstone','Water Stone'),98:('leafstone','Leaf Stone')}
SIGMA_ITEMS={42:('kingsrock',"King's Rock"),43:('metalcoat','Metal Coat'),44:('upgrade','Up-Grade'),46:('reapercloth','Reaper Cloth'),
 47:('dubiousdisc','Dubious Disc'),49:('linkcable','Link Cable'),51:('razorclaw','Razor Claw'),52:('electirizer','Electirizer'),
 53:('magmarizer','Magmarizer'),55:('dragonscale','Dragon Scale'),56:('fairydust','Fairy Dust'),57:('ovalstone','Oval Stone'),
 58:('protector','Protector'),59:('prismscale','Prism Scale'),60:('shinystone','Shiny Stone'),61:('dawnstone','Dawn Stone'),
 62:('duskstone','Dusk Stone'),72:('razorfang','Razor Fang')}
GYM_IDS={'kanto':[414,415,416,417,418,420,419,350], 'johto':[414,415,416,417,418,420,419,350]}
# Fixed-size, non-control-flow commands supported by this static reader.
# Unknown commands terminate that path. Text/movement pointers are never read as
# executable code. Branch/call/return commands are handled separately below.
LENGTHS={0x00:1,0x01:1,0x0f:6,0x10:3,0x11:6,0x12:6,0x13:6,0x14:3,0x15:9,
 0x16:5,0x17:5,0x18:5,0x19:5,0x1a:5,0x1b:3,0x1c:3,0x1d:6,0x1e:6,
 0x1f:6,0x20:9,0x21:5,0x22:5,0x25:3,0x26:5,0x27:1,0x28:3,
 0x29:3,0x2a:3,0x2b:3,0x2c:5,0x2d:1,0x2e:1,0x2f:3,
 0x30:1,0x31:3,0x32:1,0x33:4,0x34:3,0x35:1,0x36:3,0x37:2,0x38:2,
 0x42:5,0x43:1,0x44:5,0x45:5,0x46:5,0x47:5,0x48:3,0x49:5,0x4a:5,
 0x4b:3,0x4c:3,0x4d:3,0x4e:3,0x4f:7,0x50:9,0x51:3,0x52:5,0x53:3,0x54:5,0x55:3,
 0x56:5,0x57:7,0x58:5,0x59:5,0x5a:1,0x5b:4,0x60:3,0x61:3,0x62:3,
 0x66:1,0x67:5,0x68:1,0x69:1,0x6a:1,0x6b:1,0x6c:1,0x6d:1,0x6e:3,0x6f:5,0x70:6,0x71:6}


def normalize(name):return re.sub(r'[^a-z0-9]','',name.lower().replace('♀','female').replace('♂','male'))

def species_lookup(world,manifest,tag):
 byname={normalize(s['name']):key for key,s in world['species'].items()}
 return {int(i):byname[normalize(s['name'])] for i,s in manifest['catalogs'][tag].items() if normalize(s['name']) in byname}

def normalize_object_list(objects):
 """ROM-free normalization for decoded, raw-indexed object event records."""
 visible=[]
 for i,obj in enumerate(objects):
  if obj.get('movement')==76:continue
  o=dict(obj);o.setdefault('sourceLocalId',o['id']);o.setdefault('sourceObjectIndex',i);visible.append(o)
 reserved={o['id'] for o in visible};used=set()
 for o in visible:
  if o['id'] in used:o['id']=next(n for n in range(1,256) if n not in reserved and n not in used)
  used.add(o['id'])
 return visible

def normalize_objects(r,m):
 """Preserve visible local IDs; remap only duplicates after hidden filtering.

 sourceObjectIndex always addresses the original ROM event array, including
 entries omitted by the map importer. It is never the filtered-list index.
 """
 try:
  ev=r.ptr(int(m['sourceHeader'],16)+4);count=r.b[ev]
  if not count:return []
  if count>128:raise ValueError('object count')
  table=r.ptr(ev+4)
 except (KeyError,ValueError,IndexError,struct.error):return list(m.get('objects',[]))
 visible=[]
 for i in range(count):
  q=table+i*24;r.raw(q,24);x,y=struct.unpack_from('<hh',r.b,q+4)
  if r.b[q+9]==76 or not (0<=x<m['width'] and 0<=y<m['height']):continue
  visible.append({'id':r.b[q],'graphics':r.b[q+1],'x':x,'y':y,'movement':r.b[q+9],
   'trainerType':r.u16(q+12),'sourceLocalId':r.b[q],'sourceObjectIndex':i})
 return normalize_object_list(visible)

def first_battles(r,start,limit=512):
 """Return reachable first battle sites and why incomplete paths stopped.

 Calls have a bounded return stack; both conditional branches are visited.
 Standard dialogue calls return, but an unknown standard goto terminates. No
 outcome of a ROM variable, flag, native function or player choice is invented.
 """
 todo=[(start,())];seen=set();battles={};stops=collections.Counter()
 while todo and len(seen)<limit:
  pc,stack=todo.pop()
  if (pc,stack) in seen:continue
  seen.add((pc,stack))
  if not 0<=pc<len(r.b):stops['range']+=1;continue
  op=r.b[pc]
  try:
   if op==0x5c:
    kind=r.b[pc+1];tid=r.u16(pc+2)
    # First trainer command suffices; do not decode its post-battle script.
    # Modes 4/6/7/8 are double battles and cannot run in the single-battle MMO.
    if kind not in (0,1,2,3,4,5,6,7,8,9):stops['battle-mode']+=1;continue
    # Intro and defeat text pointers validate the command boundary.
    if kind==3:
     r.ptr(pc+6)
    else:
     r.ptr(pc+6);r.ptr(pc+10)
    battles[pc]={'trainerId':tid,'battleType':kind,'battleOffset':hex(pc)}
   elif op==0x02:pass
   elif op==0x03:
    if stack:todo.append((stack[-1],stack[:-1]))
   elif op in (0x04,0x05):
    target=r.ptr(pc+1)
    if op==0x04:
     if len(stack)>=8:stops['call-depth']+=1;continue
     todo.append((target,stack+(pc+5,)))
    else:todo.append((target,stack))
   elif op in (0x06,0x07):
    if r.b[pc+1]>5:raise ValueError('invalid comparison')
    target=r.ptr(pc+2);todo.append((pc+6,stack))
    if op==0x07:
     if len(stack)<8:todo.append((target,stack+(pc+6,)))
     else:stops['call-depth']+=1
    else:todo.append((target,stack))
   elif op==0x09:
    if r.b[pc+1]>9:raise ValueError('unknown standard script')
    todo.append((pc+2,stack))
   elif op==0x08:stops['standard-goto']+=1
   elif op in LENGTHS:
    size=LENGTHS[op];r.raw(pc,size);todo.append((pc+size,stack))
   else:stops[f'opcode-{op:02x}']+=1
  except (IndexError,ValueError,struct.error):stops['invalid-instruction']+=1
 if todo:stops['instruction-limit']+=1
 return sorted(battles.values(),key=lambda b:int(b['battleOffset'],16)),dict(stops)

def trainer(r,profile,tid,lookup,moves):
 if not 1<=tid<2048:raise ValueError('trainer ID outside bounded table')
 q=profile['trainerTable']+tid*40;r.raw(q,40)
 flags=r.b[q];count=r.b[q+32];name=text(r.raw(q+4,12)).strip()
 if flags not in (0,1,2,3) or not 1<=count<=6 or not name or '?' in name:raise ValueError('trainer header')
 if r.b[q+24] not in (0,1):raise ValueError('double-battle field')
 p=r.ptr(q+36);stride=16 if flags&1 else 8;team=[]
 for i in range(count):
  o=p+i*stride;r.raw(o,stride);iv,level,sourceId=struct.unpack_from('<HHH',r.b,o)
  if not 0<=iv<=255 or not 1<=level<=100 or sourceId not in lookup:raise ValueError('trainer party species/level/IV')
  rawmoves=list(struct.unpack_from('<4H',r.b,o+(8 if flags&2 else 6))) if flags&1 else []
  if any(m and str(m) not in moves for m in rawmoves):raise ValueError('unsupported custom trainer move')
  team.append({'species':lookup[sourceId],'level':level,'moves':[m for m in rawmoves if m],
   'sourceSpeciesId':sourceId,'sourceMoves':rawmoves,'heldItemId':r.u16(o+6) if flags&2 else 0,'iv':iv})
 return {'trainerId':tid,'name':name.title(),'trainerClassId':r.b[q+1], 'team':team,
  'doubleBattle':bool(r.b[q+24]),'trainerOffset':hex(q),'partyOffset':hex(p),'partyFlags':flags}

def extract_trainers(r,tag,world,lookup):
 profile=PROFILES[tag];result={};unresolved=[];gym_candidates=collections.defaultdict(list)
 for mid,m in sorted(world['maps'].items()):
  if not mid.startswith(tag+'_'):continue
  try:
   hp=int(m['sourceHeader'],16);ev=r.ptr(hp+4);count=r.b[ev]
   if count==0:continue
   if count>128:raise ValueError('object count')
   table=r.ptr(ev+4)
  except (KeyError,ValueError,IndexError,struct.error):continue
  normalized={o['sourceObjectIndex']:o for o in normalize_objects(r,m) if 'sourceObjectIndex' in o}
  for i in range(count):
   q=table+i*24
   try:
    if i not in normalized:continue
    obj=normalized[i];npc=obj['id'];x,y=obj['x'],obj['y']
    # Border-only script proxies cannot be approached in the rendered world.
    if x==0 or y==0:continue
    start=r.ptr(q+16);battles,stops=first_battles(r,start)
   except (ValueError,IndexError,struct.error):continue
   ids={b['trainerId'] for b in battles};chosen=None
   if len(ids)==1 and (not stops or next(iter(ids)) in GYM_IDS[tag]):chosen=battles[0]
   elif ids:
    leaders=ids.intersection(GYM_IDS[tag])
    # Leaders with one verified original challenge and later rematches are
    # explicit adapters. Arbitrary rival/conditional teams remain unsupported.
    if len(leaders)==1:chosen=next(b for b in battles if b['trainerId'] in leaders)
   key=f'{mid}:{npc}'
   if chosen:
    try:
     t=trainer(r,profile,chosen['trainerId'],lookup,world['moves'])
     if t['doubleBattle'] or chosen['battleType'] in (4,6,7,8):raise ValueError('double battle unsupported')
     record={**t,**chosen,'id':key,'map':mid,'npc':npc,'x':x,'y':y,'source':tag,'sourceScript':hex(start),
      'sourceObjectOffset':hex(q),'sourceObjectIndex':i,'sourceLocalId':r.b[q],'association':'event-control-flow','conditionalTrainerIds':sorted(ids)}
     result[key]=record
     if t['trainerId'] in GYM_IDS[tag]:gym_candidates[t['trainerId']].append(record)
    except (ValueError,IndexError,struct.error) as exc:unresolved.append({'map':mid,'npc':npc,'reason':str(exc),'trainerIds':sorted(ids)})
   elif battles or r.u16(q+12):
    unresolved.append({'map':mid,'npc':npc,'reason':'ambiguous trainer branches' if battles else 'unsupported script path','trainerIds':sorted(ids),'stops':stops})
 gyms=[]
 for order,tid in enumerate(GYM_IDS[tag],1):
  candidates=gym_candidates[tid]
  if len(candidates)==1:
   t=candidates[0];gyms.append({'region':'Kanto' if tag=='kanto' else 'Johto','source':tag,'order':order,'name':t['name'],'trainerId':tid,'map':t['map'],'npc':t['npc'],'trainer':t['id']})
  else:unresolved.append({'reason':'gym association missing or ambiguous','trainerId':tid,'candidates':[t['id'] for t in candidates]})
 return result,gyms,unresolved

def extract_evolutions(r,tag,lookup,world):
 profile=PROFILES[tag];base=profile['evolutionTable'];slots=profile['evolutionSlots'];rules={};unsupported=[]
 stones={**STONES,**(SIGMA_ITEMS if tag=='johto' else {})}
 itemtable=r.ptr(0x1c8)
 for itemId,(key,name) in stones.items():
  q=itemtable+itemId*44
  if r.u16(q+14)!=itemId or normalize(text(r.raw(q,14)))!=normalize(name):raise ValueError(f'{tag} item definition mismatch: {itemId}')
 if r.b.find(struct.pack('<I',base+0x8000000),0,0x100000)<0:raise ValueError('Evolution table has no engine reference')
 # Verify the reviewed table's six starter chains before accepting any records.
 for sourceId,level,target in [(1,16,2),(2,32,3),(4,16,5),(5,36,6),(7,16,8),(8,36,9)]:
  if struct.unpack_from('<HHH',r.b,base+sourceId*slots*8)!=(4,level,target):raise ValueError(f'{tag} evolution anchor mismatch')
 for sourceId,key in sorted(lookup.items()):
  entries=[]
  for slot in range(slots):
   q=base+(sourceId*slots+slot)*8;method,param,target,pad=struct.unpack_from('<HHHH',r.b,q)
   if method==0:continue
   raw={'species':key,'source':tag,'sourceSpeciesId':sourceId,'rawMethod':method,'rawParameter':param,'targetSourceId':target,'offset':hex(q)}
   if pad!=0 or target not in lookup:unsupported.append({**raw,'reason':'invalid or unavailable target'});continue
   if world['species'][key]['growth']!=world['species'][lookup[target]]['growth']:
    unsupported.append({**raw,'target':lookup[target],'reason':'growth curve differs; requires experience migration'});continue
   out={**raw,'target':lookup[target]};out.pop('species')
   if method==4 and 1<=param<=100:out.update(method='level',level=param)
   elif method==5:out.update(method='trade')
   elif method==7 and param in stones:out.update(method='stone',item=stones[param][0])
   else:unsupported.append({**raw,'target':lookup[target],'reason':'evolution method or item not implemented'});continue
   entries.append(out)
  if entries:rules[key]=entries
 return rules,unsupported

SIGMA_ITEM_TABLE_POINTER=0x1c8
SIGMA_ITEM_TABLE=0x3db028
FIELD_ITEM_GRAPHICS=92
ITEM_POCKETS={1:'items',2:'key-items',3:'poke-balls',4:'tm-hm',5:'berries'}


def field_item_script(r,start,limit=128):
 """Recognize the reviewed linear Sigma field-item idiom without executing code.

 The item scripts write source item/quantity into VAR_8000/VAR_8001 and call
 standard script 1. Prefix dialogue/facing commands are tolerated only when
 their fixed lengths are known. Calls, gotos, branches, returns and unknown
 opcodes stop the path, preventing bytes from adjacent scripts being treated as
 a pickup.
 """
 pc=start;item=None;quantity=None;steps=0
 while steps<64 and 0<=pc<len(r.b) and pc-start<limit:
  steps+=1;op=r.b[pc]
  try:
   if op==0x1a:
    var,value=r.u16(pc+1),r.u16(pc+3)
    if var==0x8000:item=value
    elif var==0x8001:quantity=value
    pc+=5;continue
   if op==0x09:
    standard=r.b[pc+1]
    if standard==1 and item is not None and quantity is not None:
     if not 1<=item<=999 or not 1<=quantity<=999:return None
     return {'sourceItemId':item,'quantity':quantity,'sourceGiveCommand':hex(pc),'scriptBytes':pc-start+2}
    pc+=2;continue
   # Never invent outcomes for control flow. These commands terminate this
   # bounded path rather than following ROM branches or subroutines.
   if op in (0x02,0x03,0x04,0x05,0x06,0x07,0x08):return None
   size=LENGTHS.get(op)
   if size is None:return None
   r.raw(pc,size);pc+=size
  except (IndexError,ValueError,struct.error):return None
 return None


def sigma_item_definition(r,item_id):
 table=r.ptr(SIGMA_ITEM_TABLE_POINTER)
 if table!=SIGMA_ITEM_TABLE:raise ValueError('Sigma active item table mismatch')
 q=table+item_id*44;r.raw(q,44);name=text(r.raw(q,14)).strip()
 if not name or '?' in name:raise ValueError(f'Unreadable Sigma item name: {item_id}')
 stored=r.u16(q+14);price=r.u16(q+16);importance=r.b[q+24];pocket=r.b[q+26]
 key=normalize(name.replace('é','e'))
 if not key:raise ValueError(f'Invalid Sigma item key: {item_id}')
 category=ITEM_POCKETS.get(pocket,'items')
 description={'key-items':'Key Item','poke-balls':'Poké Ball','tm-hm':'TM / HM','berries':'Berry'}.get(category,'Item')+' recovered from a verified Johto / Sigma field Poké Ball.'
 item={'name':name,'sourceId':item_id,'source':'johto','sourceOffset':hex(q),'sourceStoredId':stored,
  'sourcePrice':price,'price':price,'priceSource':'sigma-rom-field-catalog','pocket':pocket,'pocketName':category,
  'importance':importance,'fieldItem':True,'buyable':False,'tradable':not bool(importance),'description':description}
 if importance:item['keyItem']=True
 return key,item


def extract_sigma_item_pickups(r,world):
 """Audit Poké Ball map objects and publish only statically verified pickups."""
 pickups={};items={};excluded=[];scanned=0
 for mid,m in sorted(world['maps'].items()):
  if not mid.startswith('johto_'):continue
  try:
   ev=r.ptr(int(m['sourceHeader'],16)+4);count=r.b[ev]
   if count>128:raise ValueError('object count')
   table=r.ptr(ev+4) if count else None
  except (KeyError,ValueError,IndexError,struct.error):continue
  for obj in normalize_objects(r,m):
   if obj.get('graphics')!=FIELD_ITEM_GRAPHICS:continue
   scanned+=1;q=table+obj['sourceObjectIndex']*24
   try:
    source_script=r.ptr(q+16);match=field_item_script(r,source_script);source_flag=r.u16(q+20)
   except (ValueError,IndexError,struct.error):match=None;source_script=None;source_flag=None
   if not match:
    excluded.append({'map':mid,'npc':obj['id'],'name':m.get('name',mid),'x':obj['x'],'y':obj['y'],
     'sourceObjectIndex':obj['sourceObjectIndex'],'sourceLocalId':obj.get('sourceLocalId',obj['id']),
     'sourceObjectOffset':hex(q),'sourceScript':hex(source_script) if source_script is not None else None,
     'reason':'No bounded linear standard item-give script on this Poké Ball object.'})
    continue
   item_id=match['sourceItemId'];item_key,item=sigma_item_definition(r,item_id)
   if item_key in items and items[item_key]['sourceId']!=item_id:raise ValueError('Sigma field-item key collision: '+item_key)
   items[item_key]=item;pickup_id=f'{mid}:{obj["id"]}'
   if pickup_id in pickups:raise ValueError('Duplicate Sigma pickup identity: '+pickup_id)
   pickups[pickup_id]={'id':pickup_id,'map':mid,'npc':obj['id'],'x':obj['x'],'y':obj['y'],'graphics':FIELD_ITEM_GRAPHICS,
    'item':item_key,'quantity':match['quantity'],'sourceItemId':item_id,'sourceScript':hex(source_script),
    'sourceGiveCommand':match['sourceGiveCommand'],'sourceObjectOffset':hex(q),'sourceObjectIndex':obj['sourceObjectIndex'],
    'sourceLocalId':obj.get('sourceLocalId',obj['id']),'sourceFlag':source_flag}
 field_item_count=len(items)
 # Evolution-item behavior remains an MMO feature. Keep every established
 # evolution item in the catalog even when that item has no verified field-ball
 # placement, while enriching any overlapping pickup with the same ROM identity.
 evolution={**STONES,**SIGMA_ITEMS}
 for item_id,(key,name) in evolution.items():
  if key not in items:
   extracted_key,item=sigma_item_definition(r,item_id)
   if extracted_key!=key:raise ValueError('Sigma evolution item key mismatch: '+key)
   item['fieldItem']=False;item['description']='Evolution item identified in the reviewed Johto / Sigma item catalog.'
   items[key]=item
  if items[key]['sourceId']!=item_id or normalize(items[key]['name'])!=normalize(name):raise ValueError('Sigma evolution item identity mismatch: '+key)
  items[key]['evolutionStone']=True
 audit={'spriteGraphics':FIELD_ITEM_GRAPHICS,'scannedPokeballObjects':scanned,'verifiedPickups':len(pickups),
  'excludedLookalikes':len(excluded),'uniqueItems':field_item_count,'catalogItems':len(items),'scriptPolicy':'Linear fixed-length path; VAR_8000 item + VAR_8001 quantity + callstd 1; no branches/calls/gotos executed.',
  'excluded':excluded}
 if (scanned,len(pickups),len(excluded),field_item_count)!=(386,361,25,125):
  raise ValueError(f'Unexpected Sigma item-ball audit counts: {(scanned,len(pickups),len(excluded),field_item_count)}')
 return pickups,items,audit


def extract_sigma_learnsets(r,world):
 """Read the relocated table used by the supplied Sigma engine."""
 table=r.ptr(0x3ea7c)
 if table!=0xa74f64:raise ValueError('Sigma active learnset table mismatch')
 result={};unsupported=[]
 for key,s in sorted(world['species'].items()):
  if s['source']!='johto':continue
  try:
   start=r.ptr(table+s['sourceId']*4);last=0;learnset=[]
   for index in range(128):
    value=r.u16(start+index*2)
    if value==65535:break
    level,move=value>>9,value&511
    if not 1<=level<=100 or str(move) not in world['moves'] or level<last:raise ValueError('unsupported move or out-of-order level')
    learnset.append([level,move]);last=level
   else:raise ValueError('unterminated learnset')
   if not learnset or learnset[0][0]!=1:raise ValueError('no level-one move in source learnset')
   result[key]={'learnset':learnset,'learnsetSource':'rom','learnsetProvenance':{'source':'johto','table':hex(table),'offset':hex(start),'sourceSpeciesId':s['sourceId']}}
  except (IndexError,ValueError,struct.error) as exc:unsupported.append({'species':key,'sourceSpeciesId':s['sourceId'],'reason':str(exc)})
 return result,unsupported

def extract(firered,sigma,root=ROOT):
 world=json.loads((root/'Server/data/world.json').read_text());manifest=json.loads((root/'Tools/extraction_manifest.json').read_text())
 recovered=root/'Server/data/interior_maps.json'
 if recovered.is_file():
  for key,m in json.loads(recovered.read_text()).items():world['maps'].setdefault(key,m)
 out={'format':1,'sources':{},'trainers':{},'gyms':[],'evolutions':{},'evolutionsBySource':{},'items':{},'itemPickups':{},'itemPickupAudit':{},'speciesOverrides':{},'normalizedObjects':{},'unsupported':{}}
 for tag,path in [('kanto',firered),('johto',sigma)]:
  r=Rom(path);digest=hashlib.sha256(r.b).hexdigest()
  # The extraction manifest was generated from the accepted matching ROMs.
  expected=next(s['sha256'] for s in manifest['sources'] if s['source']==tag)
  if digest!=expected:raise ValueError(f'{tag} ROM hash differs from the accepted asset source')
  lookup=species_lookup(world,manifest,tag)
  out['normalizedObjects'].update({mid:normalize_objects(r,m) for mid,m in world['maps'].items() if mid.startswith(tag+'_')})
  trainers,gyms,unresolved=extract_trainers(r,tag,world,lookup)
  evolutions,unsupported=extract_evolutions(r,tag,lookup,world)
  out['sources'][tag]={'sha256':digest,'bytes':len(r.b),'label':'FireRed USA/Europe Rev 1' if tag=='kanto' else 'Ultra Shiny Gold Sigma Completo 1.5.0',
   'trainerTable':hex(PROFILES[tag]['trainerTable']),'evolutionTable':hex(PROFILES[tag]['evolutionTable']),'evolutionSlots':PROFILES[tag]['evolutionSlots']}
  out['trainers'].update(trainers);out['gyms'].extend(gyms);out['evolutionsBySource'][tag]=evolutions
  out['unsupported'][tag]={'trainers':unresolved,'evolutions':unsupported}
  if tag=='johto':
   out['speciesOverrides'],learn_errors=extract_sigma_learnsets(r,world)
   out['unsupported'][tag]['learnsets']=learn_errors
   out['itemPickups'],out['items'],out['itemPickupAudit']=extract_sigma_item_pickups(r,world)
  for key,rules in evolutions.items():
   if world['species'][key]['source']==tag:out['evolutions'][key]=rules
 out['policy']={'sharedSpeciesEvolution':'Canonical source of the stable species key; region changes never change an owned Pokemon evolution rules.',
  'trainerRewards':'MMO-authored; source parties and coordinates do not imply original event scripts, rewards, held-item effects or trainer AI are executed.',
  'unsupportedScripts':'Unknown opcodes, ambiguous first teams, doubles and custom moves unavailable in the current move catalog are excluded.'}
 return out

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('firered',type=Path);parser.add_argument('sigma',type=Path);parser.add_argument('--root',type=Path,default=ROOT)
 args=parser.parse_args();result=extract(args.firered,args.sigma,args.root)
 dest=args.root/'Server/data/adventure_rom.json';dest.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 print(json.dumps({'trainers':len(result['trainers']),'gyms':result['gyms'],'evolutionSpecies':len(result['evolutions']),'itemPickups':len(result['itemPickups']),'fieldItems':len(result['items']),'output':str(dest)},indent=2))
if __name__=='__main__':main()
