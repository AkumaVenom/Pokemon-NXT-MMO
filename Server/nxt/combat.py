"""Authoritative Gen-III-style single battle engine for Pokemon NXT.

The runtime consumes move-effect, flag, category and species battle metadata
statically extracted from the reviewed FireRed Rev-1 and Sigma 1.5.0 ROMs.
Clients never supply damage, accuracy, HP, RNG, status, rewards or mechanics.

NXT is a single-battle MMO, so effects whose original purpose is exclusively a
double-battle ally/target rule (Follow Me, Helping Hand, Plus/Minus redirection)
fail cleanly in singles rather than inventing a different effect.
"""
from __future__ import annotations
import copy, hashlib, math, time, uuid
from .security import RequestError, require, integer
from .varieties import variety_key

# Type ids follow the active ROM tables. Slot 9 remains Mystery/???; Fairy 18
# is an NXT extension used by explicitly authored later content.
CHART={0:([],[5,8],[7]),1:([0,5,8,15,17],[2,3,6,14,18],[7]),2:([1,6,12],[5,8,13],[]),3:([12,18],[3,4,5,7],[8]),4:([3,5,8,10,13],[6,12],[2]),5:([2,6,10,15],[1,4,8],[]),6:([12,14,17],[1,2,3,7,8,10,18],[]),7:([7,14],[8,17],[0]),8:([5,15,18],[8,10,11,13],[]),9:([],[],[]),10:([6,8,12,15],[5,10,11,16],[]),11:([4,5,10],[11,12,16],[]),12:([4,5,11],[2,3,6,8,10,12,16],[]),13:([2,11],[12,13,16],[4]),14:([1,3],[8,14],[17]),15:([2,4,12,16],[8,10,11,15],[]),16:([16],[8],[18]),17:([7,14],[1,8,17,18],[]),18:([1,16,17],[3,8,10],[])}

# Battle move flags in the GBA move table.
FLAG_CONTACT=0x01; FLAG_PROTECT=0x02; FLAG_MAGIC_COAT=0x04; FLAG_SNATCH=0x08; FLAG_MIRROR=0x10; FLAG_KINGS_ROCK=0x20
SIGMA_MOVE_IDS={183,210,237,294,295,297,346}

# Gen-III held item source ids used by battle mechanics.
BERRY_JUICE=44; CHERI=133; CHESTO=134; PECHA=135; RAWST=136; ASPEAR=137; LEPPA=138; ORAN=139; PERSIM=140; LUM=141; SITRUS=142
PINCH_BERRIES=set(range(143,148)); LIECHI=168; GANLON=169; SALAC=170; PETAYA=171; APICOT=172; LANSAT=173; STARF=174; ENIGMA=175
BRIGHTPOWDER=179; WHITE_HERB=180; QUICK_CLAW=183; MENTAL_HERB=185; CHOICE_BAND=186; KINGS_ROCK=187; SOUL_DEW=191; DEEPSEA_TOOTH=192; DEEPSEA_SCALE=193; FOCUS_BAND=196; SCOPE_LENS=198; LEFTOVERS=200; LIGHT_BALL=202; SHELL_BELL=219; LUCKY_PUNCH=222; METAL_POWDER=223; THICK_CLUB=224; STICK=225

# Stats: 0 accuracy, 1 attack, 2 defense, 3 speed, 4 special attack,
# 5 special defense, 6 evasion. Content.stats uses HP,Atk,Def,Spe,SpA,SpD.
STAT_NAMES={0:'accuracy',1:'attack',2:'defense',3:'speed',4:'specialAttack',5:'specialDefense',6:'evasion'}
UP1={10:1,11:2,12:3,13:4,14:5,15:0,16:6}; DOWN1={18:1,19:2,20:3,21:4,22:5,23:0,24:6}
UP2={50:1,51:2,52:3,53:4,54:5,55:0,56:6}; DOWN2={58:1,59:2,60:3,61:4,62:5,63:0,64:6}
HIT_DOWN={68:1,69:2,70:3,71:4,72:5,73:0,74:6}
HIGH_CRIT_EFFECTS={39,43,75,200,209}
MAJOR_STATUS={'sleep','poison','burn','freeze','paralysis','toxic'}
SOUND_MOVES={45,46,47,48,103,173,195,215,253,304,319,320,336}
FOE_SOUND_MOVES={45,46,47,48,103,173,253,304,319,320}
# FireRed's shared copy-forbidden table has an early Mimic sentinel and a
# later Metronome/Assist sentinel. Keep the three call families distinct.
MIMIC_BANNED={102,118,165,166}
METRONOME_BANNED=MIMIC_BANNED|{68,168,182,194,197,203,214,243,264,266,270,271,289,343}
ASSIST_BANNED=METRONOME_BANNED|{119,274}

# Effects whose primary target is the opposing battler in a singles battle.
# This is intentionally effect-driven rather than target-byte-driven: ROM hacks
# can reuse a native effect with an unusual target byte (Sigma's Roost is a
# reviewed example: EFFECT_RESTORE_HP still heals BS_ATTACKER).
FOE_STATUS_EFFECTS=set(DOWN1)|set(DOWN2)|{1,28,33,49,66,67,82,84,86,90,91,94,100,106,107,113,118,120,143,165,166,167,168,175,177,178,187,191,199,205}


def sigma_variant(move):
 source_id=move.get('sourceMoveId')
 return move.get('source')=='johto' and source_id in SIGMA_MOVE_IDS and move.get('id')==1024+source_id

def matchup(kind,defenders):
 sup,res,immune=CHART.get(kind,([],[],[]));v=1.0
 for d in set(defenders):v*=0 if d in immune else 2 if d in sup else .5 if d in res else 1
 return v

def stage(n):
 n=max(-6,min(6,int(n)));return (2+n)/2 if n>=0 else 2/(2-n)
def accuracy_stage(n):
 # FireRed stores deliberately rounded stage ratios rather than exact thirds.
 n=max(-6,min(6,int(n)));num,den=((33,100),(36,100),(43,100),(50,100),(60,100),(75,100),(1,1),(133,100),(166,100),(2,1),(233,100),(133,50),(3,1))[n+6];return num/den

def _stable_u32(mon):
 if type(mon.get('personality')) is int:return mon['personality']&0xffffffff
 h=hashlib.sha256(str(mon.get('uid','')).encode()).digest();return int.from_bytes(h[:4],'little')

class Battle:
 def __init__(self,content,kind,players,names,rosters,items,turn_seconds=45,audio_source='kanto',terrain='plain'):
  self.c=content;self.id=str(uuid.uuid4());self.kind=kind;self.players=players;self.names=names;self.rosters=copy.deepcopy(rosters);self.items=copy.deepcopy(items)
  self.active=[next((i for i,m in enumerate(r) if m['hp']>0),0) for r in self.rosters];self.stages={};self.volatile={};self.side=[self._new_side(),self._new_side()]
  self.choice={};self.turn=1;self.turn_seconds=turn_seconds;self.deadline=time.monotonic()+turn_seconds;self.ended=False;self.winner=None;self.caught=None;self.rewarded=False
  self.logs=[f'{names[1]} appeared!' if kind=='wild' else f'{names[0]} vs {names[1]}.'];self.seeded=set();self.protected=set();self.experience_events=[];self.experience_awarded=set();self.participants={}
  self.weather='';self.weather_turns=0;self.field={'mudSport':False,'waterSport':False};self.future=[];self.wishes=[];self.payday=0;self.run_attempts=0;self.terrain=terrain
  self.audio_source=audio_source if audio_source in ('kanto','johto') else 'kanto';self.audio_revision=0;self.audio_events=[]
  self.damage_this_turn={};self.damaged_this_turn=set();self.acted_this_turn=set();self.last_move=[None,None];self.last_successful_move=[None,None];self.last_move_target=[None,None]
  self.audio('battle_start',kind=kind)
  for side in (1,0):self.sendout_audio(side,initial=True)
  self._record_participant()

 def _new_side(self):return {'reflect':0,'lightScreen':0,'safeguard':0,'mist':0,'spikes':0}
 def vol(self,m):return self.volatile.setdefault(m['uid'],{})
 def _moves(self,m):return self.vol(m).get('movesOverride',m.get('moves',[]))
 def _public_mon(self,m,private=True):
  q=copy.deepcopy(m);v=self.vol(m)
  if 'movesOverride' in v:q['moves']=copy.deepcopy(v['movesOverride'])
  if v.get('speciesOverride') in self.c.species:q['species']=v['speciesOverride']
  return self.c.public_mon(q,private)
 def name(self,m):return self.c.varieties.display_name(m)
 def mon(self,side):return self.rosters[side][self.active[side]]
 def tiers(self,m):return self.stages.setdefault(m['uid'],[0]*7)
 def types(self,m):
  v=self.vol(m)
  if 'types' in v:return list(v['types'])
  if self.ability(m)==59 and self.c.species[m['species']]['name']=='Castform':
   return [{'sun':[10],'rain':[11],'hail':[15]}.get(self.weather_active(),[0])][0]
  return list(self.c.species[m['species']]['types'])
 def ability(self,m):
  if 'ability' in self.vol(m):return self.vol(m)['ability']
  abilities=self.c.species[m['species']].get('abilities',[0,0]);a0=abilities[0] if abilities else 0;a1=abilities[1] if len(abilities)>1 else 0
  return a1 if a1 and (_stable_u32(m)&1) else a0
 def gender(self,m):
  ratio=int(self.c.species[m['species']].get('genderRatio',255));p=_stable_u32(m)&0xff
  if ratio==255:return 'genderless'
  if ratio==254:return 'female'
  if ratio==0:return 'male'
  return 'female' if p<ratio else 'male'
 def friendship(self,m):return max(0,min(255,int(m.get('friendship',self.c.species[m['species']].get('baseFriendship',70)))))
 def maxhp(self,m):return self.c.stats(m)[0]
 def weather_active(self):
  if any(self.ability(self.mon(s)) in (13,76) for s in (0,1) if self.mon(s)['hp']>0):return ''
  return self.weather
 def _record_participant(self):
  if self.kind!='duel' and self.mon(0)['hp']>0 and self.mon(1)['hp']>0:self.participants.setdefault(self.mon(1)['uid'],set()).add(self.mon(0)['uid'])

 def audio(self,cue,side=None,**data):
  event={'id':f'{self.id}:{self.audio_revision}:{len(self.audio_events)}','cue':cue,'source':self.audio_source,**data}
  if side is not None:
   event['side']=side;mon=self.mon(1-side if cue.startswith('capture_') else side)
   if event.get('species')==mon['species']:event.update(uid=mon['uid'],variety=variety_key(mon),shiny=variety_key(mon)=='shiny')
  self.audio_events.append(event)
 def reset_audio(self):self.audio_revision+=1;self.audio_events=[]
 def audio_view(self,side):
  out=[]
  for original in self.audio_events:
   event=dict(original)
   if 'side' in event:event['side']='you' if event['side']==side else 'opponent'
   if event['cue']=='battle_end':event['result']=self.result(side)
   out.append(event)
  return {'revision':self.audio_revision,'events':out}
 def result(self,side):return None if not self.ended else 'caught' if self.caught else 'won' if self.winner==side else 'lost' if self.winner is not None else 'escaped'

 def sendout_audio(self,side,initial=False,baton=None):
  mon=self.mon(side)
  if baton is None:
   self.stages.pop(mon['uid'],None);self.volatile.pop(mon['uid'],None);self.seeded.discard(mon['uid'])
   self.vol(mon)['enteredTurn']=self.turn if initial else self.turn+1
  else:
   self.stages[mon['uid']]=baton.get('stages',[0]*7)[:];self.volatile[mon['uid']]=copy.deepcopy(baton.get('volatile',{}));self.vol(mon)['enteredTurn']=self.turn if initial else self.turn+1
  self._record_participant();self.audio('sendout',side,species=mon['species'])
  if variety_key(mon)=='shiny':self.audio('shiny',side,species=mon['species'])
  if not initial:self._spikes_damage(side)
  self._entry_ability(side)
  self._consume_item_if_needed(side)

 def _entry_ability(self,side):
  m=self.mon(side);a=self.ability(m);enemy=self.mon(1-side)
  if a==2:self.weather='rain';self.weather_turns=0;self.logs.append('It started to rain!')
  elif a==22 and enemy['hp']>0:self._change_stage(1-side,1,-1,source_side=side,ability=True)
  elif a==45:self.weather='sand';self.weather_turns=0;self.logs.append('A sandstorm kicked up!')
  elif a==70:self.weather='sun';self.weather_turns=0;self.logs.append('The sunlight turned harsh!')
  elif a==36 and enemy['hp']>0:
   other=self.ability(enemy)
   if other:self.vol(m)['ability']=other;self.logs.append(f'{self.name(m)} traced its foe’s Ability!')

 def _spikes_damage(self,side):
  layers=self.side[side]['spikes'];m=self.mon(side)
  if not layers or 2 in self.types(m) or self.ability(m)==26:return
  den={1:8,2:6,3:4}[min(3,layers)];d=max(1,self.maxhp(m)//den);self._direct_hp_loss(side,d,'spikes')

 def usable(self,mon):
  v=self.vol(mon);slots=[];forced=v.get('forcedMove')
  for i,entry in enumerate(self._moves(mon)):
   mid=entry['id'];move=self.c.moves.get(str(mid))
   if forced and mid==forced and v.get('multiTurnPP')==mid:
    if move:slots.append(i)
    continue
   if entry.get('pp',0)<=0:continue
   if not move:continue
   if forced and mid!=forced:continue
   if v.get('disabledMove')==mid and v.get('disableTurns',0)>0:continue
   if v.get('encoreMove') and v.get('encoreTurns',0)>0 and mid!=v['encoreMove']:continue
   if v.get('torment') and v.get('lastMove')==mid:continue
   if v.get('tauntTurns',0)>0 and move.get('power',0)==0:continue
   choice=v.get('choiceMove')
   if mon.get('heldItemId')==CHOICE_BAND and choice and mid!=choice:continue
   foe=self.mon(1-self._side_of(mon)) if self._side_of(mon) is not None else None
   if foe and self.vol(foe).get('imprison') and any(q['id']==mid for q in self._moves(foe)):continue
   slots.append(i)
  return slots
 def _side_of(self,mon):
  for side in (0,1):
   if any(q['uid']==mon['uid'] for q in self.rosters[side]):return side
  return None

 def choose(self,side,data):
  require(not self.ended,'This battle has ended.');require(side not in self.choice,'Your action is already queued.');kind=data.get('action');m=self.mon(side);v=self.vol(m)
  if kind=='attack':
   slot=integer(data.get('slot'),-1,3,'Move slot');usable=self.usable(m);require((slot in usable) or (slot==-1 and not usable),'That move is unavailable or has no PP.')
   action={'action':'attack','slot':slot}
   if data.get('uid') is not None:action['uid']=data.get('uid')
  elif kind=='switch':
   require(not self._trapped(side),'This Pokemon cannot switch out right now.');uid=data.get('uid');idx=next((i for i,q in enumerate(self.rosters[side]) if q['uid']==uid),-1)
   require(idx>=0 and idx!=self.active[side] and self.rosters[side][idx]['hp']>0,'Select a healthy party member other than your active Pokemon.');action={'action':'switch','index':idx}
  elif kind in ('capture','item'):
   require(self.kind!='duel','Items are disabled in friendly duels.');item=data.get('item');require(item in self.c.items and self.items[side].get(item,0)>0,'You do not have that item.')
   if kind=='capture':require(self.kind=='wild' and 'capture' in self.c.items[item],'You can only capture wild Pokemon with a Poke Ball.')
   else:require('heal' in self.c.items[item] and m['hp']<self.maxhp(m),'That healing item cannot be used now.')
   action={'action':kind,'item':item}
  elif kind=='run':
   require(self.kind!='trainer','You cannot run from a trainer battle.');require(not self._trapped(side) or self.ability(m)==50,'This Pokemon cannot escape right now.');action={'action':'run'}
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
  return {'id':self.id,'kind':self.kind,'source':self.audio_source,'turn':self.turn,'you':self._public_mon(self.mon(side)),'opponent':self._public_mon(self.mon(1-side),False),'opponentName':self.names[1-side],'party':[self._public_mon(m) for m in self.rosters[side]],'opponentRemaining':sum(m['hp']>0 for m in self.rosters[1-side]),'waiting':side in self.choice,'canRun':self.kind!='trainer' and not self._trapped(side),'seconds':max(0,int(self.deadline-time.monotonic())),'usable':self.usable(self.mon(side)),'log':self.logs[-22:],'ended':self.ended,'result':self.result(side),'weather':self.weather_active(),'audio':self.audio_view(side)}

 def _priority(self,s):
  a=self.choice[s];m=self.mon(s);priority={'forfeit':11,'run':10,'switch':6,'capture':5,'item':5}.get(a['action'],0)
  if a['action']=='attack':
   move=self._selected_move(s,a);priority=move.get('priority',0)
   # Pursuit strikes a switching target before the switch.
   if move.get('effect')==128 and self.choice.get(1-s,{}).get('action')=='switch':priority=7
  # Quick Claw is a same-priority ordering effect in Gen III.
  quick=1 if m.get('heldItemId')==QUICK_CLAW and self.c.rng.random()<.2 else 0
  speed=self._stat(s,3)
  return priority,quick,speed,self.c.rng.random()

 def _selected_move(self,side,a):
  m=self.mon(side);slot=a.get('slot',-1)
  if slot<0:return self.c.moves['165']
  return self.c.moves[str(self._moves(m)[slot]['id'])]

 def resolve(self):
  require(len(self.choice)==2,'Waiting for both trainers.');self.protected=set();self.logs=[];self.experience_events=[];self._record_participant();self.reset_audio();self.damage_this_turn={};self.damaged_this_turn=set();self.acted_this_turn=set()
  order=sorted((0,1),key=self._priority,reverse=True)
  for side in order:
   if self.ended:break
   m=self.mon(side);enemy=self.mon(1-side);a=self.choice[side]
   if m['hp']<=0:continue
   k=a['action']
   if k in ('run','forfeit'):
    if k=='forfeit' or self.kind=='duel':
     self.ended=True;self.winner=1-side;self.logs.append(f'{self.names[side]} '+('forfeited after the turn timer expired.' if k=='forfeit' else 'withdrew from battle.'));self.audio('escape',side);break
    if self._try_run(side):break
    continue
   if k=='switch':self._switch(side,a['index']);self.acted_this_turn.add(m['uid']);continue
   if k=='item':
    item=a['item'];self.items[side][item]-=1;old=m['hp'];m['hp']=min(self.maxhp(m),m['hp']+self.c.items[item]['heal']);self.logs.append(f'{self.name(m)} recovered {m["hp"]-old} HP.');self.audio('recover',side,species=m['species'],item=item,amount=m['hp']-old);continue
   if k=='capture':
    self._capture(side,a['item']);continue
   # If the target fainted earlier this turn, a normal attack has no target.
   if enemy['hp']<=0:continue
   self._attack_action(side,a);self.acted_this_turn.add(m['uid'])
  if not self.ended:self._end_turn()
  self._collect_experience();self._resolve_faints()
  if all(not any(m['hp']>0 for m in roster) for roster in self.rosters):self.ended=True;self.winner=None if self.kind=='duel' else 1
  if self.ended:self.audio('battle_end')
  self._record_participant();self.choice={};self.turn+=1;self.deadline=time.monotonic()+self.turn_seconds

 def _try_run(self,side):
  m=self.mon(side);enemy=self.mon(1-side);self.run_attempts+=1
  if self.ability(m)==50 or self._stat(side,3)>self._stat(1-side,3):success=True
  else:
   odds=min(255,(self._stat(side,3)*128//max(1,self._stat(1-side,3)))+30*self.run_attempts)
   success=self.c.rng.randrange(256)<odds
  if success:
   self.ended=True;self.winner=None;self.logs.append(f'{self.names[side]} got away safely!');self.audio('escape',side);return True
  self.logs.append("Couldn't escape!");return False

 def _capture(self,side,item):
  enemy=self.mon(1-side);self.items[side][item]-=1;hp=self.maxhp(enemy);sp=self.c.species[enemy['species']];bonus=2 if enemy['status'] in ('sleep','freeze') else 1.5 if enemy['status'] else 1
  chance=min(1,((3*hp-2*enemy['hp'])*sp['catchRate']*self.c.items[item]['capture']*bonus)/(3*hp*255));self.audio('capture_throw',side,item=item,species=enemy['species'])
  if self.c.rng.random()<chance:self.caught=copy.deepcopy(enemy);self.caught['originalTrainer']=self.names[side];self.ended=True;self.winner=side;self.logs.append(f'Gotcha! {self.name(enemy)} was caught!');self.audio('capture_success',side,species=enemy['species'])
  else:self.logs.append(f'{self.name(enemy)} broke free!');self.audio('capture_fail',side,species=enemy['species'])

 def _attack_action(self,side,a):
  m=self.mon(side);slot=a.get('slot',-1);mid=165 if slot<0 else self._moves(m)[slot]['id'];move=self.c.moves[str(mid)]
  forced=self.vol(m).get('forcedMove')
  if forced and forced!=mid:
   mid=forced;move=self.c.moves[str(mid)];slot=next((i for i,q in enumerate(self._moves(m)) if q['id']==mid),-1)
  if not self._pre_move(side,move):return
  # These Gen-III chains/one-move windows end when the user successfully
  # proceeds with a different move. Persistent field statuses remain intact.
  if move.get('effect') not in (111,116):self.vol(m)['protectChain']=0
  if move.get('effect')!=81:self.vol(m).pop('rage',None)
  if move.get('effect')!=98:self.vol(m).pop('destinyBond',None)
  if move.get('effect')!=194:self.vol(m).pop('grudge',None)
  if move.get('effect')!=119:self.vol(m).pop('furyCutter',None)
  continuation=self.vol(m).get('multiTurnPP')==mid
  if slot>=0 and not continuation:
   targeted=move.get('target')!=16;cost=2 if targeted and self.ability(self.mon(1-side))==46 else 1;entries=self._moves(m);entries[slot]['pp']=max(0,entries[slot]['pp']-cost)
   if m.get('heldItemId')==CHOICE_BAND and not self.vol(m).get('choiceMove'):self.vol(m)['choiceMove']=mid
  self.logs.append(f'{self.name(m)} used {move["name"]}!');self.audio('move',side,species=m['species'],move=mid,moveType=move['type']);self.last_move[side]=mid;self.last_move_target[side]=self.mon(1-side)['uid'];self.vol(m)['lastMove']=mid
  self._execute_move(side,mid,move,a,depth=0)
  self._consume_item_if_needed(side);self._consume_item_if_needed(1-side)

 def _pre_move(self,side,move):
  m=self.mon(side);v=self.vol(m);effect=move['effect']
  if v.pop('flinch',False):self.logs.append(f'{self.name(m)} flinched!');return False
  if v.pop('recharge',False):self.logs.append(f'{self.name(m)} must recharge!');return False
  if self.ability(m)==54:
   loaf=v.get('truantLoaf',False);v['truantLoaf']=not loaf
   if loaf:self.logs.append(f'{self.name(m)} is loafing around!');return False
  if m['status']=='sleep':
   dec=2 if self.ability(m)==48 else 1;m['sleep']=max(0,m.get('sleep',1)-dec)
   if m['sleep']<=0:m['status']='';self.logs.append(f'{self.name(m)} woke up!');self.audio('status_clear',side,species=m['species'],status='sleep')
   elif effect not in (92,97):self.logs.append(f'{self.name(m)} is asleep.');self.audio('status',side,species=m['species'],status='sleep');return False
  if m['status']=='freeze':
   if effect==125 or self.c.rng.random()<.2:m['status']='';self.logs.append(f'{self.name(m)} thawed out!');self.audio('status_clear',side,species=m['species'],status='freeze')
   else:self.logs.append(f'{self.name(m)} is frozen solid!');return False
  if m['status']=='paralysis' and self.c.rng.random()<.25:self.logs.append(f'{self.name(m)} is fully paralyzed.');self.audio('status',side,species=m['species'],status='paralysis');return False
  if v.get('confusionTurns',0)>0:
   v['confusionTurns']-=1
   if v['confusionTurns']<=0:self.logs.append(f'{self.name(m)} snapped out of confusion!')
   else:
    self.logs.append(f'{self.name(m)} is confused!')
    if self.c.rng.random()<.5:
     atk=self._stat(side,1);defn=self._stat(side,2);raw=((2*m['level']//5+2)*40*atk/max(1,defn)/50)+2;d=max(1,int(raw*self.c.rng.randint(85,100)/100));self._damage(side,side,d,reason='confusion',direct=False);return False
  if v.get('attractSource') and self.mon(1-side)['uid']!=v.get('attractSource'):v.pop('attractSource',None)
  if v.get('attractSource') and self.c.rng.random()<.5:self.logs.append(f'{self.name(m)} is immobilized by love!');return False
  if effect==170 and m['uid'] in self.damaged_this_turn:self.logs.append('But it failed!');self.audio('no_effect',side);return False
  return True

 def _execute_move(self,side,mid,move,a,depth=0):
  if depth>8:self._fail(side);return
  m=self.mon(side);enemy=self.mon(1-side);effect=move['effect'];v=self.vol(m);ev=self.vol(enemy)
  if effect in (96,110,131,141,163):self._fail(side);return
  # Opposing sound moves are stopped by Soundproof before their move effect.
  # Party/global sound scripts (Heal Bell/Perish Song) handle Soundproof per
  # affected Pokemon instead of being rejected wholesale here.
  if mid in FOE_SOUND_MOVES and self.ability(enemy)==43:return self._ability_no_effect(1-side)
  # Snatch steals eligible self-benefit moves; Magic Coat reflects eligible
  # opposing status moves. Both flags come directly from the GBA move table.
  if move.get('flags',0)&FLAG_SNATCH and ev.pop('snatch',False):
   self.logs.append(f'{self.name(enemy)} snatched the move!');self._execute_called(1-side,mid,depth);return
  foe_status=move.get('power',0)==0 and effect in FOE_STATUS_EFFECTS
  if foe_status and move.get('flags',0)&FLAG_MAGIC_COAT and ev.pop('magicCoat',False):
   self.logs.append(f'{self.name(enemy)} reflected the move!');self._execute_called(1-side,mid,depth);return
  if foe_status:
   if not self._accuracy(side,move,effect):self.logs.append('The attack missed!');self.audio('miss',side);return
   if self._protected(1-side,move):return
  # Single-battle-only contextual failures.
  if effect in (172,176):self._fail(side);return
  if effect==1:return self._status_move(side,'sleep',move,checked=True)
  # Called-move families.
  if effect==9: # Mirror Move
   called=self.last_move[1-side];called_move=self.c.moves.get(str(called)) if called else None
   if not called_move or called==mid or not (called_move.get('flags',0)&FLAG_MIRROR):self._fail(side);return
   self._execute_called(side,called,depth);return
  if effect==83: # Metronome
   pool=[int(k) for k,q in self.c.moves.items() if int(k)<1024 and int(k) not in METRONOME_BANNED and q.get('effect') not in (83,95)]
   if not pool:self._fail(side);return
   self._execute_called(side,self.c.rng.choice(pool),depth);return
  if effect==97: # Sleep Talk
   if m['status']!='sleep':self._fail(side);return
   # FireRed rejects called-move families, Focus Punch, Uproar and every
   # charging/semi-invulnerable/Bide family from Sleep Talk's candidate pool.
   sleep_talk_bad_effects={9,26,39,75,83,97,145,151,155,159,170,180}
   pool=[q['id'] for q in self._moves(m) if q['id'] not in (0,mid) and self.c.moves[str(q['id'])]['effect'] not in sleep_talk_bad_effects]
   if not pool:self._fail(side);return
   self._execute_called(side,self.c.rng.choice(pool),depth);return
  if effect==180: # Assist
   pool=[]
   for q in self.rosters[side]:
    if q['uid']==m['uid']:continue
    pool.extend(x['id'] for x in self._moves(q) if x['id'] not in ASSIST_BANNED and x['id']!=0)
   if not pool:self._fail(side);return
   self._execute_called(side,self.c.rng.choice(pool),depth);return
  if effect==173: # Nature Power
   # Exact FRLG terrain table: Stun Spore / Razor Leaf / Earthquake /
   # Hydro Pump / Surf / Bubblebeam / Rock Slide / Shadow Ball / Swift.
   called={'grass':78,'long_grass':75,'sand':89,'underwater':56,'water':57,'pond':61,'mountain':157,'cave':247,'building':129,'plain':129}.get(self.terrain,129)
   self._execute_called(side,called,depth);return
  # Two-turn charging/semi-invulnerable moves.
  if effect in (39,75,145,151,155):
   charge=v.get('charge')
   if charge!=mid:
    if effect==151 and self.weather_active()=='sun':pass
    else:
     v['charge']=mid;v['forcedMove']=mid;v['multiTurnPP']=mid
     if effect==155:v['semi']={19:'fly',91:'dig',291:'dive',340:'fly'}.get(mid,'fly')
     if effect==145:self._change_stage(side,2,1,source_side=side)
     self.logs.append(f'{self.name(m)} is preparing its attack!');return
   v.pop('charge',None);v.pop('semi',None);v.pop('forcedMove',None);v.pop('multiTurnPP',None)
  # Bide: two storing turns then double damage received.
  if effect==26:
   if not v.get('bideTurns'):
    v.update(bideTurns=2,bideDamage=0,forcedMove=mid,multiTurnPP=mid);self.logs.append(f'{self.name(m)} began storing energy!');return
   v['bideTurns']-=1
   if v['bideTurns']>0:self.logs.append(f'{self.name(m)} is storing energy!');return
   damage=v.pop('bideDamage',0);v.pop('forcedMove',None);v.pop('multiTurnPP',None);v.pop('bideTurns',None)
   if damage<=0:self._fail(side);return
   self._deal_fixed(side,1-side,damage*2,move);return
  # Rampage/uproar/rollout force repetition.
  if effect==27 and not v.get('rampageTurns'):
   v['rampageTurns']=self.c.rng.randint(2,3);v['forcedMove']=mid;v['multiTurnPP']=mid
  if effect==159 and not v.get('uproarTurns'):
   v['uproarTurns']=self.c.rng.randint(2,5);v['forcedMove']=mid;v['multiTurnPP']=mid
  if effect==117 and not v.get('rolloutCount'):
   v['rolloutCount']=1;v['forcedMove']=mid;v['multiTurnPP']=mid

  # Primary status/stat/support effects before ordinary damage routing.
  if effect in UP1:return self._change_stage(side,UP1[effect],1,source_side=side)
  if effect in DOWN1:return self._change_stage(1-side,DOWN1[effect],-1,source_side=side,move=move)
  if effect in UP2:return self._change_stage(side,UP2[effect],2,source_side=side)
  if effect in DOWN2:return self._change_stage(1-side,DOWN2[effect],-2,source_side=side,move=move)
  if effect==25:
   for q in self.stages.values():q[:]=[0]*7
   self.logs.append('All stat changes were eliminated!');return
  if effect==28:return self._force_switch(1-side,side,move)
  if effect==30:return self._conversion(side)
  if effect==32:return self._heal(side,max(1,self.maxhp(m)//2))
  if effect==33:return self._status_move(side,'toxic',move,checked=True)
  if effect==35:return self._screen(side,'lightScreen')
  if effect==37:return self._rest(side)
  if effect==38:return self._ohko(side,move)
  if effect==46:return self._side_condition(side,'mist',5)
  if effect==47:
   if v.get('focusEnergy'):return self._fail(side)
   v['focusEnergy']=True;self.logs.append(f'{self.name(m)} is getting pumped!');return
  if effect==49:return self._confuse(1-side,source_side=side,move=move)
  if effect==57:return self._transform(side)
  if effect==65:return self._screen(side,'reflect')
  if effect==66:return self._status_move(side,'poison',move,checked=True)
  if effect==67:return self._status_move(side,'paralysis',move,checked=True)
  if effect==79:return self._substitute(side)
  if effect==82:return self._mimic(side,move)
  if effect==84:return self._leech_seed(side,move)
  if effect==85:self.logs.append('But nothing happened!');return
  if effect==86:return self._disable(side)
  if effect==90:return self._encore(side)
  if effect==91:return self._pain_split(side)
  if effect==93:return self._conversion2(side)
  if effect==94:ev['lockOnSource']=m['uid'];ev['lockOnTurns']=2;self.logs.append(f'{self.name(m)} took aim!');return
  if effect==95:return self._sketch(side)
  if effect==98:v['destinyBond']=True;self.logs.append(f'{self.name(m)} is trying to take its foe down with it!');return
  if effect==100:return self._spite(side)
  if effect==102:return self._heal_bell(side,mid)
  if effect==106:ev['trappedBy']=m['uid'];self.logs.append(f'{self.name(enemy)} can no longer escape!');return
  if effect==107:
   if enemy['status']!='sleep':return self._fail(side)
   ev['nightmare']=True;self.logs.append(f'{self.name(enemy)} began having a nightmare!');return
  if effect==108:v['minimized']=True;return self._change_stage(side,6,1,source_side=side)
  if effect==109:return self._curse(side)
  if effect==111:return self._protect(side)
  if effect==112:
   if self.side[1-side]['spikes']>=3:return self._fail(side)
   self.side[1-side]['spikes']+=1;self.logs.append('Spikes were scattered around the foe’s side!');return
  if effect==113:ev['foresight']=True;self.logs.append(f'{self.name(enemy)} was identified!');return
  if effect==114:
   heard=False
   for q in (0,1):
    if self.ability(self.mon(q))!=43:self.vol(self.mon(q))['perish']=4;heard=True
   if not heard:return self._fail(side)
   self.logs.append('All Pokemon hearing the song will faint in three turns!');return
  if effect==115:return self._weather('sand',side)
  if effect==116:return self._endure(side)
  if effect==118:
   self._change_stage(1-side,1,2,source_side=side,move=move);return self._confuse(1-side,source_side=side,move=move)
  if effect==120:return self._attract(side,move)
  if effect==124:return self._side_condition(side,'safeguard',5)
  if effect==127:return self._baton_pass(side,a)
  if effect==132:return self._weather_heal(side)
  if effect==133:return self._weather_heal(side)
  if effect==134:return self._weather_heal(side)
  if effect==136:return self._weather('rain',side)
  if effect==137:return self._weather('sun',side)
  if effect==142:return self._belly_drum(side)
  if effect==143:
   self.stages[m['uid']]=self.tiers(enemy)[:];self.logs.append(f'{self.name(m)} copied the foe’s stat changes!');return
  if effect==153:
   if self.kind=='wild':self.ended=True;self.winner=None;self.logs.append('The wild encounter ended.');self.audio('escape',side)
   else:self._fail(side)
   return
  if effect==156:v['defenseCurl']=True;return self._change_stage(side,2,1,source_side=side)
  if effect==157:return self._heal(side,max(1,self.maxhp(m)//2))
  if effect==160:
   if v.get('stockpile',0)>=3:return self._fail(side)
   v['stockpile']=v.get('stockpile',0)+1;self.logs.append(f'{self.name(m)} stockpiled {v["stockpile"]}!');return
  if effect==162:return self._swallow(side)
  if effect==164:return self._weather('hail',side)
  if effect==165:ev['torment']=True;self.logs.append(f'{self.name(enemy)} was subjected to torment!');return
  if effect==166:
   self._change_stage(1-side,4,1,source_side=side,move=move);return self._confuse(1-side,source_side=side,move=move)
  if effect==167:return self._status_move(side,'burn',move,checked=True)
  if effect==168:return self._memento(side)
  if effect==174:v['chargeElectric']=2;self.logs.append(f'{self.name(m)} began charging power!');return
  if effect==175:ev['tauntTurns']=2;self.logs.append(f'{self.name(enemy)} fell for the taunt!');return
  if effect==177:return self._trick(side)
  if effect==178:
   target=self.ability(enemy)
   if not target or target==25:return self._fail(side)
   v['ability']=target;self.logs.append(f'{self.name(m)} copied the foe’s Ability!');return
  if effect==179:
   if any(w['side']==side for w in self.wishes):return self._fail(side)
   self.wishes.append({'turns':2,'side':side,'amount':max(1,self.maxhp(m)//2)});self.logs.append(f'{self.name(m)} made a wish!');return
  if effect==181:
   if v.get('ingrain'):return self._fail(side)
   v['ingrain']=True;self.logs.append(f'{self.name(m)} planted its roots!');return
  if effect==183:
   if enemy['uid'] in self.acted_this_turn:return self._fail(side)
   v['magicCoat']=True;self.logs.append(f'{self.name(m)} shrouded itself with Magic Coat!');return
  if effect==184:return self._recycle(side)
  if effect==187:
   if enemy['status'] or ev.get('yawn') or ev.get('substituteHp') or self.ability(enemy) in (15,72) or any(self.vol(self.mon(q)).get('uproarTurns',0)>0 for q in (0,1)):return self._fail(side)
   ev['yawn']=2;self.logs.append(f'{self.name(enemy)} grew drowsy!');return
  if effect==191:return self._skill_swap(side)
  if effect==192:
   if v.get('imprison') or not any(a['id']==b['id'] for a in self._moves(m) for b in self._moves(enemy)):return self._fail(side)
   v['imprison']=True;self.logs.append(f'{self.name(m)} sealed the foe’s shared moves!');return
  if effect==193:return self._refresh(side)
  if effect==194:
   if v.get('grudge'):return self._fail(side)
   v['grudge']=True;self.logs.append(f'{self.name(m)} wants its foe to bear a grudge!');return
  if effect==195:
   if enemy['uid'] in self.acted_this_turn:return self._fail(side)
   v['snatch']=True;self.logs.append(f'{self.name(m)} waits to snatch a move!');return
  if effect==199:
   return self._confuse(1-side,source_side=side,move=move)
  if effect==201:v['mudSport']=True;self.logs.append('Electricity’s power was weakened!');return
  if effect==205:
   self._change_stage(1-side,1,-1,source_side=side,move=move);return self._change_stage(1-side,2,-1,source_side=side,move=move)
  if effect==206:
   self._change_stage(side,2,1,source_side=side);return self._change_stage(side,5,1,source_side=side)
  if effect==208:
   self._change_stage(side,1,1,source_side=side);return self._change_stage(side,2,1,source_side=side)
  if effect==210:v['waterSport']=True;self.logs.append('Fire’s power was weakened!');return
  if effect==211:
   self._change_stage(side,4,1,source_side=side);return self._change_stage(side,5,1,source_side=side)
  if effect==212:
   self._change_stage(side,1,1,source_side=side);return self._change_stage(side,3,1,source_side=side)
  if effect==213:return self._camouflage(side)

  # Remaining effects are damaging or damage-adjacent.
  self._damaging_move(side,mid,move,effect,depth)

 def _execute_called(self,side,mid,depth):
  move=self.c.moves.get(str(mid))
  if not move:return self._fail(side)
  self.logs.append(f'{self.name(self.mon(side))} called {move["name"]}!');self.audio('move',side,species=self.mon(side)['species'],move=mid,moveType=move['type'])
  self._execute_move(side,mid,move,{'action':'attack','slot':-1},depth+1)

 def _damaging_move(self,side,mid,move,effect,depth):
  m=self.mon(side);enemy=self.mon(1-side);v=self.vol(m);ev=self.vol(enemy)
  if effect==158 and v.get('enteredTurn')!=self.turn:return self._fail(side)
  if effect==7:
   if any(self.ability(self.mon(q))==6 for q in (0,1)):return self._fail(side)
   m['hp']=0;self.audio('damage',side,species=m['species'],reason='selfdestruct')
  if effect==186:self.side[1-side]['reflect']=0;self.side[1-side]['lightScreen']=0
  if effect==148:
   if not self._accuracy(side,move,effect):self.logs.append('The attack missed!');self.audio('miss',side);return
   atk=self._stat(side,4);defn=self._stat(1-side,5);raw=((2*m['level']//5+2)*max(1,move['power'])*atk//max(1,defn)//50)+2;damage=max(1,int(raw*self.c.rng.randint(85,100)/100));self.future.append({'turns':3,'targetSide':1-side,'sourceSide':side,'damage':damage,'move':move});self.logs.append('An attack was foreseen!');return
  # Soundproof blocks sound-based moves in Gen III.
  if mid in SOUND_MOVES and self.ability(enemy)==43:return self._ability_no_effect(1-side)
  # Dream Eater / Snore contextual checks.
  if effect==8 and enemy['status']!='sleep':return self._fail(side)
  if effect==92 and m['status']!='sleep':return self._fail(side)
  # Counter / Mirror Coat are fixed reflection effects.
  if effect in (89,144):
   rec=self.damage_this_turn.get(m['uid'])
   want_physical=effect==89
   if not rec or rec['sourceSide']!=1-side or rec['physical']!=want_physical:return self._fail(side)
   return self._deal_fixed(side,1-side,rec['damage']*2,move)
  if effect==87:return self._deal_fixed(side,1-side,m['level'],move)
  if effect==88:
   # FireRed Psywave samples one of eleven 10%-steps from 50% through 150%
   # using a 4-bit rejection loop rather than a continuous level range.
   while True:
    roll=self.c.rng.randrange(16)
    if roll<=10:break
   return self._deal_fixed(side,1-side,max(1,m['level']*(50+roll*10)//100),move)
  if effect==40:return self._deal_fixed(side,1-side,max(1,enemy['hp']//2),move)
  if effect==41:return self._deal_fixed(side,1-side,40,move)
  if effect==130:return self._deal_fixed(side,1-side,20,move)
  if effect==189:
   if enemy['hp']<=m['hp']:return self._fail(side)
   return self._deal_fixed(side,1-side,enemy['hp']-m['hp'],move)
  if effect==38:return self._ohko(side,move)
  # Multi-hit count.
  hits=1
  if effect==29:
   r=self.c.rng.randrange(8);hits=2 if r<3 else 3 if r<6 else 4 if r==6 else 5
  elif effect in (44,77):hits=2
  elif effect==104:hits=3
  elif effect==154:return self._beat_up(side,move)
  # Accuracy is one check for ordinary multi-hit moves; Triple Kick checks each.
  if effect!=104 and not self._accuracy(side,move,effect):
   if effect==45:self._jump_kick_crash(side,move)
   if effect==117:v.pop('rolloutCount',None);v.pop('forcedMove',None);v.pop('multiTurnPP',None)
   if effect==27:self._advance_repeat(v,'rampageTurns',confuse_side=side)
   if effect==159:self._advance_repeat(v,'uproarTurns')
   if effect==119:v.pop('furyCutter',None)
   return
  if self._protected(1-side,move):return
  if self._semi_blocked(side,move):return
  # Move-specific power/type.
  typ,power=self._power_type(side,move,effect)
  if power is None:return
  total=0;landed=0
  for hit in range(hits):
   if enemy['hp']<=0:break
   if effect==104 and not self._accuracy(side,move,effect):break
   hit_power=power*(hit+1) if effect==104 else power
   damage,crit,mult,physical=self._calculate_damage(side,move,hit_power,typ,effect)
   if mult==0:
    if landed==0:self.logs.append('It had no effect.');self.audio('no_effect',1-side)
    break
   if effect==101:damage=min(damage,max(0,enemy['hp']-1))
   if damage<=0:break
   resolved_move=move if typ==move.get('type') else {**move,'type':typ}
   dealt=self._damage(side,1-side,damage,move=resolved_move,physical=physical,critical=crit,effectiveness=mult);total+=dealt;landed+=1
   if dealt<=0:break
  if landed>1:self.logs.append(f'Hit {landed} times!')
  if total<=0:return
  self.last_successful_move[side]=mid
  # Direct move effects after damage.
  if effect in (3,8):self._drain(side,total)
  if effect==34:self.payday+=m['level']*5
  if effect==42:
   ev['wrapTurns']=self.c.rng.randint(2,5);ev['wrappedBy']=m['uid'];ev['trappedBy']=m['uid']
  if effect==48:self._recoil(side,max(1,total//4))
  if effect==198:self._recoil(side,max(1,total//3))
  if effect==80:v['recharge']=True
  if effect==81:v['rage']=True
  if effect==117:
   v['rolloutCount']=v.get('rolloutCount',1)+1
   if v['rolloutCount']>5:v.pop('rolloutCount',None);v.pop('forcedMove',None);v.pop('multiTurnPP',None)
  if effect==119:v['furyCutter']=min(5,v.get('furyCutter',0)+1)
  else:
   if effect!=119:v.pop('furyCutter',None)
  if effect==105 and not m.get('heldItemId') and enemy.get('heldItemId') and self.ability(enemy)!=60:m['heldItemId']=self._remove_item(enemy)
  if effect==129:
   self.side[side]['spikes']=0;v.pop('leechSeedSource',None);v.pop('wrapTurns',None);v.pop('trappedBy',None)
  if effect==169 and m['status'] in ('poison','toxic','burn','paralysis'):pass
  if effect==171 and enemy['status']=='paralysis':enemy['status']='';self.audio('status_clear',1-side,species=enemy['species'],status='paralysis')
  if effect==188:
   if enemy.get('heldItemId') and self.ability(enemy)!=60:self._remove_item(enemy)
  if effect==204:self._change_stage(side,4,-2,source_side=side,self_inflicted=True)
  if effect==182:
   self._change_stage(side,1,-1,source_side=side,self_inflicted=True);self._change_stage(side,2,-1,source_side=side,self_inflicted=True)
  if effect==125 and enemy['hp']>0:self._secondary_status(side,'burn',move)
  if effect==202 and enemy['hp']>0 and self._secondary_roll(side,move):self._apply_status(1-side,'toxic',source_side=side)
  # Secondary families.
  secondary_status={2:'poison',4:'burn',5:'freeze',6:'paralysis'}
  if effect in secondary_status and enemy['hp']>0:self._secondary_status(side,secondary_status[effect],move)
  if effect==36 and enemy['hp']>0 and self._secondary_roll(side,move):self._apply_status(1-side,self.c.rng.choice(['burn','freeze','paralysis']),source_side=side)
  if effect in (31,75,92,146,150) and enemy['hp']>0 and self._secondary_roll(side,move):self._flinch(1-side)
  if effect==158 and enemy['hp']>0:self._flinch(1-side)
  if effect==76 and enemy['hp']>0 and self._secondary_roll(side,move):self._confuse(1-side,source_side=side)
  if effect==77 and enemy['hp']>0 and self._secondary_roll(side,move):self._apply_status(1-side,'poison',source_side=side)
  if effect in HIT_DOWN and enemy['hp']>0 and self._secondary_roll(side,move):self._change_stage(1-side,HIT_DOWN[effect],-1,source_side=side,move=move)
  if effect==138 and self._secondary_roll(side,move):self._change_stage(side,2,1,source_side=side)
  if effect==139 and self._secondary_roll(side,move):self._change_stage(side,1,1,source_side=side)
  if effect==140 and self._secondary_roll(side,move):
   for stat in (1,2,3,4,5):self._change_stage(side,stat,1,source_side=side)
  if effect==152 and enemy['hp']>0:self._secondary_status(side,'paralysis',move)
  if effect==200 and enemy['hp']>0:self._secondary_status(side,'burn',move)
  if effect==209 and enemy['hp']>0:self._secondary_status(side,'poison',move)
  if effect==197 and enemy['hp']>0:self._secret_power_secondary(side,move)
  if effect==203:pass
  # Repeating-move teardown.
  if effect==27:self._advance_repeat(v,'rampageTurns',confuse_side=side)
  if effect==159:self._advance_repeat(v,'uproarTurns')
  # Hyper Beam/recharge; Shell Bell and contact abilities/items.
  if effect==80:v['recharge']=True
  if m.get('heldItemId')==SHELL_BELL and m['hp']>0:self._heal(side,max(1,total//8),quiet=True)
  self._contact_effects(side,move)

 def _power_type(self,side,move,effect):
  m=self.mon(side);enemy=self.mon(1-side);v=self.vol(m);typ=move['type'];power=max(1,move.get('power',1))
  if effect==99:
   ratio=48*m['hp']//max(1,self.maxhp(m));power=200 if ratio<=1 else 150 if ratio<=4 else 100 if ratio<=9 else 80 if ratio<=16 else 40 if ratio<=32 else 20
  elif effect==117:
   power=move['power']*(2**max(0,v.get('rolloutCount',1)-1))*(2 if v.get('defenseCurl') else 1)
  elif effect==119:power=min(160,move['power']*(2**v.get('furyCutter',0)))
  elif effect==121:power=max(1,self.friendship(m)*10//25)
  elif effect==122:
   # FireRed Present uses byte thresholds 102/178/204, not round 40/30/10/20
   # percentages. The final branch heals the target by one quarter.
   r=self.c.rng.randrange(256)
   if r>=204:
    if enemy['hp']>=self.maxhp(enemy):self._fail(side)
    else:self._heal(1-side,max(1,self.maxhp(enemy)//4))
    return typ,None
   power=40 if r<102 else 80 if r<178 else 120
  elif effect==123:power=max(1,(255-self.friendship(m))*10//25)
  elif effect==126:
   r=self.c.rng.randrange(100);mag=4 if r<5 else 5 if r<15 else 6 if r<35 else 7 if r<65 else 8 if r<85 else 9 if r<95 else 10;power={4:10,5:30,6:50,7:70,8:90,9:110,10:150}[mag];self.logs.append(f'Magnitude {mag}!')
  elif effect==135:
   bits=sum(((m['ivs'][i]&1)<<i) for i in range(6));second=sum((((m['ivs'][i]>>1)&1)<<i) for i in range(6));raw=(bits*15)//63+1;typ=raw+1 if raw>=9 else raw;power=(second*40)//63+30
  elif effect==161:
   stock=v.get('stockpile',0)
   if not stock:self._fail(side);return typ,None
   power=100*stock;v['stockpile']=0
  elif effect==169 and m['status'] in ('poison','toxic','burn','paralysis'):power*=2
  elif effect==171 and enemy['status']=='paralysis':power*=2
  elif effect==185 and m['uid'] in self.damaged_this_turn:power*=2
  elif effect==190:power=max(1,150*m['hp']//max(1,self.maxhp(m)))
  elif effect==196:
   w=int(self.c.species[enemy['species']].get('weightHectograms',1000));power=20 if w<100 else 40 if w<250 else 60 if w<500 else 80 if w<1000 else 100 if w<2000 else 120
  elif effect==203:
   weather=self.weather_active()
   if weather:power*=2;typ={'sun':10,'rain':11,'sand':5,'hail':15}[weather]
  if effect==151 and self.weather_active() in ('rain','sand','hail'):power=max(1,power//2)
  if effect in (146,149) and self.vol(enemy).get('semi')=='fly':power*=2
  if effect in (147,126) and self.vol(enemy).get('semi')=='dig':power*=2
  if move['name']=='Surf' and self.vol(enemy).get('semi')=='dive':power*=2
  if move['name']=='Whirlpool' and self.vol(enemy).get('semi')=='dive':power*=2
  if effect==150 and self.vol(enemy).get('minimized'):power*=2
  if effect==128 and self.choice.get(1-side,{}).get('action')=='switch':power*=2
  return typ,power

 def _calculate_damage(self,side,move,power,typ,effect):
  m=self.mon(side);enemy=self.mon(1-side);physical=move.get('category',0)==0
  critical=self._critical(side,move,effect)
  ai,di=(1,2) if physical else (4,5);atk=self._stat(side,ai,crit_attacker=critical);defn=self._stat(1-side,di,crit_defender=critical)
  if effect==7:defn=max(1,defn//2)
  # Field/move/ability power modifiers.
  weather=self.weather_active()
  if weather=='sun':power=power*3//2 if typ==10 else power//2 if typ==11 else power
  elif weather=='rain':power=power*3//2 if typ==11 else power//2 if typ==10 else power
  if any(self.vol(self.mon(s)).get('mudSport') for s in (0,1)) and typ==13:power=max(1,power//2)
  if any(self.vol(self.mon(s)).get('waterSport') for s in (0,1)) and typ==10:power=max(1,power//2)
  if self.ability(m)==18 and self.vol(m).get('flashFire') and typ==10:power=power*3//2
  if self.ability(enemy)==47 and typ in (10,15):power=max(1,power//2)
  if self.ability(m) in (65,66,67,68) and m['hp']*3<=self.maxhp(m):
   boost_type={65:12,66:10,67:11,68:6}[self.ability(m)]
   if typ==boost_type:power=power*3//2
  if self.vol(m).get('chargeElectric',0)>0 and typ==13:power*=2
  mult=self._type_multiplier(side,1-side,typ,move)
  if self.ability(enemy)==25 and mult<=1 and move['power']>0:mult=0
  raw=((2*m['level']//5+2)*max(1,power)*max(1,atk)//max(1,defn)//50)+2
  if not critical:
   if physical and self.side[1-side]['reflect']>0:raw=max(1,raw//2)
   if not physical and self.side[1-side]['lightScreen']>0:raw=max(1,raw//2)
  stab=1.5 if typ in self.types(m) else 1
  damage=max(1,int(raw*stab*mult*(2 if critical else 1)*self.c.rng.randint(85,100)/100)) if mult else 0
  return damage,critical,mult,physical

 def _type_multiplier(self,attacker_side,target_side,typ,move):
  target=self.mon(target_side);types=self.types(target);v=matchup(typ,types)
  if self.vol(target).get('foresight') and typ in (0,1) and 7 in types:
   # Recompute without Ghost's immunity to Normal/Fighting.
   effective=[t for t in types if t!=7];v=matchup(typ,effective or [0])
  a=self.ability(target)
  if typ==4 and a==26:return 0
  if typ==13 and a==10:
   self._heal(target_side,max(1,self.maxhp(target)//4),quiet=True);return 0
  if typ==11 and a==11:
   self._heal(target_side,max(1,self.maxhp(target)//4),quiet=True);return 0
  if typ==10 and a==18:self.vol(target)['flashFire']=True;return 0
  return v

 def _critical(self,side,move,effect):
  m=self.mon(side);enemy=self.mon(1-side)
  if self.ability(enemy) in (4,75):return False
  level=0
  if effect in HIGH_CRIT_EFFECTS:level+=1
  if self.vol(m).get('focusEnergy'):level+=2
  item=m.get('heldItemId',0)
  if item==SCOPE_LENS:level+=1
  if item==LUCKY_PUNCH and self.c.species[m['species']]['name']=='Chansey':level+=2
  if item==STICK and "Farfetch" in self.c.species[m['species']]['name']:level+=2
  if item==LANSAT:level+=2
  den=[16,8,4,3,2][min(4,level)];return self.c.rng.randrange(den)==0

 def _accuracy(self,side,move,effect):
  m=self.mon(side);enemy=self.mon(1-side);ev=self.vol(enemy)
  if ev.get('lockOnSource')==m['uid'] and ev.get('lockOnTurns',0)>0:return True
  if effect in (17,78):return True
  if effect==152:
   w=self.weather_active()
   if w=='rain':return True
   accuracy=50 if w=='sun' else move.get('accuracy',100)
  else:accuracy=move.get('accuracy',100)
  if not accuracy:return True
  # Foresight identifies the foe and ignores its evasion stage.
  target_evasion=0 if ev.get('foresight') else self.tiers(enemy)[6]
  diff=self.tiers(m)[0]-target_evasion;accuracy*=accuracy_stage(diff)
  if self.ability(m)==14:accuracy*=1.3
  if self.ability(m)==55 and move.get('category',0)==0:accuracy*=.8
  if self.ability(enemy)==8 and self.weather_active()=='sand':accuracy*=.8
  if enemy.get('heldItemId')==BRIGHTPOWDER:accuracy*=.9
  return self.c.rng.randrange(100)<max(1,min(100,int(accuracy)))

 def _semi_blocked(self,side,move):
  enemy=self.mon(1-side);ev=self.vol(enemy);semi=ev.get('semi')
  if not semi:return False
  if ev.get('lockOnSource')==self.mon(side)['uid'] and ev.get('lockOnTurns',0)>0:return False
  name=move['name'];allowed=(semi=='fly' and name in ('Thunder','Gust','Twister','Sky Uppercut')) or (semi=='dig' and name in ('Earthquake','Magnitude')) or (semi=='dive' and name in ('Surf','Whirlpool'))
  if allowed:return False
  self.logs.append('The attack missed!');self.audio('miss',side);return True

 def _protected(self,target_side,move):
  target=self.mon(target_side)
  if target['uid'] in self.protected and move.get('flags',0)&FLAG_PROTECT:
   self.logs.append(f'{self.name(target)} protected itself.');self.audio('protected',target_side,species=target['species']);return True
  return False

 def _stat(self,side,index,crit_attacker=False,crit_defender=False):
  m=self.mon(side);override=self.vol(m).get('statsOverride');base=override[index] if override and index>0 else self.c.stats(m)[index];tier_index={1:1,2:2,3:3,4:4,5:5}[index];n=self.tiers(m)[tier_index]
  if crit_attacker and n<0:n=0
  if crit_defender and n>0:n=0
  val=base*stage(n);a=self.ability(m);item=m.get('heldItemId',0);name=self.c.species[m['species']]['name']
  if index==1:
   if m['status']=='burn' and a!=62:val*=.5
   if a in (37,74):val*=2
   if a==55:val*=1.5
   if a==62 and m['status']:val*=1.5
   if item==CHOICE_BAND:val*=1.5
   if item==THICK_CLUB and name in ('Cubone','Marowak'):val*=2
  elif index==2:
   if a==63 and m['status']:val*=1.5
   if item==METAL_POWDER and name=='Ditto' and not self.vol(m).get('transformed'):val*=2
  elif index==3:
   if m['status']=='paralysis':val*=.25
   if a==33 and self.weather_active()=='rain':val*=2
   if a==34 and self.weather_active()=='sun':val*=2
  elif index==4:
   if item==LIGHT_BALL and name=='Pikachu':val*=2
   if item==DEEPSEA_TOOTH and name=='Clamperl':val*=2
   if item==SOUL_DEW and name in ('Latios','Latias'):val*=1.5
  elif index==5:
   if item==DEEPSEA_SCALE and name=='Clamperl':val*=2
   if item==SOUL_DEW and name in ('Latios','Latias'):val*=1.5
  return max(1,int(val))

 def _damage(self,source_side,target_side,damage,move=None,physical=None,critical=False,effectiveness=1,direct=True,reason=None):
  target=self.mon(target_side);source=self.mon(source_side);v=self.vol(target)
  # Substitute absorbs direct opposing damage and status-facing effects.
  if direct and source_side!=target_side and v.get('substituteHp',0)>0:
   hit=min(damage,v['substituteHp']);v['substituteHp']-=hit;self.logs.append('The substitute took damage!')
   if v['substituteHp']<=0:v.pop('substituteHp',None);self.logs.append(f'{self.name(target)}’s substitute faded!')
   return hit
  actual=min(target['hp'],max(0,int(damage)))
  if actual<=0:return 0
  # Focus Band can leave its holder at 1 HP.
  if actual>=target['hp'] and target.get('heldItemId')==FOCUS_BAND and target['hp']>1 and self.c.rng.random()<.1:actual=target['hp']-1
  if self.vol(target).get('endure') and actual>=target['hp'] and target['hp']>1:actual=target['hp']-1
  target['hp']=max(0,target['hp']-actual)
  if move and move.get('type')==10 and target.get('status')=='freeze':
   target['status']='';target['sleep']=0;self.logs.append(f'{self.name(target)} thawed out!');self.audio('status_clear',target_side,species=target['species'],status='freeze')
  if source_side!=target_side and direct:
   rec={'damage':actual,'physical':bool(physical),'sourceSide':source_side,'move':move['id'] if move else None};prior=self.damage_this_turn.get(target['uid'])
   if prior and prior['sourceSide']==source_side and prior['physical']==rec['physical'] and prior.get('move')==rec.get('move'):rec['damage']+=prior['damage']
   self.damage_this_turn[target['uid']]=rec;self.damaged_this_turn.add(target['uid'])
   # Bide stores all direct damage.
   if v.get('bideTurns'):v['bideDamage']=v.get('bideDamage',0)+actual
   if v.get('rage') and target['hp']>0:self._change_stage(target_side,1,1,source_side=target_side)
  if move:
   self.logs.append(f'{self.name(target)} lost {actual} HP.');self.audio('hit',target_side,species=target['species'],effectiveness=effectiveness,critical=critical,damage=actual)
   if critical:self.logs.append('A critical hit!')
   if effectiveness>1:self.logs.append("It's super effective!")
   elif 0<effectiveness<1:self.logs.append("It's not very effective.")
  else:self.audio('damage',target_side,species=target['species'],reason=reason or 'effect',amount=actual)
  # Color Change applies after a damaging hit.
  if move and target['hp']>0 and self.ability(target)==16 and move['type'] not in self.types(target):v['types']=[move['type']]
  return actual

 def _deal_fixed(self,side,target_side,damage,move):
  if not self._accuracy(side,move,move['effect']):self.logs.append('The attack missed!');self.audio('miss',side);return
  if self._protected(target_side,move) or self._semi_blocked(side,move):return
  mult=self._type_multiplier(side,target_side,move['type'],move)
  if self.ability(self.mon(target_side))==25 and mult<=1:mult=0
  if mult==0:self.logs.append('It had no effect.');self.audio('no_effect',target_side);return
  self._damage(side,target_side,max(1,damage),move=move,physical=move.get('category',0)==0,effectiveness=1)

 def _direct_hp_loss(self,side,amount,reason):
  m=self.mon(side);d=min(m['hp'],max(1,int(amount)));m['hp']-=d;self.logs.append(f'{self.name(m)} is hurt by {reason}.');self.audio('damage',side,species=m['species'],reason=reason,amount=d);return d
 def _recoil(self,side,amount):
  m=self.mon(side)
  if self.ability(m)==69:return
  self._direct_hp_loss(side,amount,'recoil')
 def _drain(self,side,amount):
  target=self.mon(1-side)
  if self.ability(target)==64:self._direct_hp_loss(side,max(1,amount//2),'liquid_ooze')
  else:self._heal(side,max(1,amount//2),quiet=True)
 def _heal(self,side,amount,quiet=False):
  m=self.mon(side);old=m['hp'];m['hp']=min(self.maxhp(m),m['hp']+max(1,int(amount)))
  if m['hp']==old:
   if not quiet:self._fail(side)
   return False
  if not quiet:self.logs.append(f'{self.name(m)} recovered {m["hp"]-old} HP.')
  self.audio('recover',side,species=m['species'],amount=m['hp']-old);return True

 def _secondary_roll(self,side,move):
  target=self.mon(1-side)
  if self.ability(target)==19:return False
  chance=move.get('chance',0)/100
  if self.ability(self.mon(side))==32:chance=min(1,chance*2)
  return chance>0 and self.c.rng.random()<chance
 def _secondary_status(self,side,status,move):
  if self._secondary_roll(side,move):self._apply_status(1-side,status,source_side=side)

 def _apply_status(self,side,status,source_side=None,ignore_safeguard=False,rest=False):
  m=self.mon(side);types=self.types(m);a=self.ability(m);v=self.vol(m)
  if m['status'] or v.get('substituteHp',0)>0 and source_side is not None and source_side!=side:return False
  if not ignore_safeguard and source_side is not None and source_side!=side and self.side[side]['safeguard']>0:return False
  if status in ('poison','toxic') and (3 in types or 8 in types or a==17):return False
  if status=='burn' and (10 in types or a==41):return False
  if status=='freeze' and (15 in types or a==40):return False
  if status=='sleep' and (a in (15,72) or any(self.vol(self.mon(s)).get('uproarTurns',0)>0 for s in (0,1))):return False
  if status=='paralysis' and a==7:return False
  m['status']=status;m['sleep']=2 if rest else self.c.rng.randint(2,5) if status=='sleep' else 0
  if status=='toxic':v['toxicCounter']=1
  self.logs.append(f'{self.name(m)} became {status}.');self.audio('status',side,species=m['species'],status=status)
  self._consume_item_if_needed(side)
  if source_side is not None and source_side!=side and a==28 and status in ('poison','toxic','burn','paralysis'):
   self._apply_status(source_side,status,source_side=side,ignore_safeguard=True)
  return True

 def _status_move(self,side,status,move,checked=False):
  target=1-side
  if status=='paralysis' and move['type']==13 and self._type_multiplier(side,target,13,move)==0:return self._ability_no_effect(target)
  if not checked:
   if not self._accuracy(side,move,move['effect']):self.logs.append('The attack missed!');self.audio('miss',side);return
   if self._protected(target,move):return
  # Magic Coat reflects reflectable status moves.
  if self.vol(self.mon(target)).pop('magicCoat',False) and move.get('flags',0)&FLAG_MAGIC_COAT:target=side
  if not self._apply_status(target,status,source_side=side):self._fail(side)

 def _confuse(self,side,source_side=None,move=None,ignore_safeguard=False):
  m=self.mon(side);v=self.vol(m)
  if self.ability(m)==20 or v.get('confusionTurns',0)>0 or v.get('substituteHp',0)>0 and source_side is not None and source_side!=side:return False
  if not ignore_safeguard and source_side is not None and source_side!=side and self.side[side]['safeguard']>0:return False
  v['confusionTurns']=self.c.rng.randint(2,5);self.logs.append(f'{self.name(m)} became confused!');self._consume_item_if_needed(side);return True
 def _flinch(self,side):
  m=self.mon(side)
  if self.ability(m)==39:return False
  if m['uid'] in self.acted_this_turn:return False
  self.vol(m)['flinch']=True;return True

 def _change_stage(self,side,index,delta,source_side=None,move=None,ability=False,self_inflicted=False):
  m=self.mon(side);a=self.ability(m)
  if delta<0 and source_side is not None and source_side!=side and not self_inflicted:
   if self.side[side]['mist']>0 or a in (29,73) or index==0 and a==51 or index==1 and a==52:return self._fail(source_side)
   if self.vol(m).get('substituteHp',0)>0:return self._fail(source_side)
  t=self.tiers(m);old=t[index];t[index]=max(-6,min(6,old+delta))
  if old==t[index]:
   if source_side is not None:self._fail(source_side)
   return False
  cue='stat_up' if delta>0 else 'stat_down';self.logs.append(f'{self.name(m)}: {STAT_NAMES[index]} {"rose" if delta>0 else "fell"}.');self.audio(cue,side,species=m['species'],stat=STAT_NAMES[index])
  if delta<0:self._white_herb(side)
  return True

 def _white_herb(self,side):
  m=self.mon(side)
  if m.get('heldItemId')!=WHITE_HERB:return
  t=self.tiers(m)
  if any(x<0 for x in t):
   self._remove_item(m,True)
   for i,x in enumerate(t):
    if x<0:t[i]=0
   self.logs.append(f'{self.name(m)} restored its lowered stats with White Herb!')

 def _remove_item(self,m,recyclable=False):
  item=m.get('heldItemId',0)
  if item and recyclable:self.vol(m)['lastItem']=item
  if item:m['heldItemId']=0
  return item
 def _consume_item_if_needed(self,side):
  m=self.mon(side);item=m.get('heldItemId',0);v=self.vol(m);hp=m['hp'];maxhp=self.maxhp(m)
  if not item or hp<=0:return
  status_cures={CHERI:'paralysis',CHESTO:'sleep',PECHA:('poison','toxic'),RAWST:'burn',ASPEAR:'freeze'}
  if item==LUM and (m['status'] or v.get('confusionTurns')):
   old=m['status'];m['status']='';m['sleep']=0;v.pop('confusionTurns',None);self._remove_item(m,True);self.logs.append(f'{self.name(m)} cured its condition with Lum Berry!');return
  if item in status_cures:
   want=status_cures[item];ok=m['status'] in want if isinstance(want,tuple) else m['status']==want
   if ok:m['status']='';m['sleep']=0;self._remove_item(m,True);self.logs.append(f'{self.name(m)} cured its condition with a Berry!');return
  if item==PERSIM and v.get('confusionTurns'):v.pop('confusionTurns',None);self._remove_item(m,True);return
  if item==MENTAL_HERB and v.get('attractSource'):v.pop('attractSource',None);self._remove_item(m,True);return
  if item==LEPPA:
   slot=next((q for q in self._moves(m) if q.get('pp',0)==0),None)
   if slot:slot['pp']=min(self.c.moves[str(slot['id'])]['pp'],10);self._remove_item(m,True);return
  heal=0
  if hp*2<=maxhp:
   if item==BERRY_JUICE:heal=20
   elif item==ORAN:heal=10
   elif item==SITRUS:heal=30
  if heal:self._remove_item(m,True);self._heal(side,heal,quiet=True);return
  if hp*4<=maxhp:
   if item in PINCH_BERRIES:self._remove_item(m,True);self._heal(side,max(1,maxhp//8),quiet=True);return
   boost={LIECHI:1,GANLON:2,SALAC:3,PETAYA:4,APICOT:5}.get(item)
   if boost:self._remove_item(m,True);self._change_stage(side,boost,1,source_side=side);return
   if item==LANSAT:self._remove_item(m,True);v['focusEnergy']=True;return
   if item==STARF:
    self._remove_item(m,True);choices=[i for i in (1,2,3,4,5) if self.tiers(m)[i]<6]
    if choices:self._change_stage(side,self.c.rng.choice(choices),2,source_side=side)

 def _contact_effects(self,side,move):
  if not move.get('flags',0)&FLAG_CONTACT:return
  m=self.mon(side);enemy=self.mon(1-side)
  if enemy['hp']<=0 or m['hp']<=0:return
  a=self.ability(enemy)
  if a==24:self._direct_hp_loss(side,max(1,self.maxhp(m)//16),'rough_skin')
  elif a in (9,38,49,27,56) and self.c.rng.random()<.3:
   if a==9:self._apply_status(side,'paralysis',source_side=1-side)
   elif a==38:self._apply_status(side,'poison',source_side=1-side)
   elif a==49:self._apply_status(side,'burn',source_side=1-side)
   elif a==27:self._apply_status(side,self.c.rng.choice(['sleep','poison','paralysis']),source_side=1-side)
   elif a==56:self._attract(1-side,None,target_side=side)
  if m.get('heldItemId')==KINGS_ROCK and move.get('flags',0)&FLAG_KINGS_ROCK and self.c.rng.random()<.1:self._flinch(1-side)

 def _trapped(self,side):
  m=self.mon(side);v=self.vol(m);enemy=self.mon(1-side);ea=self.ability(enemy)
  if v.get('trappedBy') and v.get('trappedBy')!=enemy['uid']:
   v.pop('trappedBy',None);v.pop('wrapTurns',None);v.pop('wrappedBy',None)
  if v.get('trappedBy') or v.get('ingrain'):return True
  if ea==23:return True
  if ea==42 and 8 in self.types(m):return True
  if ea==71 and 2 not in self.types(m) and self.ability(m)!=26:return True
  return False

 def _switch(self,side,index,baton=None):
  old=self.mon(side)
  if self.ability(old)==30:old['status']='';old['sleep']=0
  self.active[side]=index;self.logs.append(f'{self.names[side]} sent out {self.name(self.mon(side))}!');self.sendout_audio(side,baton=baton)

 def _force_switch(self,target_side,source_side,move):
  target=self.mon(target_side);source=self.mon(source_side)
  if self.ability(target)==21 or self.vol(target).get('ingrain'):return self._fail(source_side)
  # In a wild encounter Roar/Whirlwind ends the encounter on success. FireRed
  # guarantees success at equal/higher level; lower-level users pass the ROM's
  # byte-scaled level check before forcing the encounter out.
  if self.kind=='wild':
   if source['level']<target['level']:
    roll=self.c.rng.randrange(256)
    if ((roll*(source['level']+target['level']))>>8)+1<=target['level']//4:return self._fail(source_side)
   self.ended=True;self.winner=None;self.logs.append('The wild Pokemon was blown away!');self.audio('escape',source_side);return
  choices=[i for i,q in enumerate(self.rosters[target_side]) if i!=self.active[target_side] and q['hp']>0]
  if not choices:return self._fail(source_side)
  self._switch(target_side,self.c.rng.choice(choices))

 def _screen(self,side,key):
  if self.side[side][key]>0:return self._fail(side)
  self.side[side][key]=5;self.logs.append(f'{key} raised the team’s protection!')
 def _side_condition(self,side,key,turns):
  if self.side[side][key]>0:return self._fail(side)
  self.side[side][key]=turns;self.logs.append(f'{self.name(self.mon(side))} protected its team!')
 def _weather(self,kind,side):
  if self.weather==kind and self.weather_turns>0:return self._fail(side)
  self.weather=kind;self.weather_turns=5;self.logs.append({'rain':'It started to rain!','sun':'The sunlight turned harsh!','sand':'A sandstorm brewed!','hail':'It started to hail!'}[kind])

 def _rest(self,side):
  m=self.mon(side)
  if m['hp']>=self.maxhp(m):return self._fail(side)
  if not self._apply_status(side,'sleep',source_side=side,ignore_safeguard=True,rest=True):return self._fail(side)
  m['hp']=self.maxhp(m);self.logs.append(f'{self.name(m)} slept and became healthy!');self.audio('recover',side,species=m['species'],amount=self.maxhp(m))
 def _substitute(self,side):
  m=self.mon(side);cost=max(1,self.maxhp(m)//4);v=self.vol(m)
  if v.get('substituteHp') or m['hp']<=cost:return self._fail(side)
  m['hp']-=cost;v['substituteHp']=cost;v.pop('wrapTurns',None);v.pop('trappedBy',None);v.pop('wrappedBy',None);self.logs.append(f'{self.name(m)} made a substitute!')
 def _protect(self,side):
  m=self.mon(side);v=self.vol(m);chain=v.get('protectChain',0);den=min(8,2**chain)
  if chain and self.c.rng.randrange(den)!=0:v['protectChain']=0;return self._fail(side)
  v['protectChain']=chain+1;self.protected.add(m['uid']);self.logs.append(f'{self.name(m)} protected itself!');self.audio('protected',side,species=m['species'])
 def _endure(self,side):
  m=self.mon(side);v=self.vol(m);chain=v.get('protectChain',0);den=min(8,2**chain)
  if chain and self.c.rng.randrange(den)!=0:v['protectChain']=0;return self._fail(side)
  v['protectChain']=chain+1;v['endure']=True;self.logs.append(f'{self.name(m)} braced itself!')
 def _leech_seed(self,side,move):
  enemy=self.mon(1-side)
  if 12 in self.types(enemy) or self.vol(enemy).get('leechSeedSource') or self.vol(enemy).get('substituteHp'):return self._fail(side)
  self.vol(enemy)['leechSeedSource']=self.mon(side)['uid'];self.seeded.add(enemy['uid']);self.logs.append(f'{self.name(enemy)} was seeded!')
 def _disable(self,side):
  enemy=self.mon(1-side);mid=self.last_move[1-side];slot=next((q for q in self._moves(enemy) if q['id']==mid),None)
  if not mid or not slot or slot.get('pp',0)<=0 or self.vol(enemy).get('disableTurns'):return self._fail(side)
  self.vol(enemy).update(disabledMove=mid,disableTurns=self.c.rng.randint(2,5));self.logs.append(f'{self.name(enemy)}’s last move was disabled!')
 def _encore(self,side):
  enemy=self.mon(1-side);mid=self.last_move[1-side]
  if not mid or mid in (119,165,227) or self.vol(enemy).get('encoreTurns'):return self._fail(side)
  if not any(q['id']==mid and q['pp']>0 for q in self._moves(enemy)):return self._fail(side)
  self.vol(enemy).update(encoreMove=mid,encoreTurns=self.c.rng.randint(3,6));self.logs.append(f'{self.name(enemy)} received an encore!')
 def _pain_split(self,side):
  a=self.mon(side);b=self.mon(1-side);avg=(a['hp']+b['hp'])//2;a['hp']=min(self.maxhp(a),avg);b['hp']=min(self.maxhp(b),avg);self.logs.append('The battlers shared their pain!')
 def _spite(self,side):
  enemy=self.mon(1-side);mid=self.last_move[1-side];slot=next((q for q in self._moves(enemy) if q['id']==mid),None)
  if not slot or slot.get('pp',0)<=1:return self._fail(side)
  slot['pp']=max(0,slot['pp']-self.c.rng.randint(2,5));self.logs.append(f'{self.name(enemy)}’s PP was reduced!')
 def _heal_bell(self,side,mid):
  changed=False;is_bell=mid==215
  for q in self.rosters[side]:
   if q['status'] and not (is_bell and self.ability(q)==43):q['status']='';q['sleep']=0;changed=True
  if not changed:return self._fail(side)
  self.logs.append('The party’s status problems were cured!')
 def _weather_heal(self,side):
  w=self.weather_active();den=3 if w=='sun' else 4 if w in ('rain','sand','hail') else 2;num=2 if w=='sun' else 1;self._heal(side,max(1,self.maxhp(self.mon(side))*num//den))
 def _belly_drum(self,side):
  m=self.mon(side);cost=self.maxhp(m)//2
  if m['hp']<=cost or self.tiers(m)[1]>=6:return self._fail(side)
  m['hp']-=cost;self.tiers(m)[1]=6;self.logs.append(f'{self.name(m)} cut its HP and maximized Attack!')
 def _curse(self,side):
  m=self.mon(side);enemy=self.mon(1-side)
  if 7 in self.types(m):
   cost=max(1,self.maxhp(m)//2)
   if m['hp']<=cost:return self._fail(side)
   m['hp']-=cost;self.vol(enemy)['curseSource']=m['uid'];self.logs.append(f'{self.name(enemy)} was afflicted by a curse!')
  else:
   self._change_stage(side,3,-1,source_side=side,self_inflicted=True);self._change_stage(side,1,1,source_side=side);self._change_stage(side,2,1,source_side=side)
 def _attract(self,side,move,target_side=None):
  if target_side is None:target_side=1-side
  source=self.mon(side);target=self.mon(target_side)
  if self.ability(target)==12:return self._fail(side)
  a,b=self.gender(source),self.gender(target)
  if a=='genderless' or b=='genderless' or a==b:return self._fail(side)
  self.vol(target)['attractSource']=source['uid'];self.logs.append(f'{self.name(target)} fell in love!');self._consume_item_if_needed(target_side)
 def _memento(self,side):
  target=self.mon(1-side);tiers=self.tiers(target)
  if tiers[1]<=-6 and tiers[4]<=-6:return self._fail(side)
  self._change_stage(1-side,1,-2,source_side=side);self._change_stage(1-side,4,-2,source_side=side);self.mon(side)['hp']=0;self.logs.append(f'{self.name(self.mon(side))} fainted from Memento!')
 def _trick(self,side):
  a=self.mon(side);b=self.mon(1-side)
  if self.ability(a)==60 or self.ability(b)==60 or not (a.get('heldItemId') or b.get('heldItemId')):return self._fail(side)
  a['heldItemId'],b['heldItemId']=b.get('heldItemId',0),a.get('heldItemId',0);self.logs.append('The held items were switched!')
 def _skill_swap(self,side):
  a=self.mon(side);b=self.mon(1-side);aa=self.ability(a);bb=self.ability(b)
  if (not aa and not bb) or aa==25 or bb==25:return self._fail(side)
  self.vol(a)['ability']=bb;self.vol(b)['ability']=aa;self.logs.append('The battlers swapped Abilities!')
 def _refresh(self,side):
  m=self.mon(side)
  if m['status'] not in ('poison','toxic','burn','paralysis'):return self._fail(side)
  st=m['status'];m['status']='';m['sleep']=0;self.logs.append(f'{self.name(m)} cured its {st}!')
 def _recycle(self,side):
  m=self.mon(side);v=self.vol(m)
  if m.get('heldItemId') or not v.get('lastItem'):return self._fail(side)
  m['heldItemId']=v.pop('lastItem');self.logs.append(f'{self.name(m)} recycled its item!')
 def _swallow(self,side):
  m=self.mon(side);v=self.vol(m);n=v.get('stockpile',0)
  if not n:return self._fail(side)
  amount={1:self.maxhp(m)//4,2:self.maxhp(m)//2,3:self.maxhp(m)}[n];v['stockpile']=0;self._heal(side,max(1,amount))
 def _camouflage(self,side):
  typ={'grass':12,'long_grass':12,'sand':4,'underwater':11,'water':11,'pond':11,'mountain':5,'cave':5,'building':0,'plain':0}.get(self.terrain,0);self.vol(self.mon(side))['types']=[typ];self.logs.append(f'{self.name(self.mon(side))} changed type!')
 def _conversion(self,side):
  m=self.mon(side);choices=[self.c.moves[str(q['id'])]['type'] for q in self._moves(m) if self.c.moves[str(q['id'])]['type'] not in self.types(m)]
  if not choices:return self._fail(side)
  self.vol(m)['types']=[self.c.rng.choice(choices)];self.logs.append(f'{self.name(m)} changed type!')
 def _conversion2(self,side):
  last=self.last_successful_move[1-side]
  if not last:return self._fail(side)
  incoming=self.c.moves[str(last)]['type'];choices=[]
  for typ in range(18):
   if 0<matchup(incoming,[typ])<1:choices.append(typ)
  if not choices:return self._fail(side)
  self.vol(self.mon(side))['types']=[self.c.rng.choice(choices)];self.logs.append(f'{self.name(self.mon(side))} changed type!')
 def _transform(self,side):
  m=self.mon(side);enemy=self.mon(1-side);v=self.vol(m);ev=self.vol(enemy)
  if v.get('transformed') or ev.get('transformed') or ev.get('substituteHp'):return self._fail(side)
  v['transformed']=True;v['types']=self.types(enemy);v['ability']=self.ability(enemy);v['speciesOverride']=ev.get('speciesOverride',enemy['species']);v['statsOverride']=self.c.stats(enemy);self.stages[m['uid']]=self.tiers(enemy)[:]
  v['movesOverride']=[{'id':q['id'],'pp':5} for q in self._moves(enemy)];self.logs.append(f'{self.name(m)} transformed!')
 def _mimic(self,side,move):
  m=self.mon(side);last=self.last_move[1-side]
  if self.vol(m).get('transformed') or not last or last in MIMIC_BANNED or str(last) not in self.c.moves:return self._fail(side)
  if any(q.get('id')==last for q in self._moves(m)):return self._fail(side)
  moves=copy.deepcopy(self._moves(m));slot=next((q for q in moves if q['id']==move['id']),None)
  if not slot:return self._fail(side)
  slot['id']=last;slot['pp']=min(5,self.c.moves[str(last)]['pp']);self.vol(m)['movesOverride']=moves;self.logs.append(f'{self.name(m)} learned the foe’s move for this battle!')
 def _sketch(self,side):
  m=self.mon(side);last=self.last_move[1-side];v=self.vol(m)
  # FireRed forbids Sketch while transformed and cannot copy NONE, Struggle,
  # Sketch itself, an unavailable move, or a move already known permanently.
  if v.get('transformed') or not last or last in (165,166) or str(last) not in self.c.moves:return self._fail(side)
  if any(q.get('id')==last for q in m.get('moves',[])):return self._fail(side)
  current=self.last_move[side];slot=next((q for q in m.get('moves',[]) if q['id']==current),None)
  if not slot:return self._fail(side)
  slot['id']=last;slot['pp']=self.c.moves[str(last)]['pp'];self.logs.append(f'{self.name(m)} sketched the move!')
 def _baton_pass(self,side,a):
  m=self.mon(side);choices=[i for i,q in enumerate(self.rosters[side]) if i!=self.active[side] and q['hp']>0]
  if not choices:return self._fail(side)
  wanted=a.get('uid');idx=next((i for i in choices if self.rosters[side][i]['uid']==wanted),choices[0])
  v=self.vol(m);pass_keys={'confusionTurns','focusEnergy','substituteHp','leechSeedSource','ingrain','perish','attractSource'}
  baton={'stages':self.tiers(m)[:],'volatile':{k:copy.deepcopy(v[k]) for k in pass_keys if k in v}}
  self._switch(side,idx,baton=baton)
 def _ohko(self,side,move):
  m=self.mon(side);enemy=self.mon(1-side)
  if self._protected(1-side,move) or self._semi_blocked(side,move):return
  mult=self._type_multiplier(side,1-side,move['type'],move)
  if self.ability(enemy)==25 and mult<=1:mult=0
  if mult==0:self.logs.append('It had no effect.');self.audio('no_effect',1-side);return
  if self.ability(enemy)==5 or m['level']<enemy['level']:return self._fail(side)
  locked=self.vol(enemy).get('lockOnSource')==m['uid'] and self.vol(enemy).get('lockOnTurns',0)>0
  chance=move.get('accuracy',30)+m['level']-enemy['level']
  # FireRed compares Random()%100 + 1 against the level-adjusted threshold.
  if not locked and self.c.rng.randrange(100)+1>=chance:self.logs.append('The attack missed!');self.audio('miss',side);return
  self._damage(side,1-side,enemy['hp'],move=move,physical=move.get('category',0)==0,effectiveness=1)
 def _jump_kick_crash(self,side,move):
  m=self.mon(side);enemy=self.mon(1-side);typ,power=self._power_type(side,move,move['effect']);damage,_,mult,_=self._calculate_damage(side,move,power or move['power'],typ,move['effect'])
  if mult:self._direct_hp_loss(side,max(1,damage//2),'crash')
  self.logs.append('The attack missed!');self.audio('miss',side)
 def _beat_up(self,side,move):
  target=self.mon(1-side);participants=[q for q in self.rosters[side] if q['hp']>0 and not q['status']]
  if not participants:return self._fail(side)
  if not self._accuracy(side,move,move['effect']) or self._protected(1-side,move):return
  total=0;base_def=max(1,self.c.species[target['species']]['baseStats'][2])
  mult=self._type_multiplier(side,1-side,move['type'],move)
  if not mult:return self._ability_no_effect(1-side)
  for q in participants:
   base_atk=self.c.species[q['species']]['baseStats'][1];raw=((2*q['level']//5+2)*10*base_atk//base_def//50)+2;d=max(1,int(raw*mult*self.c.rng.randint(85,100)/100));total+=self._damage(side,1-side,d,move=move,physical=True,effectiveness=mult)
   if target['hp']<=0:break
  self.logs.append(f'Beat Up struck {len(participants)} times!')
 def _secret_power_secondary(self,side,move):
  # One FireRed secondary-effect roll, then the terrain-specific payload.
  # Shield Dust and Serene Grace are handled by that single roll.
  if not self._secondary_roll(side,move):return
  terrain=self.terrain
  if terrain=='grass':self._apply_status(1-side,'poison',source_side=side)
  elif terrain=='long_grass':self._apply_status(1-side,'sleep',source_side=side)
  elif terrain=='sand':self._change_stage(1-side,0,-1,source_side=side)
  elif terrain=='underwater':self._change_stage(1-side,2,-1,source_side=side)
  elif terrain=='water':self._change_stage(1-side,1,-1,source_side=side)
  elif terrain=='pond':self._change_stage(1-side,3,-1,source_side=side)
  elif terrain=='mountain':self._confuse(1-side,source_side=side,move=move)
  elif terrain=='cave':self._flinch(1-side)
  else:self._apply_status(1-side,'paralysis',source_side=side)

 def _advance_repeat(self,v,key,confuse_side=None):
  if not v.get(key):return
  v[key]-=1
  if v[key]<=0:
   v.pop(key,None);v.pop('forcedMove',None);v.pop('multiTurnPP',None)
   if confuse_side is not None:self._confuse(confuse_side,source_side=confuse_side,ignore_safeguard=True)

 def _ability_no_effect(self,side):self.logs.append('It had no effect.');self.audio('no_effect',side);return False
 def _fail(self,side):self.logs.append('But it failed!');self.audio('no_effect',side);return False

 def _weather_turn(self):
  weather=self.weather_active()
  for side in (0,1):
   m=self.mon(side)
   if m['hp']<=0:continue
   if weather=='sand' and not any(t in self.types(m) for t in (4,5,8)) and self.ability(m) not in (8,45):self._direct_hp_loss(side,max(1,self.maxhp(m)//16),'sandstorm')
   elif weather=='hail' and 15 not in self.types(m):self._direct_hp_loss(side,max(1,self.maxhp(m)//16),'hail')
   if weather=='rain' and self.ability(m)==44:self._heal(side,max(1,self.maxhp(m)//16),quiet=True)
  if self.weather_turns>0:
   self.weather_turns-=1
   if self.weather_turns==0:self.logs.append('The weather returned to normal.');self.weather=''

 def _end_turn(self):
  # Delayed attacks/wishes tick before ordinary residuals in this compact Gen-III ordering.
  for e in list(self.future):
   e['turns']-=1
   if e['turns']<=0:
    target=self.mon(e['targetSide']);self._damage(e['sourceSide'],e['targetSide'],e['damage'],move=e['move'],physical=False,effectiveness=1);self.future.remove(e)
  for w in list(self.wishes):
   w['turns']-=1
   if w['turns']<=0:self._heal(w['side'],w['amount'],quiet=True);self.wishes.remove(w)
  uproar=any(self.vol(self.mon(q)).get('uproarTurns',0)>0 for q in (0,1))
  if uproar:
   for q in (0,1):
    qm=self.mon(q)
    if qm['hp']>0 and qm.get('status')=='sleep' and self.ability(qm)!=43:qm['status']='';qm['sleep']=0;self.logs.append(f'{self.name(qm)} woke up in the uproar!');self.audio('status_clear',q,species=qm['species'],status='sleep')
  for side in (0,1):
   m=self.mon(side);v=self.vol(m)
   if m['hp']<=0:continue
   if m['status'] in ('poison','burn'):
    self._direct_hp_loss(side,max(1,self.maxhp(m)//8),m['status'])
   elif m['status']=='toxic':
    c=max(1,v.get('toxicCounter',1));self._direct_hp_loss(side,max(1,self.maxhp(m)*c//16),'toxic');v['toxicCounter']=min(15,c+1)
   if m['hp']>0 and v.get('leechSeedSource'):
    amount=min(m['hp'],max(1,self.maxhp(m)//8));self._direct_hp_loss(side,amount,'leech_seed');other=self.mon(1-side)
    if other['hp']>0:
     if self.ability(m)==64:self._direct_hp_loss(1-side,amount,'liquid_ooze')
     else:self._heal(1-side,amount,quiet=True)
   if m['hp']>0 and v.get('curseSource'):self._direct_hp_loss(side,max(1,self.maxhp(m)//4),'curse')
   if v.get('nightmare') and m['status']!='sleep':v.pop('nightmare',None)
   if m['hp']>0 and v.get('nightmare') and m['status']=='sleep':self._direct_hp_loss(side,max(1,self.maxhp(m)//4),'nightmare')
   if m['hp']>0 and v.get('wrapTurns',0)>0:
    self._direct_hp_loss(side,max(1,self.maxhp(m)//16),'binding');v['wrapTurns']-=1
    if v['wrapTurns']<=0:v.pop('wrapTurns',None);v.pop('trappedBy',None);v.pop('wrappedBy',None)
   if m['hp']>0 and v.get('ingrain'):self._heal(side,max(1,self.maxhp(m)//16),quiet=True)
   if m['hp']>0 and m.get('heldItemId')==LEFTOVERS:self._heal(side,max(1,self.maxhp(m)//16),quiet=True)
   if m['hp']>0 and self.ability(m)==3:self._change_stage(side,3,1,source_side=side)
   if m['hp']>0 and self.ability(m)==61 and m['status'] and self.c.rng.randrange(3)==0:
    old=m['status'];m['status']='';m['sleep']=0;self.logs.append(f'{self.name(m)} shed its {old}!')
   if v.get('yawn'):
    v['yawn']-=1
    if v['yawn']<=0:v.pop('yawn',None);self._apply_status(side,'sleep',source_side=1-side)
   if v.get('perish'):
    v['perish']-=1
    if v['perish']<=0:m['hp']=0;self.logs.append(f'{self.name(m)}’s perish count fell to zero!')
    else:self.logs.append(f'{self.name(m)}’s perish count is {v["perish"]}.')
   for key in ('disableTurns','encoreTurns','tauntTurns','lockOnTurns','chargeElectric'):
    if v.get(key,0)>0:
     v[key]-=1
     if v[key]<=0:
      v.pop(key,None)
      if key=='disableTurns':v.pop('disabledMove',None)
      elif key=='encoreTurns':v.pop('encoreMove',None)
      elif key=='lockOnTurns':v.pop('lockOnSource',None)
   v.pop('endure',None);v.pop('magicCoat',None);v.pop('snatch',None)
   self._consume_item_if_needed(side)
  for s in (0,1):
   for key in ('reflect','lightScreen','safeguard','mist'):
    if self.side[s][key]>0:self.side[s][key]-=1
  self._weather_turn()

 def _collect_experience(self):
  if self.kind=='duel':return
  enemy=self.mon(1)
  if enemy['hp']<=0 and enemy['uid'] not in self.experience_awarded:
   self.experience_awarded.add(enemy['uid']);self.experience_events.append({'species':enemy['species'],'level':enemy['level'],'participants':sorted(self.participants.get(enemy['uid'],()))})

 def _resolve_faints(self):
  # Destiny Bond / Grudge are evaluated against direct KO records before switch-in.
  for side in (0,1):
   m=self.mon(side)
   if m['hp']<=0:
    rec=self.damage_this_turn.get(m['uid']);v=self.vol(m)
    if rec and v.get('destinyBond') and self.mon(rec['sourceSide'])['hp']>0:self.mon(rec['sourceSide'])['hp']=0;self.logs.append('Destiny Bond took its attacker down!')
    if rec and v.get('grudge'):
     attacker=self.mon(rec['sourceSide']);slot=next((q for q in self._moves(attacker) if q['id']==rec.get('move')),None)
     if slot:slot['pp']=0;self.logs.append('Grudge depleted the attacking move’s PP!')
  for side in (0,1):
   m=self.mon(side)
   if m['hp']<=0:
    self.logs.append(f'{self.name(m)} fainted!');self.audio('faint',side,species=m['species']);alive=next((i for i,q in enumerate(self.rosters[side]) if q['hp']>0),None)
    if alive is None:self.ended=True;self.winner=1-side
    else:self._switch(side,alive)

