"""Versioned content registry and immutable creature factories."""
from __future__ import annotations
import json,math,secrets,uuid
from pathlib import Path
from .growth import Growth
TYPES=['Normal','Fighting','Flying','Poison','Ground','Rock','Bug','Ghost','Steel','Mystery','Fire','Water','Grass','Electric','Psychic','Ice','Dragon','Dark','Fairy']
NATURES=['Hardy','Lonely','Brave','Adamant','Naughty','Bold','Docile','Relaxed','Impish','Lax','Timid','Hasty','Serious','Jolly','Naive','Modest','Mild','Quiet','Bashful','Rash','Calm','Gentle','Sassy','Careful','Quirky']
class Content:
 def __init__(self,path:Path):
  self.source_path=path
  d=json.loads(path.read_text(encoding='utf-8'));self.data=d;self.maps=d['maps'];self.species=d['species'];self.moves=d['moves'];self.pack=d['pack'];self.items=d['items'];self.rng=secrets.SystemRandom()
  self.growth=Growth(self)
  if d['format']!=1:raise RuntimeError('Unsupported world content format')
  for k,m in self.maps.items():
   n=m['width']*m['height']
   if any(len(m[f])!=n for f in ('collision','behavior','elevation')):raise RuntimeError(f'Invalid collision map: {k}')
 def xp(self,level,growth=0):
  n=level
  if n<=1:return 0
  if growth==1:
   if n<=50:v=n**3*(100-n)//50
   elif n<=68:v=n**3*(150-n)//100
   elif n<=98:v=n**3*((1911-10*n)//3)//500
   else:v=n**3*(160-n)//100
  elif growth==2:
   if n<=15:v=n**3*((n+1)//3+24)//50
   elif n<=36:v=n**3*(n+14)//50
   else:v=n**3*(n//2+32)//50
  elif growth==3:v=6*n**3//5-15*n*n+100*n-140
  elif growth==4:v=4*n**3//5
  elif growth==5:v=5*n**3//4
  else:v=n**3
  return max(0,v)
 def stats(self,mon):
  s=self.species[mon['species']];n=mon['level'];iv=mon['ivs'];nature=mon['nature'];boost,drop=nature//5,nature%5;order=[1,2,3,4,5]
  out=[]
  for i,base in enumerate(s['baseStats']):
   raw=(2*base+iv[i])*n//100
   if i==0:val=1 if s['name']=='Shedinja' else raw+n+10
   else:
    val=raw+5
    if boost!=drop:
     if i==order[boost]:val=val*110//100
     elif i==order[drop]:val=val*90//100
   out.append(val)
  return out
 def new_mon(self,key,level,owner='Wild'):
  if key not in self.species or not 1<=level<=100:raise ValueError('Invalid creature')
  s=self.species[key];ids=[]
  for lv,mid in s['learnset']:
   # Native initial assignment stops at the first over-level ROM row. Do not
   # sort a profile or fabricate Tackle when no native move has been earned.
   if lv>level:break
   if str(mid) in self.moves and mid not in ids:
    if len(ids)==4:ids.pop(0)
    ids.append(mid)
  mon={'uid':str(uuid.uuid4()),'species':key,'level':level,'exp':self.xp(level,s['growth']),'ivs':[self.rng.randrange(32) for _ in range(6)],'nature':self.rng.randrange(25),'originalTrainer':owner,'shiny':self.rng.randrange(8192)==0,'status':'','sleep':0,'moves':[{'id':mid,'pp':self.moves[str(mid)]['pp']} for mid in ids[-4:]]}
  mon['hp']=self.stats(mon)[0];self.growth.ensure(mon);self.growth.stamp_move_namespace(mon);return mon
 def gain_xp(self,mon,amount):
  self.growth.ensure(mon);s=self.species[mon['species']];old=mon['level'];oldhp=self.stats(mon)[0];hp=mon['hp']
  mon['exp']=min(self.xp(100,s['growth']),mon['exp']+max(0,int(amount)))
  while mon['level']<100 and mon['exp']>=self.xp(mon['level']+1,s['growth']):mon['level']+=1
  if mon['level']>old:
   maximum=self.stats(mon)[0];mon['hp']=min(maximum,max(1,hp+maximum-oldhp)) if hp>0 else 0
   self.growth.queue_moves(mon,old,mon['level'])
  return mon['level']-old
 def public_mon(self,mon,private=True):
  s=self.species[mon['species']];v={k:mon[k] for k in ('uid','species','level','hp','shiny','status')};v.update({'name':s['name'],'maxHp':self.stats(mon)[0]})
  if private:v.update({'moves':mon['moves'],'exp':mon['exp'],'nextExp':self.xp(min(100,mon['level']+1),s['growth']),'levelExp':self.xp(mon['level'],s['growth']),'stats':self.stats(mon),'nature':NATURES[mon['nature']],'originalTrainer':mon['originalTrainer'],'pendingLearn':self.growth.pending_moves(mon),'relearnMoves':self.growth.reminder_options(mon),'levelUpMoves':self.growth.level_up_moves(mon),'evolutions':self.growth.options(mon)})
  return v
 def heal(self,mon):
  mon['hp']=self.stats(mon)[0];mon['status']='';mon['sleep']=0
  for m in mon['moves']:m['pp']=self.moves[str(m['id'])]['pp']
