#!/usr/bin/env python3
"""Promote verified extracted content to versioned, ROM-independent game packs."""
from pathlib import Path
import json,sys,struct,hashlib,re,collections
from extract_assets import Rom,text,writejson
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'Client/app/assets';D=ROOT/'Server/data'

def learnsets(r):
 sig=struct.pack('<HHH',545,2093,3657) # FR Bulbasaur: Lv1 Tackle, Lv4 Growl, Lv7 Leech Seed.
 p=r.b.find(sig)
 if p<0:return {}
 ref=r.b.find(struct.pack('<I',p+0x8000000));t=ref # species NONE intentionally aliases Bulbasaur before species 1
 result={}
 for i in range(1,412):
  try:
   q=r.ptr(t+i*4);lst=[]
   for j in range(100):
    v=r.u16(q+j*2)
    if v==65535:break
    lv,move=v>>9,v&511
    if not 1<=lv<=100 or not 1<=move<=354:raise ValueError('invalid learnset')
    lst.append([lv,move])
   result[i]=lst
  except:pass
 return result

def encounters(r,tag,mapids):
 # Find validated headers by structure, not by an assumed first map ID. Sigma
 # relocates and extends the table, and its first encounter map differs from FR.
 import numpy as np
 words=np.frombuffer(r.b[:len(r.b)//4*4],dtype='<u4')
 known={int(k.split('_')[1])|(int(k.split('_')[2])<<8) for k in mapids if k.startswith(tag+'_')}
 candidates=np.flatnonzero(np.isin(words,list(known)))
 headers={}
 for wi in candidates:
  wi=int(wi);q=wi*4
  if wi+4>=len(words):continue
  ps=words[wi+1:wi+5]
  if not np.any(ps) or not np.all((ps==0)|((ps>=0x8000000)&(ps<0x8000000+len(r.b)))):continue
  try:
   slots={}
   for typ,offset,count in [('land',4,12),('water',8,5),('rock',12,5),('fishing',16,10)]:
    if r.u32(q+offset)==0:continue
    info=r.ptr(q+offset)
    if not 1<=r.b[info]<=100 or r.b[info+1:info+4]!=b'\0\0\0':raise ValueError('rate')
    p=r.ptr(info+4);ss=[]
    for n in range(count):
     lo,hi,mon=struct.unpack_from('<BBH',r.b,p+n*4)
     if not (1<=lo<=hi<=100 and 0<mon<1500):raise ValueError('slot')
     ss.append({'min':lo,'max':hi,'sourceId':mon})
    slots[typ]=ss
   headers[q]=(f'{tag}_{r.b[q]}_{r.b[q+1]}',slots)
  except (ValueError,IndexError,struct.error):pass
 # Prefer the longest contiguous, validated table; never combine stale original
 # tables with the relocated active table solely because their headers are valid.
 chains=[]
 for q in headers:
  if q-20 in headers:continue
  chain=[];p=q
  while p in headers:chain.append(headers[p]);p+=20
  chains.append((len(chain),q,chain))
 if not chains:return {}
 length,start,best=max(chains)
 print(tag,'encounter table',hex(start),'entries',length)
 return dict(best)

def main():
 raw=json.loads(((A/'manifest.json') if (A/'manifest.json').exists() else ROOT/'Tools/extraction_manifest.json').read_text());roms={tag:Rom(path) for tag,path in [('kanto',sys.argv[1]),('johto',sys.argv[2])]}
 catalog={};lookup={'kanto':{},'johto':{}};byname={}
 for tag,source in raw['catalogs'].items():
  for n,s in source.items():
   i=int(n);name=s['name'];norm=re.sub(r'[^a-z0-9]','',name.lower())
   if tag=='kanto' and (252<=i<=276 or i>411):continue
   if not norm or '?' in name or 'Unused' in name or min(s['baseStats'])<1 or max(s['types'])>18:continue
   if norm in byname:lookup[tag][n]=byname[norm];continue
   key=f'{"fr" if tag=="kanto" else "sg"}_{i}'
   s=dict(s);s.update({'key':key,'source':tag,'sourceId':i,'name':name.replace('?','’')});s.pop('id',None)
   catalog[key]=s;lookup[tag][n]=key;byname[norm]=key
 learns=learnsets(roms['kanto']);moves={};r=roms['kanto'];mp=r.ptr(0x1cc);np=r.ptr(0x148)
 # Gen III moves; variable-power and advanced side effects have documented alpha limits.
 for i in range(1,355):
  b=r.raw(mp+i*12,12)
  moves[str(i)]={'id':i,'name':text(r.raw(np+i*13,13)).title(),'effect':b[0],'power':b[1],'type':b[2],'accuracy':b[3],'pp':b[4],'chance':b[5],'target':b[6],'priority':struct.unpack('b',b[7:8])[0]}
 fallback={0:33,1:2,2:16,3:40,4:189,5:88,6:141,7:122,8:232,10:52,11:55,12:22,13:84,14:93,15:181,16:82,17:44,18:33}
 for key,s in catalog.items():
  if s['source']=='kanto':s['learnset']=learns.get(s['sourceId'],[[1,33],[5,fallback.get(s['types'][0],33)]])
  else:s['learnset']=[[1,33],[4,fallback.get(s['types'][0],33)],[10,98],[15,44]]
  s['learnsetSource']='rom' if s['source']=='kanto' and s['sourceId'] in learns else 'alpha-type-template'
 for tag,r in roms.items():
  table=encounters(r,tag,raw['maps']);print(tag,'wild maps',len(table),'learnsets',len(learns))
  for k,m in raw['maps'].items():
   if not k.startswith(tag):continue
   _,names=r.region_table();m['name']=names.get(m['section'],m['name']).replace('?',"'")
   converted={}
   for terrain,slots in table.get(k,{}).items():
    vals=[]
    for slot in slots:
     key=lookup[tag].get(str(slot['sourceId']))
     if key:vals.append({'species':key,'min':slot['min'],'max':slot['max']})
    if vals:converted[terrain]=vals
   m['encounters']=converted;m['encounterSource']='rom' if converted else 'alpha-fallback'
 # Use an authored low-level fallback only where the native table is absent or custom-scripted.
 for m in raw['maps'].values():
  if not m['encounters']:
   ids=[16,19,10,13,25] if m['id'].startswith('kanto') else [161,163,165,167,187,179]
   m['encounters']={'land':[{'species':f'fr_{i}','min':3,'max':7} for i in ids]}
  # Named source map IDs remain stable forever; content updates must not renumber them.
  safe=[]
  for y in range(1,m['height']-1):
   for x in range(1,m['width']-1):
    j=y*m['width']+x
    if m['collision'][j]==0 and m['behavior'][j] not in list(range(16,28))+list(range(96,114)) and (x,y) not in {(w['x'],w['y']) for w in m['warps']}:
     safe.append((abs(x-m['width']//2)+abs(y-m['height']//2),x,y))
  m['playable']=bool(safe)
  m['spawn']=list(min(safe)[1:]) if safe else [0,0]
  if m['id']=='kanto_3_0':m['spawn']=[10,10]
  if m['id']=='johto_3_0':m['spawn']=[17,10]
 world={'format':1,'version':'0.1.0-alpha','maps':raw['maps'],'species':catalog,'moves':moves,'objects':raw['objects'],'homes':{'Kanto':'kanto_3_0','Johto':'johto_3_0'},'starters':['fr_1','fr_4','fr_7','fr_152','fr_155','fr_158'],'items':{'pokeball':{'name':'Poke Ball','price':200,'capture':1},'greatball':{'name':'Great Ball','price':600,'capture':1.5},'ultraball':{'name':'Ultra Ball','price':1200,'capture':2},'potion':{'name':'Potion','price':300,'heal':20},'superpotion':{'name':'Super Potion','price':700,'heal':50}}}
 pack=hashlib.sha256(json.dumps(world,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24];world['pack']=pack
 D.mkdir(parents=True,exist_ok=True);writejson(D/'world.json',world)
 for k,m in raw['maps'].items():writejson(A/'world/maps'/f'{k}.json',{a:v for a,v in m.items() if a not in ('encounters','encounterSource','sourceHeader')})
 summaries={k:{a:m[a] for a in ['id','name','region','width','height','mapType','spawn','bank','map','section','playable']} for k,m in raw['maps'].items()}
 client={k:world[k] for k in ['version','pack','species','moves','objects','homes','starters','items']};client['maps']=summaries
 writejson(A/'world/client.json',client)
 report={'version':world['version'],'pack':pack,'maps':len(raw['maps']),'catalogEntries':len(catalog),'mapsWithWalkableSpawn':sum(m['playable'] for m in raw['maps'].values()),'learnsetsFromFireRed':len(learns),'sources':raw['sources'],'limitations':['No ARM machine code, ROM images, original event scripts or music player are shipped.','Native static maps and object-frame sheets were decoded. Tile animation and original story scripting are not executed.','Follower animation uses extracted two-frame party icons, not a complete directional overworld Pokemon set.','Sigma species without a compatible FireRed learnset use explicit alpha type templates.','A decoded map is not evidence that every original scripted passage or story sequence is implemented.']}
 writejson(ROOT/'Docs/ASSET_REPORT.json',report)
 # Move the large raw extraction manifest out of runtime; it is a build/audit artifact.
 writejson(ROOT/'Tools/extraction_manifest.json',raw)
 (A/'manifest.json').unlink(missing_ok=True)
 from repack_content import publish
 publish(world,ROOT)
 print('Prepared native content from supplied source files.')
if __name__=='__main__':main()
