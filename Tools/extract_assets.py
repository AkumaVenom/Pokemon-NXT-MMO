#!/usr/bin/env python3
"""Pokemon NXT MMO build-time GBA asset importer. Runtime never opens a ROM.
Sources: the user-supplied ROMs only. Formats documented by pret/pokefirered.
Requires Pillow and numpy. Rejects out-of-bounds pointers and invalid LZ streams.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
import numpy as np
from PIL import Image
CHARS={0:' ',0xad:'.',0xae:'-',0xab:'!',0xac:'?',0xb4:"'",0xb5:'♂',0xb6:'♀',0xba:':',0xb8:',',0xf0:':',0x1b:'é',0xb0:'…',0xf1:'ä',0xf2:'ö',0xf3:'ü',0xf4:'Ä',0xf5:'Ö',0xf6:'Ü'}
CHARS.update({0xbb+i:chr(65+i) for i in range(26)});CHARS.update({0xd5+i:chr(97+i) for i in range(26)});CHARS.update({0xa1+i:str(i) for i in range(10)})
def text(b):return ''.join(CHARS.get(x,'?') for x in b.split(b'\xff')[0])
def encode(s):return bytes(next(k for k,v in CHARS.items() if v==x) for x in s)
def writejson(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,separators=(',',':'),ensure_ascii=False),encoding='utf-8')
class Rom:
 def __init__(self,path):
  self.path=Path(path);self.b=self.path.read_bytes();self.errors=[];self.cache={};self.metacache={}
 def u16(self,o):return struct.unpack_from('<H',self.b,o)[0]
 def u32(self,o):return struct.unpack_from('<I',self.b,o)[0]
 def ptr(self,o):
  v=self.u32(o)-0x08000000
  if not 0<=v<len(self.b):raise ValueError(f'Invalid pointer at {o:x}')
  return v
 def validptr(self,o):
  try:self.ptr(o);return True
  except (ValueError,struct.error):return False
 def raw(self,o,n):
  if o<0 or o+n>len(self.b):raise ValueError('Range exceeds ROM')
  return self.b[o:o+n]
 def lz(self,o):
  if o in self.cache:return self.cache[o]
  if self.b[o]!=0x10:raise ValueError(f'Not LZ77 at {o:x}')
  n=self.u32(o)>>8
  if not 0<n<=2**20:raise ValueError('Invalid LZ size')
  p=o+4;out=bytearray()
  while len(out)<n:
   flags=self.b[p];p+=1
   for bit in range(7,-1,-1):
    if flags&(1<<bit):
     a,c=self.b[p:p+2];p+=2;ln=(a>>4)+3;dist=((a&15)<<8|c)+1
     if dist>len(out):raise ValueError('Invalid LZ back-reference')
     for _ in range(min(ln,n-len(out))):out.append(out[-dist])
    else:out.append(self.b[p]);p+=1
    if len(out)>=n:break
  result=bytes(out);self.cache[o]=result;return result
 def palette(self,o,compressed=False):return colors(self.lz(o)[:32] if compressed else self.raw(o,32))
 def sprite(self,raw,pal,w,h):
  need=w*h//2
  a=np.frombuffer(raw[:need],dtype=np.uint8)
  if len(a)!=need:raise ValueError('Sprite too short')
  pix=np.empty(need*2,dtype=np.uint8);pix[0::2]=a&15;pix[1::2]=a>>4
  pix=pix.reshape(h//8,w//8,8,8).transpose(0,2,1,3).reshape(h,w)
  rgba=pal[pix].copy();rgba[pix==0,3]=0
  return Image.fromarray(rgba)
 def map_table(self):
  for a in [0x5524c,0x55260]:
   try:
    t=self.ptr(a);g=self.ptr(t);h=self.ptr(g);l=self.ptr(h)
    if 1<=self.u32(l)<=256 and 1<=self.u32(l+4)<=256:return t
   except:pass
  raise ValueError('Unsupported ROM map table')
 def region_table(self):
  # FRLG stores section names as a pointer array, starting at section 0x58.
  t=0x3f1d1c if self.b[0xbc] else 0x3f1cac
  names={}
  for k in range(88,256):
   try:
    q=self.ptr(t+(k-88)*4);n=text(self.raw(q,64))
    if not n or len(n)>50 or n.count('?')>3:break
    names[k]=n.title()
   except:break
  return t,names
 def maps(self,tag,out):
  table=self.map_table();_,names=self.region_table();result={};pointers=[]
  for g in range(128):
   try:
    group=self.ptr(table+g*4);h=self.ptr(group);l=self.ptr(h)
    if not 1<=self.u32(l)<=256 or not 1<=self.u32(l+4)<=256:break
    pointers.append(group)
   except:break
  for g,group in enumerate(pointers):
   # Tables are contiguous in both supplied ROMs; also validate each header.
   nxt=min((p for p in pointers if p>group),default=table if table>group else group+1024)
   for m in range(min(256,max(1,(nxt-group)//4))):
    try:
     hp=self.ptr(group+m*4);lp=self.ptr(hp);w,h=self.u32(lp),self.u32(lp+4)
     if not (1<=w<=256 and 1<=h<=256 and w*h<=50000):break
     gp=self.ptr(lp+12);primary=self.ptr(lp+16);secondary=self.ptr(lp+20)
     if self.b[primary] not in (0,1) or self.b[secondary+1]!=1:break
     key=f'{tag}_{g}_{m}';grid=np.frombuffer(self.raw(gp,w*h*2),dtype='<u2').reshape(h,w);ids=grid&1023
     tiles,attrs=self.metatiles(primary,secondary)
     composite=tiles[ids].transpose(0,2,1,3,4).reshape(h*16,w*16,4)
     # Split layer assets preserve player occlusion under trees/roofs.
     layer=(attrs[ids]>>29)&3
     ground=composite.copy();overlay=np.zeros_like(composite)
     for mid in np.unique(ids):
      if ((attrs[mid]>>29)&3)==2:
       upper=self.meta_upper[mid]
       for yy,xx in np.argwhere(ids==mid):
        overlay[yy*16:yy*16+16,xx*16:xx*16+16]=upper
        ground[yy*16:yy*16+16,xx*16:xx*16+16]=self.meta_lower[mid]
     dest=out/'maps'/tag;dest.mkdir(parents=True,exist_ok=True)
     Image.fromarray(composite).save(dest/f'{g}_{m}.png')
     Image.fromarray(ground).save(dest/f'{g}_{m}_ground.png')
     has_overlay=bool(overlay[:,:,3].any())
     if has_overlay:Image.fromarray(overlay).save(dest/f'{g}_{m}_over.png')
     beh=(attrs[ids]&511).astype(int)
     collision=((grid>>10)&3).astype(int)
     events=[];warps=[];connections=[]
     if self.validptr(hp+4):
      ev=self.ptr(hp+4);oc,wc,cc,bc=self.b[ev:ev+4]
      if oc and self.validptr(ev+4):
       op=self.ptr(ev+4)
       for j in range(min(oc,128)):
        q=op+j*24
        x,y=struct.unpack_from('<hh',self.b,q+4)
        if 0<=x<w and 0<=y<h:events.append({'id':self.b[q],'graphics':self.b[q+1],'x':x,'y':y,'movement':self.b[q+9],'trainerType':self.u16(q+12)})
      if wc and self.validptr(ev+8):
       wp=self.ptr(ev+8)
       for j in range(min(wc,128)):
        q=wp+j*8;x,y=struct.unpack_from('<hh',self.b,q)
        warps.append({'x':x,'y':y,'elevation':self.b[q+4],'index':j,'targetIndex':self.b[q+5],'target':f'{tag}_{self.b[q+7]}_{self.b[q+6]}'})
     if self.validptr(hp+12):
      cp=self.ptr(hp+12);count=self.u32(cp)
      if 0<count<=16:
       p=self.ptr(cp+4)
       for j in range(count):
        q=p+j*12;connections.append({'direction':self.b[q],'offset':struct.unpack_from('<i',self.b,q+4)[0],'target':f'{tag}_{self.b[q+8]}_{self.b[q+9]}'})
     section=self.b[hp+20];name=names.get(section,f'{"Kanto" if tag=="kanto" else "Sigma"} Area {g}-{m}')
     result[key]={'id':key,'region':'Kanto' if tag=='kanto' else 'Johto / Sigma','name':name,'bank':g,'map':m,'width':w,'height':h,'mapType':self.b[hp+23],'section':section,'image':f'maps/{tag}/{g}_{m}.png','ground':f'maps/{tag}/{g}_{m}_ground.png','overlay':f'maps/{tag}/{g}_{m}_over.png' if has_overlay else None,'collision':collision.flatten().tolist(),'elevation':(grid>>12).flatten().tolist(),'behavior':beh.flatten().tolist(),'warps':warps,'connections':connections,'objects':events,'sourceHeader':hex(hp)}
    except Exception as e:
     self.errors.append(f'map {g}:{m}: {e}');continue
  return result
 def metatiles(self,primary,secondary):
  key=(primary,secondary)
  if key in self.metacache:
   alltiles,attrs,self.meta_lower,self.meta_upper=self.metacache[key];return alltiles,attrs
  pals=np.zeros((16,16,4),dtype=np.uint8);pals[:,:,3]=255
  for ts,start,end in [(primary,0,7),(secondary,7,13)]:
   pp=self.ptr(ts+8)
   for p in range(start,end):pals[p]=colors(self.raw(pp+p*32,32))
  # FRLG primary tile and metatile boundaries: 640 and 640.
  pixels=np.zeros((1024,8,8),dtype=np.uint8)
  for ts,start,maxcount in [(primary,0,640),(secondary,640,384)]:
   p=self.ptr(ts+4);raw=self.lz(p) if self.b[ts] else self.raw(p,maxcount*32)
   count=min(len(raw)//32,maxcount);a=np.frombuffer(raw[:count*32],dtype=np.uint8);v=np.empty(a.size*2,dtype=np.uint8);v[::2]=a&15;v[1::2]=a>>4;pixels[start:start+count]=v.reshape(count,8,8)
  lowers=np.zeros((1024,16,16,4),dtype=np.uint8);uppers=np.zeros_like(lowers);attrs=np.zeros(1024,dtype=np.uint32)
  for ts,start,count in [(primary,0,640),(secondary,640,384)]:
   mp=self.ptr(ts+12);ap=self.ptr(ts+20)
   for i in range(count):
    attrs[start+i]=self.u32(ap+i*4)
    for layer,dest in [(0,lowers),(1,uppers)]:
     for q in range(4):
      val=self.u16(mp+i*16+(layer*4+q)*2);pix=pixels[val&1023]
      if val&1024:pix=pix[:,::-1]
      if val&2048:pix=pix[::-1,:]
      col=pals[(val>>12)&15,pix].copy()
      if layer:col[pix==0,3]=0
      dest[start+i,(q//2)*8:(q//2)*8+8,(q%2)*8:(q%2)*8+8]=col
  alltiles=lowers.copy();mask=uppers[:,:,:,3]>0;alltiles[mask]=uppers[mask]
  self.meta_lower,self.meta_upper=lowers,uppers;self.metacache[key]=(alltiles,attrs,lowers,uppers)
  return alltiles,attrs
 def species(self,tag,out):
  f,b,p,s,ic,ip,ipt,n=[self.ptr(o) for o in range(0x128,0x148,4)]
  stats=self.ptr(0x1bc);result={};count=0
  for i in range(1,1500):
   try:
    fp=self.ptr(f+i*8);bp=self.ptr(b+i*8);pp=self.ptr(p+i*8);sp=self.ptr(s+i*8)
    if self.u16(f+i*8+6)!=i:break
    name=text(self.raw(n+i*11,11)).strip()
    if not name:continue
    pal=self.palette(pp,True);shine=self.palette(sp,True)
    directory=out/'pokemon'/tag;directory.mkdir(parents=True,exist_ok=True)
    for typ,ptr,cols in [('front',fp,pal),('back',bp,pal),('shiny',fp,shine),('back_shiny',bp,shine)]:self.sprite(self.lz(ptr),cols,64,64).save(directory/f'{i}_{typ}.png')
    iconpath=None
    try:
     idx=self.b[ip+i];palette=self.palette(self.ptr(ipt+idx*8));raw=self.raw(self.ptr(ic+i*4),1024)
     sheet=Image.new('RGBA',(64,32));sheet.paste(self.sprite(raw[:512],palette,32,32),(0,0));sheet.paste(self.sprite(raw[512:],palette,32,32),(32,0));sheet.save(directory/f'{i}_icon.png');iconpath=f'pokemon/{tag}/{i}_icon.png'
    except Exception as e:self.errors.append(f'icon {i}: {e}')
    d=self.raw(stats+i*28,28)
    result[str(i)]={'id':i,'name':name.title(),'baseStats':list(d[:6]),'types':list(d[6:8]),'catchRate':d[8],'baseExperience':d[9],'growth':d[19],'front':f'pokemon/{tag}/{i}_front.png','back':f'pokemon/{tag}/{i}_back.png','shiny':f'pokemon/{tag}/{i}_shiny.png','backShiny':f'pokemon/{tag}/{i}_back_shiny.png','icon':iconpath}
    count+=1
   except Exception as e:self.errors.append(f'species {i}: {e}');continue
  return result
 def objects(self,tag,out):
  # Find canonical player-info struct by field layout, then pointer array.
  candidates=[];pattern=struct.pack('<H',0xffff)
  a=np.frombuffer(self.b[:len(self.b)//4*4],dtype='<u4')
  for o in range(0x300000,min(len(self.b)-36,0x1100000),4):
   if self.b[o:o+2]!=pattern:continue
   try:
    if self.u16(o+8)==16 and self.u16(o+10)==32 and self.u16(o+6) in (256,512) and self.validptr(o+28) and self.validptr(o+16):candidates.append(o)
   except:pass
  tables=[]
  valid=set(candidates)
  for o in candidates:
   needle=struct.pack('<I',o+0x8000000);pos=0
   while True:
    pos=self.b.find(needle,pos)
    if pos<0:break
    if pos%4==0:
     try:
      p1=self.ptr(pos+4);p2=self.ptr(pos+8)
      if self.u16(p1)==65535 and self.u16(p2)==65535 and self.u16(p1+8)==32:tables.append(pos)
     except:pass
    pos+=1
  # Known table pointers act only as candidates; every entry is validated.
  tables=[0x39fe20 if self.b[0xbc] else 0x39fdb0]+tables
  table=None
  for t in tables:
   try:
    p=self.ptr(t)
    if self.u16(p)==65535 and self.u16(p+8)==16 and self.u16(p+10)==32:table=t;break
   except:pass
  if table is None:self.errors.append('object pointer table not located');return {}
  # Palette registry entries consist of data pointer, palette tag, zero padding.
  palmap={}
  for o in range(0x300000,len(self.b)-8,4):
   if self.b[o+6:o+8]!=b'\0\0':continue
   t=self.u16(o+4)
   if 0x1100<=t<=0x1130 and self.validptr(o):
    pp=self.ptr(o)
    try:
     vals=struct.unpack('<16H',self.raw(pp,32))
     if max(vals)<32768:palmap.setdefault(t,pp) # first canonical registry; later matches are reflection tag arrays
    except:pass
  result={};directory=out/'objects'/tag;directory.mkdir(parents=True,exist_ok=True)
  for i in range(240):
   try:
    q=self.ptr(table+i*4)
    if self.u16(q)!=65535:break
    w,h=self.u16(q+8),self.u16(q+10)
    if w not in (8,16,32,64,88,96) or h not in (8,16,32,64,96):break
    paletteTag=self.u16(q+2);pp=palmap.get(paletteTag)
    if pp is None:continue
    pal=self.palette(pp);frameTable=self.ptr(q+28);frames=[]
    for f in range(18):
     try:
      p=self.ptr(frameTable+8*f);sz=self.u16(frameTable+8*f+4)
      if sz!=w*h//2:break
      frames.append(self.sprite(self.raw(p,sz),pal,w,h))
     except:break
    if not frames:continue
    sheet=Image.new('RGBA',(w*len(frames),h))
    for f,img in enumerate(frames):sheet.paste(img,(f*w,0))
    sheet.save(directory/f'{i}.png');result[str(i)]={'id':i,'width':w,'height':h,'frames':len(frames),'image':f'objects/{tag}/{i}.png','palette':hex(paletteTag),'visibleTop':min((im.getbbox()[1] for im in frames[:3] if im.getbbox()),default=0)}
   except Exception as e:self.errors.append(f'object {i}: {e}')
  return result

def colors(raw):
 a=np.frombuffer(raw,dtype='<u2');c=np.zeros((len(a),4),dtype=np.uint8);c[:,0]=(a&31)*255//31;c[:,1]=((a>>5)&31)*255//31;c[:,2]=((a>>10)&31)*255//31;c[:,3]=255;return c

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--firered',required=True);ap.add_argument('--sigma',required=True);ap.add_argument('--output',required=True);args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 manifest={'format':1,'maps':{},'catalogs':{},'objects':{},'sources':[]}
 for tag,file in [('kanto',args.firered),('johto',args.sigma)]:
  rom=Rom(file);print('Extracting',tag,flush=True)
  maps=rom.maps(tag,out);print('Maps',len(maps),flush=True);species=rom.species(tag,out);print('Species',len(species),flush=True);objects=rom.objects(tag,out);print('Objects',len(objects),flush=True)
  manifest['maps'].update(maps);manifest['catalogs'][tag]=species;manifest['objects'][tag]=objects
  manifest['sources'].append({'source':tag,'filename':Path(file).name,'sha256':hashlib.sha256(rom.b).hexdigest(),'size':len(rom.b),'revision':rom.b[0xbc],'mapTable':hex(rom.map_table()),'maps':len(maps),'species':len(species),'objects':len(objects),'warnings':rom.errors})
 writejson(out/'manifest.json',manifest)
 print('Done',len(manifest['maps']),'maps')
if __name__=='__main__':main()
