"""Authoritative single battles. Never accepts client damage, HP, RNG or rewards.

This alpha implements ordinary damage, STAB, type matchups, accuracy, priority,
PP, six-member switching, common status moves and capture. It does NOT claim
full original ROM battle-script compatibility. See Docs/ALPHA_SCOPE.md.
"""
from __future__ import annotations
import copy,math,time,uuid
from .security import RequestError,require,integer
from .varieties import variety_key
# Each entry: super-effective, resisted, immune. Gen III chart, Fairy extension.
CHART={0:([],[5,8],[7]),1:([0,5,8,15,17],[2,3,6,14,18],[7]),2:([1,6,12],[5,8,13],[]),3:([12,18],[3,4,5,7],[8]),4:([3,5,8,10,13],[6,12],[2]),5:([2,6,10,15],[1,4,8],[]),6:([12,14,17],[1,2,3,7,8,10,18],[]),7:([7,14],[8,17],[0]),8:([5,15,18],[8,10,11,13],[]),10:([6,8,12,15],[5,10,11,16],[]),11:([4,5,10],[11,12,16],[]),12:([4,5,11],[2,3,6,8,10,12,16],[]),13:([2,11],[12,13,16],[4]),14:([1,3],[8,14],[17]),15:([2,4,12,16],[8,10,11,15],[]),16:([16],[8],[18]),17:([7,14],[1,8,17,18],[]),18:([1,16,17],[3,8,10],[])}
STATUS_MOVES={14,28,39,43,45,46,73,74,77,78,79,81,86,92,97,100,105,106,108,110,111,116,135,150,156,182,208,235,236}
FIXED={49:20,69:-1,82:40,101:-1,162:-2}
SIGMA_MOVE_IDS={183,210,237,294,295,297,346}
def sigma_variant(move):
 """Only the explicitly published renamed Sigma records have source mechanics.

 Their raw effect/category fields describe this ROM's adaptations, which need
 not match later games with the same move names. Canonical move IDs keep the
 existing alpha behavior, including its incomplete battle-script support.
 """
 source_id=move.get('sourceMoveId')
 return move.get('source')=='johto' and source_id in SIGMA_MOVE_IDS and move.get('id')==1024+source_id
def matchup(kind,defenders):
 sup,res,immune=CHART.get(kind,([],[],[]));v=1
 for d in set(defenders):v*=0 if d in immune else 2 if d in sup else .5 if d in res else 1
 return v
def stage(n):return (2+n)/2 if n>=0 else 2/(2-n)
class Battle:
 def __init__(self,content,kind,players,names,rosters,items,turn_seconds=45,audio_source='kanto'):
  self.c=content;self.id=str(uuid.uuid4());self.kind=kind;self.players=players;self.names=names;self.rosters=copy.deepcopy(rosters);self.items=copy.deepcopy(items);self.active=[next((i for i,m in enumerate(r) if m['hp']>0),0) for r in self.rosters];self.stages={};self.choice={};self.turn=1;self.turn_seconds=turn_seconds;self.deadline=time.monotonic()+turn_seconds;self.ended=False;self.winner=None;self.caught=None;self.logs=[f'{names[1]} appeared!' if kind=='wild' else f'{names[0]} vs {names[1]}.'];self.seeded=set();self.protected=set();self.rewarded=False
  self.experience_events=[];self.experience_awarded=set();self.participants={};self._record_participant()
  self.audio_source=audio_source if audio_source in ('kanto','johto') else 'kanto';self.audio_revision=0;self.audio_events=[]
  self.audio('battle_start',kind=kind)
  for side in (1,0):self.sendout_audio(side)
 def _record_participant(self):
  if self.kind!='duel' and self.mon(0)['hp']>0 and self.mon(1)['hp']>0:self.participants.setdefault(self.mon(1)['uid'],set()).add(self.mon(0)['uid'])
 def audio(self,cue,side=None,**data):
  """Presentation metadata only. World publishes resolved batches after commit.

  Event IDs survive repeated/waiting snapshots, so clients can deduplicate them.
  Audio never draws RNG or influences battle state and cannot accept client cues.
  """
  event={'id':f'{self.id}:{self.audio_revision}:{len(self.audio_events)}','cue':cue,'source':self.audio_source,**data}
  if side is not None:
   event['side']=side
   mon=self.mon(1-side if cue.startswith('capture_') else side)
   if event.get('species')==mon['species']:
    event.update(uid=mon['uid'],variety=variety_key(mon),shiny=variety_key(mon)=='shiny')
  self.audio_events.append(event)
 def reset_audio(self):self.audio_revision+=1;self.audio_events=[]
 def sendout_audio(self,side):
  mon=self.mon(side);self.stages.pop(mon['uid'],None);self.seeded.discard(mon['uid']);self._record_participant();self.audio('sendout',side,species=mon['species'])
  if variety_key(mon)=='shiny':self.audio('shiny',side,species=mon['species'])
 def audio_view(self,side):
  events=[]
  for original in self.audio_events:
   event=dict(original)
   if 'side' in event:event['side']='you' if event['side']==side else 'opponent'
   if event['cue']=='battle_end':event['result']=self.result(side)
   events.append(event)
  return {'revision':self.audio_revision,'events':events}
 def result(self,side):return None if not self.ended else 'caught' if self.caught else 'won' if self.winner==side else 'lost' if self.winner is not None else 'escaped'
 def mon(self,side):return self.rosters[side][self.active[side]]
 def name(self,m):return self.c.varieties.display_name(m)
 def tiers(self,m):return self.stages.setdefault(m['uid'],[0]*7)
 def usable(self,mon):
  usable=[]
  for i,m in enumerate(mon['moves']):
   move=self.c.moves[str(m['id'])]
   if m['pp']>0 and (move['power']>0 or m['id'] in STATUS_MOVES or m['id'] in FIXED or sigma_variant(move) and move['effect']==32):usable.append(i)
  return usable
 def choose(self,side,data):
  require(not self.ended,'This battle has ended.');require(side not in self.choice,'Your action is already queued.');kind=data.get('action');m=self.mon(side)
  if kind=='attack':
   slot=integer(data.get('slot'),-1,3,'Move slot');usable=self.usable(m)
   require((slot in usable) or (slot==-1 and not usable),'That move is unavailable in this alpha or has no PP.')
   action={'action':kind,'slot':slot}
  elif kind=='switch':
   uid=data.get('uid');idx=next((i for i,q in enumerate(self.rosters[side]) if q['uid']==uid),-1)
   require(idx>=0 and idx!=self.active[side] and self.rosters[side][idx]['hp']>0,'Select a healthy party member other than your active Pokemon.');action={'action':kind,'index':idx}
  elif kind in ('capture','item'):
   require(self.kind!='duel','Items are disabled in friendly duels.');item=data.get('item');require(item in self.c.items and self.items[side].get(item,0)>0,'You do not have that item.')
   if kind=='capture':require(self.kind=='wild' and 'capture' in self.c.items[item],"You can only capture wild Pokemon with a Poke Ball.")
   else:require('heal' in self.c.items[item] and m['hp']<self.c.stats(m)[0],"That healing item cannot be used now.")
   action={'action':kind,'item':item}
  elif kind=='run':
   require(self.kind!='trainer',"You cannot run from a trainer battle.");action={'action':kind}
  else:raise RequestError('Unknown battle action.')
  self.choice[side]=action
  if self.kind=='duel' and kind=='run' and 1-side not in self.choice:
   valid=self.usable(self.mon(1-side));self.choice[1-side]={'action':'attack','slot':valid[0] if valid else -1}
  if self.players[1] is None and side==0:
   valid=self.usable(self.mon(1));self.choice[1]={'action':'attack','slot':self.c.rng.choice(valid) if valid else -1}
 def timeout(self):
  if self.ended or time.monotonic()<self.deadline:return False
  for side in range(2):
   if side not in self.choice:
    if self.kind=='trainer' and side==1:
     valid=self.usable(self.mon(side));self.choice[side]={'action':'attack','slot':valid[0] if valid else -1}
    else:self.choice[side]={'action':'forfeit' if self.kind=='trainer' else 'run'}
  return True
 def view(self,side):
  return {'id':self.id,'kind':self.kind,'source':self.audio_source,'turn':self.turn,'you':self.c.public_mon(self.mon(side)),'opponent':self.c.public_mon(self.mon(1-side),False),'opponentName':self.names[1-side],'party':[self.c.public_mon(m) for m in self.rosters[side]],'opponentRemaining':sum(m['hp']>0 for m in self.rosters[1-side]),'waiting':side in self.choice,'canRun':self.kind!='trainer','seconds':max(0,int(self.deadline-time.monotonic())),'usable':self.usable(self.mon(side)),'log':self.logs[-18:],'ended':self.ended,'result':self.result(side),'audio':self.audio_view(side)}
 def _priority(self,s):
  a=self.choice[s];m=self.mon(s);priority={'forfeit':11,'run':10,'switch':6,'capture':5,'item':5}.get(a['action'],0)
  if a['action']=='attack' and a['slot']>=0:priority=self.c.moves[str(m['moves'][a['slot']]['id'])]['priority']
  speed=self.c.stats(m)[3]*stage(self.tiers(m)[3]);speed*=.25 if m['status']=='paralysis' else 1
  return priority,speed,self.c.rng.random()
 def resolve(self):
  require(len(self.choice)==2,'Waiting for both trainers.');self.protected=set();self.logs=[];self.experience_events=[];self._record_participant();self.reset_audio()
  for side in sorted((0,1),key=self._priority,reverse=True):
   if self.ended:break
   m=self.mon(side);enemy=self.mon(1-side);a=self.choice[side]
   if m['hp']<=0:continue
   k=a['action']
   if k in ('run','forfeit'):
    self.ended=True;self.winner=1-side if self.kind=='duel' or k=='forfeit' else None;self.logs.append(f'{self.names[side]} '+('forfeited after the turn timer expired.' if k=='forfeit' else 'withdrew from battle.'));self.audio('escape',side);break
   if k=='switch':self.active[side]=a['index'];self.logs.append(f'{self.names[side]} sent out {self.name(self.mon(side))}!');self.sendout_audio(side);continue
   if k=='item':
    item=a['item'];self.items[side][item]-=1;old=m['hp'];m['hp']=min(self.c.stats(m)[0],m['hp']+self.c.items[item]['heal']);self.logs.append(f'{self.name(m)} recovered {m["hp"]-old} HP.');self.audio('recover',side,species=m['species'],item=item,amount=m['hp']-old);continue
   if k=='capture':
    item=a['item'];self.items[side][item]-=1;hp=self.c.stats(enemy)[0];sp=self.c.species[enemy['species']];bonus=2 if enemy['status']=='sleep' else 1.5 if enemy['status'] else 1
    chance=min(1,((3*hp-2*enemy['hp'])*sp['catchRate']*self.c.items[item]['capture']*bonus)/(3*hp*255))
    self.audio('capture_throw',side,item=item,species=enemy['species'])
    if self.c.rng.random()<chance:self.caught=copy.deepcopy(enemy);self.caught['originalTrainer']=self.names[side];self.ended=True;self.winner=side;self.logs.append(f'Gotcha! {self.name(enemy)} was caught!');self.audio('capture_success',side,species=enemy['species']);break
    self.logs.append(f'{self.name(enemy)} broke free!');self.audio('capture_fail',side,species=enemy['species']);continue
   if m['status']=='sleep':
    m['sleep']=max(0,m.get('sleep',1)-1)
    if m['sleep']>0:self.logs.append(f'{self.name(m)} is asleep.');self.audio('status',side,species=m['species'],status='sleep');continue
    m['status']='';self.logs.append(f'{self.name(m)} woke up!');self.audio('status_clear',side,species=m['species'],status='sleep')
   if m['status']=='paralysis' and self.c.rng.random()<.25:self.logs.append(f'{self.name(m)} is fully paralyzed.');self.audio('status',side,species=m['species'],status='paralysis');continue
   slot=a['slot'];mid=165 if slot==-1 else m['moves'][slot]['id'];move=self.c.moves[str(mid)];variant=sigma_variant(move)
   if slot>=0:m['moves'][slot]['pp']-=1
   self.logs.append(f'{self.name(m)} used {move["name"]}!');self.audio('move',side,species=m['species'],move=mid,moveType=move['type'])
   # Sigma's Roost and Aqua Ring both select the native Recover effect. They
   # heal the user immediately; no unverified later-generation behavior is added.
   if variant and move['effect']==32:self._status(side,mid);continue
   # Stat slots 1..5 match Content.stats; unused HP slot 0 stores accuracy so
   # Special Defense changes never also change a Pokemon's chance to hit.
   accuracy=move['accuracy'] or 100;accstage=self.tiers(m)[0]-self.tiers(enemy)[6];accuracy*=((3+accstage)/3 if accstage>=0 else 3/(3-accstage))
   if self.c.rng.randrange(100)>=accuracy:self.logs.append('The attack missed!');self.audio('miss',side);continue
   if enemy['uid'] in self.protected:self.logs.append(f'{self.name(enemy)} protected itself.');self.audio('protected',1-side,species=enemy['species']);continue
   if move['power']==0 and mid not in FIXED:self._status(side,mid);continue
   typ=move['type'];mult=matchup(typ,self.c.species[enemy['species']]['types'])
   if mid==165:mult=1
   if mult==0:self.logs.append('It had no effect.');self.audio('no_effect',1-side);continue
   critical=False
   if mid in FIXED:
    fixed=FIXED[mid];damage=m['level'] if fixed==-1 else max(1,enemy['hp']//2) if fixed==-2 else fixed
   else:
    physical=move['category']==0 if variant else typ<=8;ai,di=(1,2) if physical else (4,5);attack=self.c.stats(m)[ai]*stage(self.tiers(m)[ai]);defense=self.c.stats(enemy)[di]*stage(self.tiers(enemy)[di]);attack*=.5 if physical and m['status']=='burn' else 1
    power=move['power'];power=60 if power<=1 else power
    raw=((2*m['level']//5+2)*power*attack/max(1,defense)/50)+2
    stab=1.5 if typ in self.c.species[m['species']]['types'] else 1;critical=self.c.rng.randrange(16)==0;damage=max(1,int(raw*stab*mult*(2 if critical else 1)*self.c.rng.randint(85,100)/100))
    if critical:self.logs.append('A critical hit!')
   enemy['hp']=max(0,enemy['hp']-damage);self.logs.append(f'{self.name(enemy)} lost {damage} HP.');self.audio('hit',1-side,species=enemy['species'],effectiveness=mult,critical=critical,damage=damage)
   if mult>1:self.logs.append("It's super effective!")
   elif mult<1:self.logs.append("It's not very effective.")
   if mid in (71,72,141,202):m['hp']=min(self.c.stats(m)[0],m['hp']+max(1,damage//2));self.audio('recover',side,species=m['species'])
   if mid in (36,38,165):m['hp']=max(0,m['hp']-max(1,damage//4));self.audio('damage',side,species=m['species'],reason='recoil')
   # Sigma Moonblast retains effect 72: lower Special Defense after a hit.
   # The ROM stores a 50% chance, unlike the later game's same-named move.
   if variant and move['effect']==72 and enemy['hp']>0 and self.c.rng.random()<move['chance']/100:
    t=self.tiers(enemy)
    if t[5]>-6:t[5]-=1;self.logs.append(f'{self.name(enemy)}: Special Defense fell.');self.audio('stat_down',1-side,species=enemy['species'],stat='specialDefense')
   secondary={52:('burn',.1),53:('burn',.1),84:('paralysis',.1),85:('paralysis',.1),34:('paralysis',.3),40:('poison',.3)}
   if mid in secondary and enemy['hp']>0 and not enemy['status']:
    st,ch=secondary[mid]
    if self.c.rng.random()<ch:enemy['status']=st;self.logs.append(f'{self.name(enemy)} became {st}.');self.audio('status',1-side,species=enemy['species'],status=st)
  if not self.ended:
   for side in (0,1):
    m=self.mon(side)
    if m['hp']>0 and m['status'] in ('poison','burn','toxic'):
     damage=max(1,self.c.stats(m)[0]//8);m['hp']=max(0,m['hp']-damage);self.logs.append(f'{self.name(m)} is hurt by {m["status"]}.');self.audio('damage',side,species=m['species'],reason=m['status'])
    if m['hp']>0 and m['uid'] in self.seeded:
     amount=min(m['hp'],max(1,self.c.stats(m)[0]//8));m['hp']-=amount;e=self.mon(1-side);e['hp']=min(self.c.stats(e)[0],e['hp']+amount);self.logs.append(f'Leech Seed drained {self.name(m)}.');self.audio('damage',side,species=m['species'],reason='seed');self.audio('recover',1-side,species=e['species'])
   # One event per defeated opposing Pokemon, including multi-Pokemon trainers.
   # World awards and saves the EXP; combat never mutates account progression.
   enemy=self.mon(1)
   if self.kind!='duel' and enemy['hp']<=0 and enemy['uid'] not in self.experience_awarded:
    self.experience_awarded.add(enemy['uid']);self.experience_events.append({'species':enemy['species'],'level':enemy['level'],'participants':sorted(self.participants.get(enemy['uid'],()))})
   for side in (0,1):
    if self.mon(side)['hp']<=0:
     self.logs.append(f'{self.name(self.mon(side))} fainted!');self.audio('faint',side,species=self.mon(side)['species']);alive=next((i for i,m in enumerate(self.rosters[side]) if m['hp']>0),None)
     if alive is None:self.ended=True;self.winner=1-side
     else:self.active[side]=alive;self.logs.append(f'{self.names[side]} sent out {self.name(self.mon(side))}!');self.sendout_audio(side)
  if all(not any(m['hp']>0 for m in roster) for roster in self.rosters):self.ended=True;self.winner=None if self.kind=='duel' else 1
  self._record_participant();self.choice={};self.turn+=1;self.deadline=time.monotonic()+self.turn_seconds
 def _status(self,side,mid):
  m=self.mon(side);enemy=self.mon(1-side)
  move=self.c.moves[str(mid)]
  if sigma_variant(move) and move['effect']==32:
   old=m['hp'];m['hp']=min(self.c.stats(m)[0],old+max(1,self.c.stats(m)[0]//2))
   if old==m['hp']:self.logs.append('But it failed!');self.audio('no_effect',side)
   else:self.logs.append(f'{self.name(m)} recovered {m["hp"]-old} HP.');self.audio('recover',side,species=m['species'],amount=m['hp']-old)
   return
  changes={14:(True,1,2),28:(False,0,-1),39:(False,2,-1),43:(False,2,-1),45:(False,1,-1),74:(True,4,1),81:(False,3,-1),97:(True,3,2),106:(True,2,1),108:(False,0,-1),110:(True,2,1),111:(True,2,1)}
  if mid in changes:
   own,index,delta=changes[mid];target=m if own else enemy;t=self.tiers(target);old=t[index];t[index]=max(-6,min(6,old+delta));self.logs.append(f'{self.name(target)}: {"stat rose" if delta>0 else "stat fell"}.' if old!=t[index] else 'The stat cannot change further.');self.audio(('stat_up' if delta>0 else 'stat_down') if old!=t[index] else 'no_effect',side if own else 1-side,species=target['species']);return
  statuses={77:'poison',78:'paralysis',79:'sleep',86:'paralysis',92:'toxic'}
  if mid in statuses:
   st=statuses[mid];types=self.c.species[enemy['species']]['types']
   if enemy['status'] or st in ('poison','toxic') and any(t in types for t in (3,8)) or mid==86 and 4 in types:self.logs.append('It had no effect.');self.audio('no_effect',1-side);return
   enemy['status']=st;enemy['sleep']=self.c.rng.randint(2,4) if st=='sleep' else 0;self.logs.append(f'{self.name(enemy)} became {st}.');self.audio('status',1-side,species=enemy['species'],status=st);return
  if mid==73:
   if 12 in self.c.species[enemy['species']]['types']:self.logs.append('It had no effect.');self.audio('no_effect',1-side)
   else:self.seeded.add(enemy['uid']);self.logs.append(f'{self.name(enemy)} was seeded.');self.audio('status',1-side,species=enemy['species'],status='seed')
  elif mid in (105,135,208,235,236):m['hp']=min(self.c.stats(m)[0],m['hp']+self.c.stats(m)[0]//2);self.logs.append(f'{self.name(m)} recovered HP.');self.audio('recover',side,species=m['species'])
  elif mid==156:m['hp']=self.c.stats(m)[0];m['status']='sleep';m['sleep']=3;self.logs.append(f'{self.name(m)} fell asleep and recovered HP.');self.audio('recover',side,species=m['species']);self.audio('status',side,species=m['species'],status='sleep')
  elif mid==182:self.protected.add(m['uid']);self.logs.append(f'{self.name(m)} protected itself.');self.audio('protected',side,species=m['species'])
  elif mid in (46,100):
   if self.kind=='wild':self.ended=True;self.winner=None;self.logs.append('The wild encounter ended.');self.audio('escape',side)
   else:self.logs.append('But it failed in this trainer battle.');self.audio('no_effect',side)
  elif mid==116:self.logs.append('Focus Energy is cosmetic in this alpha.')
  else:self.logs.append('But nothing happened!');self.audio('no_effect',side)
