"""Single-authority world actor, spatial replication and transactional services.
All player mutations execute under the world lock. Database calls run off-loop.
Extensions may submit intents, never client-provided state snapshots.
"""
from __future__ import annotations
import asyncio,collections,copy,hashlib,json,logging,math,time,uuid
from dataclasses import dataclass,field
from .security import Bucket,RequestError,require,integer
from .combat import Battle
from .varieties import variety_key
from .adventure import Adventure
from .field_moves import CUT_REQUIREMENTS,cut_allowed,is_cut_tree,region,tree_cleared
from .encounters import encounter_slots,select_encounter
from .portals import plan_warp,return_stack
from .async_tasks import complete_before_cancelling
log=logging.getLogger('nxt.world')
DIRECTIONS={'down':(0,1,1),'up':(0,-1,2),'left':(-1,0,3),'right':(1,0,4)}
WATER={16,17,18,19,21,26,27}
@dataclass
class Player:
 id:int
 username:str
 state:dict
 queue:asyncio.Queue
 closed:bool=False
 battle:str|None=None
 trade:str|None=None
 last_move:float=0
 last_seq:int=-1
 last_encounter:float=0
 fx:int=0
 fy:int=0
 seen:dict=field(default_factory=dict)
 move_bucket:Bucket=field(default_factory=lambda:Bucket(12,1))
 command_bucket:Bucket=field(default_factory=lambda:Bucket(40,1))
 chat_bucket:Bucket=field(default_factory=lambda:Bucket(5,10))
 muted_until:float=0
 npc_cooldowns:dict=field(default_factory=dict)
 saved_revision:int=0
 audio_session:str=field(default_factory=lambda:uuid.uuid4().hex)
 audio_sequence:int=0
 def send(self,event_type,**data):
  if self.closed:return
  # The socket writer runs later. Freeze nested state now so subsequent world
  # mutations cannot change an already queued revision, party or battle view.
  try:self.queue.put_nowait(copy.deepcopy({'type':event_type,**data}))
  except asyncio.QueueFull:self.closed=True
 def audio(self,cue,**data):
  """Owner-only, server-confirmed presentation events; never persisted in saves."""
  self.audio_sequence+=1;key=f'{self.audio_session}:{self.audio_sequence}'
  self.send('audio',id=key,events=[{'id':key+':0','cue':cue,'source':self.state['map'].split('_',1)[0],**data}])
 def entity(self):
  s=self.state;lead=next((m for m in s['creatures'] if m['uid']==s['party'][0]),None)
  return {'id':self.id,'username':self.username,'map':s['map'],'x':s['x'],'y':s['y'],'direction':s.get('direction','down'),'appearance':s['appearance'],'follower':lead['species'] if lead else None,'shiny':variety_key(lead)=='shiny','followerVariety':variety_key(lead),'fx':self.fx,'fy':self.fy,'busy':bool(self.battle or self.trade),'surf':s.get('surf',False)}
class World:
 def __init__(self,content,store,settings):
  self.c=content;self.adventure=Adventure(content);self.db=store;self.s=settings;self.players={};self.invites={};self.trades={};self.battles={};self.lock=asyncio.Lock();self.chat={'general':collections.deque(maxlen=30),'trade':collections.deque(maxlen=30)};self.started=time.monotonic();self.ticks=0;self.last_tick_ms=0;self.max_tick_ms=0;self.extension_hooks=collections.defaultdict(list);self.stopping=False
 def hook(self,event,callback):self.extension_hooks[event].append(callback)
 def emit(self,event,**context):
  for cb in self.extension_hooks.get(event,[]):
   try:cb(self,**context)
   except Exception:log.exception('Extension hook failed: %s',event)
 def initial(self,name,home,starter,appearance):
  require(isinstance(home,str) and home in self.c.data['homes'],'Select Kanto or Johto.');require(isinstance(starter,str) and starter in self.c.data['starters'],'Select a valid starter.');require(type(appearance) is int and appearance in (0,7),'Invalid trainer appearance.')
  key=self.c.data['homes'][home];m=self.c.maps[key];mon=self.c.new_mon(starter,5,name)
  state={'format':1,'revision':1,'map':key,'x':m['spawn'][0],'y':m['spawn'][1],'direction':'down','home':home,'appearance':appearance,'money':self.s.int('gameplay','starting_money'),'items':{'pokeball':self.s.int('gameplay','starting_pokeballs'),'potion':self.s.int('gameplay','starting_potions')},'creatures':[mon],'party':[mon['uid']],'surf':False}
  return self.c.varieties.migrate(self.adventure.migrate(state))
 def validate_state(self,state):
  require(state.get('format')==1,'This character requires a state migration.')
  mons=state.get('creatures',[]);ids={m['uid'] for m in mons};party=state.get('party',[])
  require(len(ids)==len(mons) and 1<=len(party)<=6 and len(set(party))==len(party) and all(i in ids for i in party),'Character ownership validation failed; contact the administrator.')
  require(all(m['species'] in self.c.species for m in mons),'This character needs a newer content pack.')
  if state['map'] not in self.c.maps or not self.c.maps[state['map']].get('playable',True):state['map']=self.c.data['homes'][state['home']];state['x'],state['y']=self.c.maps[state['map']]['spawn']
  m=self.c.maps[state['map']]
  if not (0<=state['x']<m['width'] and 0<=state['y']<m['height']):state['x'],state['y']=m['spawn']
  migrated=self.adventure.migrate(state)
  if hasattr(self.c,'growth'):migrated=self.c.growth.migrate(migrated)
  migrated=self.c.varieties.migrate(migrated)
  state.clear();state.update(migrated)
 async def join(self,uid,name,state,queue):
  async with self.lock:
   require(not self.stopping,'World is shutting down.');require(uid not in self.players,'This account is already online.');require(len(self.players)<self.s.max_players,'This world is full. Please try again later.')
   # Login must load after a previous session's final save and removal, under
   # the same lock. A preloaded snapshot can otherwise resurrect old progress.
   if state is None:state=await asyncio.to_thread(self.db.load,uid)
   original=copy.deepcopy(state);state=copy.deepcopy(state);self.validate_state(state)
   if state!=original:
    state['revision']=original['revision']+1
    try:await complete_before_cancelling(asyncio.to_thread(self.db.save_many,[(uid,state)]))
    except Exception as e:raise RequestError('The database could not save your adventure migration. Your account was not changed; try again after the database is available.') from e
   p=Player(uid,name,state,queue);self.follower_anchor(p);p.saved_revision=state['revision'];p.chat_bucket=Bucket(self.s.int('security','chat_messages_per_10_seconds'),10);self.players[uid]=p
   p.send('joined',id=uid,username=name,pack=self.c.pack,version=self.c.data['version'],world=self.s.get('world','name'),cap=self.s.max_players,online=len(self.players),stepMs=self.s.step_ms,alphaAtlas=self.s.flag('world','allow_alpha_atlas'),alphaSurf=self.s.flag('world','allow_alpha_surf'),motd=self.s.get('world','motd'))
   self.send_map(p);self.send_state(p)
   for channel,messages in self.chat.items():p.send('chat_history',channel=channel,messages=list(messages))
   self.emit('login',player=p);log.info('Joined %s (%d); online=%d',name,uid,len(self.players));return p
 def send_map(self,p,transition='arrival'):
  m=self.c.maps[p.state['map']];p.seen.clear();p.send('map',id=m['id'],name=m['name'],region=m['region'],transition=transition,entity=p.entity())
 def send_state(self,p):
  s=p.state;p.send('state',ownerId=p.id,money=s['money'],items=s['items'],party=s['party'],creatures=[self.c.public_mon(m) for m in s['creatures']],home=s['home'],revision=s['revision'],adventure=self.adventure.public(s))
 def party(self,p):return [next(m for m in p.state['creatures'] if m['uid']==uid) for uid in p.state['party']]
 async def commit(self,p,state):
  self.adventure.observe(state,[m['species'] for m in state['creatures']],caught=True);self.c.varieties.observe(state,state['creatures'],caught=True);self.adventure.refresh_unlocks(state)
  state['revision']=p.state['revision']+1
  try:await asyncio.to_thread(self.db.save_many,[(p.id,state)])
  except Exception as e:log.exception('State commit failed for %s',p.username);raise RequestError('The database could not save this action. Nothing was changed; contact the administrator.') from e
  p.state=state;p.saved_revision=state['revision'];self.send_state(p)
 def free(self,p):require(not p.battle and not p.trade,'Finish your current battle or trade first.')
 def nearby(self,a,b,radius=8):return a.state['map']==b.state['map'] and max(abs(a.state['x']-b.state['x']),abs(a.state['y']-b.state['y']))<=radius
 def require_peer(self,p,uid):
  integer(uid,1,2**53-1,'Trainer ID');q=self.players.get(uid);require(q is not None and not q.closed and q.id!=p.id,'That trainer is not available.');require(self.nearby(p,q),'Move closer to that trainer.');return q
 def walkable(self,m,x,y,surf=False,from_elevation=None,state=None):
  if not(0<=x<m['width'] and 0<=y<m['height']):return False
  j=y*m['width']+x
  # A cut overrides ONLY its exact occupied tile, never the shared grid.
  cleared=any(o['x']==x and o['y']==y and tree_cleared(state,m['id'],o) for o in m['objects'])
  if (m['collision'][j]!=0 and not cleared) or (m['behavior'][j] in WATER and not surf):return False
  elevation=m['elevation'][j]
  if from_elevation is not None and elevation not in (0,15) and from_elevation not in (0,15) and elevation!=from_elevation:return False
  # Solid environmental objects. Story-dependent NPC flags are not executed in alpha.
  if any(o['x']==x and o['y']==y and o['graphics'] in (95,96,97) and not tree_cleared(state,m['id'],o) for o in m['objects']):return False
  return True
 def follower_anchor(self,p):
  m=self.c.maps[p.state['map']];x,y=p.state['x'],p.state['y'];p.fx=x;p.fy=y
  for dx,dy in ((-1,0),(1,0),(0,1),(0,-1)):
   if self.walkable(m,x+dx,y+dy,p.state.get('surf',False),state=p.state):p.fx=x+dx;p.fy=y+dy;break
 def relocation_state(self,p,key,x=None,y=None,*,surf=None):
  require(key in self.c.maps,'That destination is not in this content pack.');m=self.c.maps[key];require(m.get('playable',True),'This extracted placeholder map has no walkable area in the alpha.')
  state=copy.deepcopy(p.state)
  if surf is not None:state['surf']=surf
  if x is None:x,y=m['spawn']
  if not self.walkable(m,x,y,state.get('surf',False),state=state):
   nearby=[(abs(xx-x)+abs(yy-y),xx,yy) for yy in range(max(0,y-4),min(m['height'],y+5)) for xx in range(max(0,x-4),min(m['width'],x+5)) if self.walkable(m,xx,yy,state.get('surf',False),state=state)]
   if nearby:_,x,y=min(nearby)
   else:x,y=m['spawn']
  state.update(map=key,x=x,y=y);self.adventure.visit(state,key);return state
 def relocate(self,p,key,x=None,y=None,transition='travel'):
  """Low-level actor relocation; normal gameplay uses relocate_saved."""
  p.state.update(self.relocation_state(p,key,x,y));p.state['revision']+=1;self.follower_anchor(p);p.last_encounter=time.monotonic();self.send_map(p,transition)
 async def relocate_saved(self,p,key,x=None,y=None,transition='travel',*,surf=None,clear_returns=False):
  """Persist the destination before publishing its map to this client."""
  candidate=self.relocation_state(p,key,x,y,surf=surf)
  if clear_returns:candidate['warpReturns']=[]
  await self.commit(p,candidate)
  self.follower_anchor(p);p.last_encounter=time.monotonic();self.send_map(p,transition)
 async def move(self,p,d):
  seq=integer(d.get('seq'),0,2**31-1,'Movement sequence');direction=d.get('direction');require(direction in DIRECTIONS,'Invalid movement direction.')
  if seq<=p.last_seq:p.send('move',seq=seq,accepted=False,reason='stale',entity=p.entity());return
  p.last_seq=seq;now=time.monotonic()
  if p.battle or p.trade or not p.move_bucket.take() or now-p.last_move<(self.s.step_ms-5)/1000:p.send('move',seq=seq,accepted=False,reason='busy' if p.battle or p.trade else 'rate',entity=p.entity());return
  p.last_move=now;s=p.state;m=self.c.maps[s['map']];dx,dy,conndir=DIRECTIONS[direction];previous={k:s[k] for k in ('map','x','y','revision')};previous['direction']=s.get('direction','down');previous_follower=(p.fx,p.fy);s['direction']=direction;s['revision']+=1;x,y=s['x']+dx,s['y']+dy;oldx,oldy=s['x'],s['y'];changed=False;accepted=False;movement='step'
  async def cross_map(key,tx,ty,transition):
   try:await self.relocate_saved(p,key,tx,ty,transition)
   except RequestError:
    p.state.update(previous);p.fx,p.fy=previous_follower;p.send('move',seq=seq,accepted=False,reason='save_failed',entity=p.entity());raise
  if not(0<=x<m['width'] and 0<=y<m['height']):
   for conn in m['connections']:
    if conn['direction']!=conndir or conn['target'] not in self.c.maps:continue
    target=self.c.maps[conn['target']]
    if conndir==1:tx,ty=x-conn['offset'],0
    elif conndir==2:tx,ty=x-conn['offset'],target['height']-1
    elif conndir==3:tx,ty=target['width']-1,y-conn['offset']
    else:tx,ty=0,y-conn['offset']
    if self.walkable(target,tx,ty,s.get('surf',False),state=s):
     await cross_map(target['id'],tx,ty,'connection');changed=True;accepted=True;movement='connection';break
  else:
   behavior=m['behavior'][y*m['width']+x];ledges={'right':56,'left':57,'up':58,'down':59}
   if behavior==ledges[direction]:x+=dx;y+=dy;movement='jump'
   portal=plan_warp(self.c,s,m,x,y,direction)
   if portal and 'blocked' in portal:p.send('notice',message=portal['blocked'])
   elif portal:
    candidate=self.relocation_state(p,portal['map'],portal['x'],portal['y']);candidate['warpReturns']=portal['warpReturns']
    try:await self.commit(p,candidate)
    except RequestError:
     p.state.update(previous);p.fx,p.fy=previous_follower;p.send('move',seq=seq,accepted=False,reason='save_failed',entity=p.entity());raise
    self.follower_anchor(p);p.last_encounter=time.monotonic();self.send_map(p,'warp');changed=True;accepted=True;movement='warp'
   else:
    source_elev=m['elevation'][oldy*m['width']+oldx]
    if self.walkable(m,x,y,s.get('surf',False),None if behavior in (56,57,58,59) else source_elev,state=s):s['x']=x;s['y']=y;p.fx=oldx;p.fy=oldy;accepted=True
  s=p.state;current=self.c.maps[s['map']];terrain=current['behavior'][s['y']*current['width']+s['x']]
  p.send('move',seq=seq,accepted=accepted,reason=None if accepted else 'blocked',movement=movement if accepted else None,terrain=terrain,pcAvailable=self.adventure.pc_available(p.state),entity=p.entity())
  if accepted and not changed:
   self.emit('move',player=p)
   m=self.c.maps[s['map']];j=s['y']*m['width']+s['x'];beh=m['behavior'][j]
   if self.adventure.wild_allowed(s) and now-p.last_encounter>3 and encounter_slots(m,s) and self.c.rng.random()<self.s.encounter_chance:await self.start_wild(p)
 async def start_wild(self,p,forced=None):
  self.free(p);require(any(m['hp']>0 for m in self.party(p)),'Your party needs healing.');m=self.c.maps[p.state['map']];j=p.state['y']*m['width']+p.state['x'];beh=m['behavior'][j]
  if forced is None:
   require(self.adventure.wild_allowed(p.state),'Wild encounters are unavailable inside Pokemon Centers and Gyms.')
   slots=encounter_slots(m,p.state)
   require(bool(slots),'No wild encounters here. Try the grass, a cave floor, or an eligible Surf area on this map.')
   key,level=select_encounter(slots,self.c.rng)
  else:key,level=forced # Internal test/extension hook only; never accepted from a client packet.
  enemy=self.c.new_mon(key,level,variety=self.c.varieties.roll(key));state=copy.deepcopy(p.state);self.adventure.observe(state,[key]);self.c.varieties.observe(state,[enemy]);await self.commit(p,state);b=Battle(self.c,'wild',[p.id,None],[p.username,'Wild '+self.c.varieties.display_name(enemy)],[self.party(p),[enemy]],[p.state['items'],{}],self.s.int('gameplay','battle_turn_seconds'),audio_source=m['id'].split('_',1)[0]);self.battles[b.id]=b;p.battle=b.id;p.last_encounter=time.monotonic();p.send('battle',battle=b.view(0))
 async def battle_action(self,p,d):
  require(p.battle in self.battles,'You are not in a battle.');b=self.battles[p.battle];require(d.get('id')==b.id,'That battle has ended.');side=b.players.index(p.id)
  if d.get('action')=='capture':require(len(p.state['creatures'])<self.s.max_owned,'Your collection is full. Make room before capturing.')
  b.choose(side,d)
  if len(b.choice)==2:await self.resolve_battle(b)
  else:p.send('battle',battle=b.view(side))
 async def resolve_battle(self,b):
  b.resolve();records=[];newstates={};audio_committed=True
  if b.kind!='duel':
   p=self.players.get(b.players[0])
   if p:
    state=copy.deepcopy(p.state);byid={m['uid']:m for m in b.rosters[0]};state['creatures']=[copy.deepcopy(byid.get(m['uid'],m)) for m in state['creatures']];state['items']=copy.deepcopy(b.items[0])
    trainer=getattr(b,'adventure_trainer',None);rematch=bool(trainer and trainer['id'] in state['adventure']['trainers'])
    if b.caught:
     require(len(state['creatures'])<self.s.max_owned,'Your collection is full.');state['creatures'].append(copy.deepcopy(b.caught))
     if len(state['party'])<6:state['party'].append(b.caught['uid'])
    if not rematch:
     for event in getattr(b,'experience_events',[]):
      participants=[m for m in state['creatures'] if m['uid'] in event['participants'] and m['uid'] in state['party'] and m['hp']>0]
      if not participants:continue
      total=max(1,self.c.species[event['species']]['baseExperience']*event['level']*(3 if b.kind=='trainer' else 2)//14);exp=max(1,total//len(participants))
      for mon in participants:
       gained=self.c.gain_xp(mon,exp);b.logs.append(f'{self.c.species[mon["species"]]["name"]} gained {exp} EXP.'+(f' Level {mon["level"]}!' if gained else ''));b.audio('experience',0,species=mon['species'],amount=exp)
       if gained:b.audio('level_up',0,species=mon['species'],level=mon['level'],gained=gained)
    if b.ended and b.winner==0 and not b.rewarded:
     if trainer:
      previous_unlocks=set(state['adventure']['unlocks']);first=self.adventure.victory(state,trainer)
      for unlocked in set(state['adventure']['unlocks'])-previous_unlocks:
       if unlocked in ('cut_kanto','cut_johto'):b.logs.append('Cut unlocked for '+unlocked[4:].title()+'! Click a small HM tree to clear your own path.')
      b.logs.append('First victory recorded. Your reward and badge progress were saved.' if first else 'Rematch complete. First-victory rewards and EXP are not awarded again.')
     elif not b.caught:state['money']=min(2_000_000_000,state['money']+(120 if b.kind=='trainer' else 25))
     b.rewarded=True
    self.adventure.observe(state,[m['species'] for m in state['creatures']],caught=True);self.c.varieties.observe(state,state['creatures'],caught=True)
    if b.ended and b.winner==1:
     for mon in state['creatures']:
      if mon['uid'] in state['party']:self.c.heal(mon)
     key=state['adventure'].get('lastCenter');returns=return_stack(self.c,{'warpReturns':state['adventure'].get('lastCenterReturns',[])})
     if key not in self.c.data.get('centers',{}):key=None
     if key and any(w.get('access',{}).get('dynamic') for w in self.c.maps[key]['warps']) and not any(e['inside']==key for e in returns):key=None
     if key is None:key=self.c.data['homes'][state['home']];returns=[];point=self.c.maps[key]['spawn']
     else:point=state['adventure'].get('lastCenterPosition') or self.c.data['centers'][key]['respawn']
     if not isinstance(point,(list,tuple)) or len(point)!=2 or not all(type(v) is int for v in point) or not self.walkable(self.c.maps[key],*point,state=state):point=self.c.data.get('centers',{}).get(key,{}).get('respawn',self.c.maps[key]['spawn'])
     state.update(map=key,x=point[0],y=point[1],surf=False,warpReturns=returns);self.adventure.visit(state,key);b.logs.append('Your party was restored at your last Pokemon Center, or your home hub if you have not visited one.')
    state['revision']=p.state['revision']+1;records.append((p.id,state));newstates[p.id]=state
   try:await asyncio.to_thread(self.db.save_many,records)
   except Exception:
    log.exception('Battle transaction failed; aborting without applying this turn')
    b.ended=True;b.winner=None;b.caught=None;b.logs=['Database save failed. This turn was not applied. The battle has been safely closed.'];newstates={};audio_committed=False;b.reset_audio();b.audio('abort',reason='save_failed')
  if b.ended and audio_committed:b.audio('battle_end')
  for side,pid in enumerate(b.players):
   p=self.players.get(pid)
   if not p:continue
   if pid in newstates:
    oldmap=p.state['map'];p.state=newstates[pid];p.saved_revision=p.state['revision'];b.rosters[side]=copy.deepcopy(self.party(p));self.send_state(p)
    if p.state['map']!=oldmap:p.fx=p.state['x'];p.fy=p.state['y'];self.send_map(p,transition='rescue')
   p.send('battle',battle=b.view(side))
   if b.ended:p.battle=None;p.last_encounter=time.monotonic()
  if b.ended:self.battles.pop(b.id,None);self.emit('battle_end',battle=b)
 async def invite(self,p,d):
  self.free(p);kind=d.get('kind');require(kind in ('trade','challenge'),'Unknown invitation.');q=self.require_peer(p,d.get('target'));self.free(q)
  require(not any(p.id in (v['from'],v['to']) or q.id in (v['from'],v['to']) for v in self.invites.values()),'One trainer already has a pending invitation.')
  key=str(uuid.uuid4());inv={'id':key,'kind':kind,'from':p.id,'to':q.id,'expires':time.monotonic()+self.s.int('gameplay','invite_timeout_seconds')};self.invites[key]=inv
  q.send('invite',id=key,kind=kind,trainer=p.username,fromId=p.id,seconds=self.s.int('gameplay','invite_timeout_seconds'));p.send('notice',message=f'{kind.title()} invitation sent to {q.username}.')
 async def answer_invite(self,p,d):
  key=d.get('id');inv=self.invites.get(key);require(inv is not None and inv['to']==p.id,'That invitation is no longer available.');self.invites.pop(key,None);q=self.players.get(inv['from']);require(q is not None,'The other trainer disconnected.')
  if d.get('accept') is not True:q.send('notice',message=f'{p.username} declined your invitation.');return
  require(inv['expires']>time.monotonic(),'That invitation expired.');self.free(p);self.free(q);require(self.nearby(p,q),'The trainers moved too far apart.')
  if inv['kind']=='challenge':
   require(all(any(m['hp']>0 for m in self.party(t)) for t in (q,p)),'Both trainers need at least one healthy Pokemon.')
   b=Battle(self.c,'duel',[q.id,p.id],[q.username,p.username],[self.party(q),self.party(p)],[{},{}],self.s.int('gameplay','battle_turn_seconds'),audio_source=p.state['map'].split('_',1)[0]);self.battles[b.id]=b;q.battle=b.id;p.battle=b.id;q.send('battle',battle=b.view(0));p.send('battle',battle=b.view(1))
  else:
   tid=str(uuid.uuid4());t={'id':tid,'players':[q.id,p.id],'offers':{q.id:{'pokemon':[],'items':{},'money':0},p.id:{'pokemon':[],'items':{},'money':0}},'ready':set(),'confirmed':set(),'revision':0,'deadline':time.monotonic()+self.s.int('gameplay','trade_timeout_seconds')};self.trades[tid]=t;q.trade=tid;p.trade=tid;self.send_trade(t)
 def trade_digest(self,t):return hashlib.sha256(json.dumps(t['offers'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
 def send_trade(self,t):
  digest=self.trade_digest(t)
  for pid in t['players']:
   p=self.players.get(pid)
   if not p:continue
   other=next(i for i in t['players'] if i!=pid);q=self.players.get(other)
   offers={}
   for owner in t['players']:
    player=self.players.get(owner)
    if player:
     o=copy.deepcopy(t['offers'][owner]);o['pokemon']=[self.c.public_mon(m,False) for m in player.state['creatures'] if m['uid'] in o['pokemon']];offers[str(owner)]=o
   p.send('trade',trade={'id':t['id'],'revision':t['revision'],'digest':digest,'you':pid,'other':other,'otherName':q.username if q else 'Disconnected','offers':offers,'ready':list(t['ready']),'confirmed':list(t['confirmed']),'seconds':max(0,int(t['deadline']-time.monotonic()))})
 def check_offer(self,p,offer):
  require(isinstance(offer,dict),'Invalid offer.');ids=offer.get('pokemon',[]);items=offer.get('items',{});money=integer(offer.get('money',0),0,2_000_000_000,'Money')
  require(isinstance(ids,list) and len(ids)<=6 and all(isinstance(i,str) for i in ids) and len(ids)==len(set(ids)),'Offer up to six distinct Pokemon.')
  owned={m['uid'] for m in p.state['creatures']};require(all(i in owned for i in ids),'You no longer own an offered Pokemon.');require(money<=p.state['money'],'You do not have that much money.');require(isinstance(items,dict) and len(items)<=len(self.c.items),'Invalid item offer.')
  clean={}
  for k,n in items.items():
   require(k in self.c.items,'Unknown trade item.');integer(n,0,999,'Item quantity');require(n<=p.state['items'].get(k,0),'You do not own that many items.')
   if n:clean[k]=n
  return {'pokemon':ids,'items':clean,'money':money}
 async def trade_action(self,p,d):
  require(p.trade in self.trades,'You are not in a trade.');t=self.trades[p.trade];require(d.get('id')==t['id'],'That trade has ended.');action=d.get('action')
  if action=='cancel':self.cancel_trade(t,'The exchange was cancelled. Nothing was transferred.');return
  require(d.get('revision')==t['revision'],'This offer changed. Review the current exchange before proceeding.')
  if action=='offer':
   t['offers'][p.id]=self.check_offer(p,d.get('offer'));t['revision']+=1;t['ready'].clear();t['confirmed'].clear()
  elif action=='lock':
   self.check_offer(p,t['offers'][p.id]);t['ready'].add(p.id)
  elif action=='confirm':
   require(len(t['ready'])==2 and d.get('digest')==self.trade_digest(t),'Both trainers must lock and review the same offer.');t['confirmed'].add(p.id)
   if len(t['confirmed'])==2:
    try:await self.commit_trade(t)
    except RequestError:
     t['confirmed'].clear();self.send_trade(t);raise
    return
  else:raise RequestError('Unknown trade action.')
  t['deadline']=time.monotonic()+self.s.int('gameplay','trade_timeout_seconds');self.send_trade(t)
 async def commit_trade(self,t):
  a,b=[self.players.get(pid) for pid in t['players']];require(a is not None and b is not None,'One trainer disconnected.');require(self.nearby(a,b),'The other trainer is too far away.')
  oa,ob=[self.check_offer(p,t['offers'][p.id]) for p in (a,b)];sa,sb=copy.deepcopy(a.state),copy.deepcopy(b.state)
  # Take both source snapshots BEFORE applying either side, so no object can duplicate.
  outgoing_a=[m for m in sa['creatures'] if m['uid'] in oa['pokemon']];outgoing_b=[m for m in sb['creatures'] if m['uid'] in ob['pokemon']]
  if hasattr(self.c,'growth'):
   for mon in outgoing_a+outgoing_b:self.c.growth.mark_trade(mon)
  for p,state,off,gain,incoming in [(a,sa,oa,ob,outgoing_b),(b,sb,ob,oa,outgoing_a)]:
   original_party=list(state['party']);state['creatures']=[m for m in state['creatures'] if m['uid'] not in off['pokemon']]+copy.deepcopy(incoming);state['party']=[i for i in original_party if i not in off['pokemon']]
   require(1<=len(state['creatures'])<=self.s.max_owned,'An exchange cannot leave a trainer with no Pokemon or exceed collection capacity.')
   vacancies=len(original_party)-len(state['party'])
   for mon in incoming[:vacancies]:state['party'].append(mon['uid'])
   require(bool(state['party']) and any(m['hp']>0 for m in state['creatures'] if m['uid'] in state['party']),'An exchange must leave each trainer with a healthy party Pokemon.')
   state['money']+=gain['money']-off['money'];require(state['money']<=2_000_000_000,'The recipient money balance would exceed the limit.')
   for item,n in off['items'].items():state['items'][item]=state['items'].get(item,0)-n
   for item,n in gain['items'].items():state['items'][item]=state['items'].get(item,0)+n;require(state['items'][item]<=999,'An item stack would exceed 999.')
   self.adventure.observe(state,[m['species'] for m in state['creatures']],caught=True);self.c.varieties.observe(state,state['creatures'],caught=True);state['revision']=p.state['revision']+1
  allids=[m['uid'] for s in (sa,sb) for m in s['creatures']];require(len(allids)==len(set(allids)),'Duplicate ownership detected; exchange blocked.')
  try:await asyncio.to_thread(self.db.trade,t['id'],a.id,sa,b.id,sb,{'offers':t['offers'],'digest':self.trade_digest(t)})
  except Exception as e:log.exception('Trade rolled back %s',t['id']);self.cancel_trade(t,'The database rejected the exchange. Neither side was changed.');return
  a.state=sa;b.state=sb;a.saved_revision=sa['revision'];b.saved_revision=sb['revision']
  for p in (a,b):p.trade=None;self.send_state(p);p.send('trade_done',id=t['id'],success=True,message='Exchange completed and saved for both trainers.');p.audio('trade_complete',trade=t['id'])
  self.trades.pop(t['id'],None);self.emit('trade_complete',trade=t);log.info('Committed trade %s between %d and %d',t['id'],a.id,b.id)
 def cancel_trade(self,t,message):
  for pid in t['players']:
   p=self.players.get(pid)
   if p:p.trade=None;p.send('trade_done',id=t['id'],success=False,message=message)
  self.trades.pop(t['id'],None)
 async def cut_tree(self,p,d,o):
  """Called only after npc identity/proximity/free-session checks under world lock."""
  m=self.c.maps[p.state['map']];key=m['id'];rule=CUT_REQUIREMENTS.get(region(key));action=d.get('action')
  require(rule is not None,'Cut is not supported in this region.')
  allowed=cut_allowed(p.state);cleared=tree_cleared(p.state,key,o)
  if action=='cut':
   require(d.get('map')==key,'That tree menu belongs to another map. Click the tree again.')
   require(allowed,'Cut is locked here. Defeat '+rule['leader']+' for the '+rule['badgeName']+'.')
   if not cleared:
    state=copy.deepcopy(p.state);cuts=state['adventure'].setdefault('cutTrees',{}).setdefault(key,[]);cuts.append(o['id']);cuts.sort()
    await self.commit(p,state)
   p.send('dialog',title='Path cleared',message='You used Cut. This tree is cleared and saved for your character only; other trainers must cut their own tree.',actions=[],npc=o['id'],map=key)
   return
  require(action in (None,'talk'),'This tree only supports Cut.')
  message=('This tree is already cleared for your character.' if cleared else
   'This small tree can be cut. Use Cut to clear this path for your character.' if allowed else
   'Cut is locked in '+region(key).title()+'. Defeat '+rule['leader']+' in '+rule['city']+' and earn the '+rule['badgeName']+' to unlock it automatically.')
  p.send('dialog',title='Small HM tree',message=message,actions=['cut'],disabledActions=[] if allowed and not cleared else ['cut'],npc=o['id'],map=key,fieldMove={'move':'Cut','unlocked':allowed,'cleared':cleared,**rule})
 async def npc(self,p,d):
  self.free(p);m=self.c.maps[p.state['map']];nid=integer(d.get('npc'),0,255,'NPC ID');o=next((o for o in m['objects'] if o['id']==nid),None);require(o is not None,'That NPC is not available.');action=d.get('action')
  require(max(abs(p.state['x']-o['x']),abs(p.state['y']-o['y']))<=2,'Move closer to speak to this character.')
  require(d.get('map',m['id'])==m['id'],'That interaction belongs to another map. Click the object again.')
  if is_cut_tree(o):await self.cut_tree(p,d,o);return
  center=self.c.data.get('centers',{}).get(m['id'],{});trainer=self.adventure.by_npc.get((m['id'],nid))
  if nid in center.get('nurseNpcIds',[]):
   if action=='heal':await self.heal(p,npc=nid);return
   require(action in (None,'talk','pc'),'Choose a Pokemon Center service.');actions=['heal']
   if self.adventure.pc_available(p.state):actions.append('pc')
   p.send('dialog',title='Nurse Joy',message='Welcome to the Pokemon Center! May I restore your Pokemon to full health? You can also manage your party and storage here.',actions=actions,npc=nid);return
  if nid in center.get('pcNpcIds',[]):
   require(action in (None,'talk','pc'),'Choose the storage service.');p.send('dialog',title='Pokemon Storage PC',message='Deposit and withdraw your Pokemon. Keep one healthy partner with you.',actions=['pc'],npc=nid);return
  if trainer:
   if action=='battle':
    self.adventure.can_challenge(p.state,trainer);require(any(mon['hp']>0 for mon in self.party(p)),'Your party needs healing.');team=[]
    for member in trainer['team']:
     enemy=self.c.new_mon(member['species'],member['level'],trainer['name'],variety='normal');iv=max(0,min(255,int(member.get('iv',0))))*31//255;enemy.update(ivs=[iv]*6,nature=0,shiny=False);self.c.heal(enemy);moves=[mid for mid in member.get('moves',[]) if str(mid) in self.c.moves]
     if moves:enemy['moves']=[{'id':mid,'pp':self.c.moves[str(mid)]['pp']} for mid in moves[:4]]
     team.append(enemy)
    require(bool(team),'This trainer team is unavailable.');state=copy.deepcopy(p.state);self.adventure.observe(state,[mon['species'] for mon in team]);self.c.varieties.observe(state,team);await self.commit(p,state)
    b=Battle(self.c,'trainer',[p.id,None],[p.username,trainer['name']],[self.party(p),team],[p.state['items'],{}],self.s.int('gameplay','battle_turn_seconds'),audio_source=m['id'].split('_',1)[0]);b.adventure_trainer=trainer;self.battles[b.id]=b;p.battle=b.id;p.send('battle',battle=b.view(0));return
   require(action in (None,'talk'),'Choose a trainer interaction.');defeated=trainer['id'] in p.state['adventure']['trainers'];gym=self.adventure.gym(trainer);summary=', '.join(f'{self.c.species[t["species"]]["name"]} Lv. {t["level"]}' for t in trainer['team']);message=('Gym challenge. ' if gym else 'Trainer challenge. ')+summary+(' Rematch: no repeat EXP, money or badge rewards.' if defeated else 'Your first victory earns a permanent record and a reward.');p.send('dialog',title=trainer['name'],message=message,actions=['battle'],npc=nid);return
  require(action in (None,'talk'),'This character does not offer that service.')
  if o['graphics']==68:p.send('dialog',title='Poke Mart',message='Welcome! Purchase supplies for your adventure from the Bag panel.',actions=['shop'],npc=nid)
  else:p.send('dialog',title=m['name'],message='Explore the region, discover Pokemon, and challenge local trainers. Your Adventure Journal tracks your next goals. Original story scripts are not executed by this MMO.',actions=[],npc=nid)
 async def heal(self,p,npc=None):
  self.free(p);self.adventure.require_nurse(p.state,npc);s=copy.deepcopy(p.state)
  for mon in s['creatures']:
   if mon['uid'] in s['party']:self.c.heal(mon)
  s['adventure']['lastCenter']=s['map'];s['adventure']['lastCenterReturns']=return_stack(self.c,s);s['adventure']['lastCenterPosition']=self.c.data['centers'][s['map']].get('respawnByNpc',{}).get(str(npc),self.c.data['centers'][s['map']].get('respawn',self.c.maps[s['map']]['spawn']));await self.commit(p,s);p.send('dialog',title='Nurse Joy',message='Your party is fully restored. We hope to see you again!',actions=['pc'] if self.adventure.pc_available(s) else [],npc=npc);p.audio('heal',atNurse=True)
 async def dispatch(self,p,d):
  async with self.lock:
   require(not p.closed and self.players.get(p.id) is p,'Your session is closed.');require(p.command_bucket.take(),'Too many commands; please slow down.');op=d.get('op')
   if op=='move':await self.move(p,d)
   elif op=='chat':
    require(p.chat_bucket.take(),'Chat rate limit: please wait a moment.');require(time.monotonic()>=p.muted_until,'You are muted by the world administrator.');channel=d.get('channel');message=d.get('text');require(channel in self.chat,'Choose General or Trade.');require(isinstance(message,str) and 1<=len(message.strip())<=240 and all(ord(x)>=32 for x in message),'Messages must be 1-240 characters on one line.')
    msg={'username':p.username,'playerId':p.id,'text':message.strip(),'time':int(time.time())};self.chat[channel].append(msg)
    for q in self.players.values():q.send('chat',channel=channel,**msg)
   elif op=='invite':await self.invite(p,d)
   elif op=='invite.answer':await self.answer_invite(p,d)
   elif op=='trade':await self.trade_action(p,d)
   elif op=='battle':await self.battle_action(p,d)
   elif op=='encounter':await self.start_wild(p)
   elif op=='npc':await self.npc(p,d)
   elif op=='heal':raise RequestError('Speak to Nurse Joy at a Pokemon Center to heal your party.')
   elif op=='journal.claim':
    self.free(p);await self.commit(p,self.adventure.claim(p.state,d.get('id')));p.send('notice',message='Objective reward received and saved.');p.audio('purchase')
   elif op=='pc':
    self.free(p);old=p.state['party'][0];await self.commit(p,self.adventure.pc(p.state,d.get('action'),d.get('uid')));p.audio('party_changed',species=self.party(p)[0]['species'],leadChanged=old!=p.state['party'][0])
   elif op in ('pokemon.learn','pokemon.remember','pokemon.evolve','pokemon.evolution.defer','pokemon.evolution.resume'):
    self.free(p);growth=self.c.growth;uid=d.get('uid')
    if op=='pokemon.learn':state=growth.learn(p.state,uid,d.get('move'),d.get('slot'))
    elif op=='pokemon.remember':state=growth.remember(p.state,uid,d.get('move'),d.get('slot'))
    elif op=='pokemon.evolve':state=growth.evolve(p.state,uid,d.get('target'))
    elif op=='pokemon.evolution.defer':state=growth.defer_evolution(p.state,uid,d.get('target'))
    else:state=growth.resume_evolution(p.state,uid,d.get('target'))
    await self.commit(p,state);p.send('notice',message='Pokemon update saved.');p.audio('level_up' if op=='pokemon.evolve' else 'party_changed')
   elif op=='party':
    self.free(p);ids=d.get('party');require(isinstance(ids,list) and 1<=len(ids)<=6 and all(isinstance(i,str) for i in ids) and len(ids)==len(set(ids)),'A party must contain 1-6 distinct Pokemon.');require(all(i in {m['uid'] for m in p.state['creatures']} for i in ids),'That Pokemon is not yours.');old_party=list(p.state['party']);require(set(ids)==set(old_party) or self.adventure.pc_available(p.state),'Visit a Pokemon Center PC to deposit or withdraw Pokemon.');require(any(m['hp']>0 for m in p.state['creatures'] if m['uid'] in ids),'Keep at least one healthy Pokemon in your party.');s=copy.deepcopy(p.state);s['party']=list(ids);await self.commit(p,s)
    if ids!=old_party:p.audio('party_changed',species=self.party(p)[0]['species'],leadChanged=ids[0]!=old_party[0])
   elif op=='buy':
    self.free(p);require(self.s.flag('world','allow_alpha_atlas') or any(o['graphics']==68 and max(abs(p.state['x']-o['x']),abs(p.state['y']-o['y']))<=2 for o in self.c.maps[p.state['map']]['objects']),'Visit a Poke Mart.');item=d.get('item');require(item in self.c.items,'Unknown item.');count=integer(d.get('quantity'),1,99,'Quantity');cost=self.c.items[item]['price']*count;require(p.state['money']>=cost,'You do not have enough money.');require(p.state['items'].get(item,0)+count<=999,'This stack would exceed 999.');s=copy.deepcopy(p.state);s['money']-=cost;s['items'][item]=s['items'].get(item,0)+count;await self.commit(p,s);p.audio('purchase',item=item,quantity=count)
   elif op=='use':
    self.free(p);item=d.get('item');uid=d.get('uid');require(item in self.c.items and 'heal' in self.c.items[item],'Select a healing item.');require(p.state['items'].get(item,0)>0,'You have none of that item.');s=copy.deepcopy(p.state);mon=next((m for m in s['creatures'] if m['uid']==uid),None);require(mon is not None and 0<mon['hp']<self.c.stats(mon)[0],'Select an injured, non-fainted Pokemon.');mon['hp']=min(self.c.stats(mon)[0],mon['hp']+self.c.items[item]['heal']);s['items'][item]-=1;await self.commit(p,s);p.audio('item',item=item,species=mon['species'])
   elif op=='travel':
    self.free(p);dest=d.get('map');require(isinstance(dest,str) and dest in self.c.maps,'Unknown destination.');
    if not self.s.flag('world','allow_alpha_atlas'):self.adventure.can_travel(p.state,dest)
    await self.relocate_saved(p,dest,surf=False,clear_returns=True)
   elif op=='surf':
    self.free(p);require(p.state.get('surf',False) or self.s.flag('world','allow_alpha_surf') or self.adventure.surf_allowed(p.state),'Earn the regional Surf badge before entering water.');require(not p.state.get('surf',False) or self.c.maps[p.state['map']]['behavior'][p.state['y']*self.c.maps[p.state['map']]['width']+p.state['x']] not in WATER,'Step onto land before disabling Surf.');s=copy.deepcopy(p.state);s['surf']=not s.get('surf',False);await self.commit(p,s);p.send('notice',message='Surf '+('enabled. Water tiles are now accessible.' if p.state['surf'] else 'disabled.'));p.audio('surf',enabled=p.state['surf'])
   elif op=='unstuck':
    self.free(p);await self.relocate_saved(p,self.c.data['homes'][p.state['home']],transition='home',surf=False,clear_returns=True);p.send('notice',message='Returned safely to your home hub.')
   elif op=='ping':p.send('pong',nonce=d.get('nonce') if isinstance(d.get('nonce'),(int,float)) else 0)
   elif op=='save':await asyncio.to_thread(self.db.save_many,[(p.id,copy.deepcopy(p.state))]);p.saved_revision=p.state['revision'];p.send('notice',message='Character saved.');p.audio('save')
   else:raise RequestError('Unknown command.')
 async def leave(self,p):
  async with self.lock:
   if self.players.get(p.id) is not p:return
   if p.trade in self.trades:self.cancel_trade(self.trades[p.trade],'A trainer disconnected. The uncommitted exchange was cancelled.')
   if p.battle in self.battles:
    b=self.battles.pop(p.battle)
    for side,pid in enumerate(b.players):
     other=self.players.get(pid)
     if other and other.id!=p.id:b.ended=True;b.winner=side;b.logs=['The other trainer disconnected. The duel is over.'];b.reset_audio();b.audio('battle_end',reason='peer_disconnected');other.battle=None;other.send('battle',battle=b.view(side))
    p.battle=None
   for key,v in list(self.invites.items()):
    if p.id in (v['from'],v['to']):
     peer=self.players.get(v['to'] if p.id==v['from'] else v['from'])
     if peer:peer.send('invite_expired',id=key)
     self.invites.pop(key,None)
   try:await asyncio.to_thread(self.db.save_many,[(p.id,copy.deepcopy(p.state))])
   except Exception:log.exception('Logout save failed for %s; last committed state remains in DB',p.username)
   self.players.pop(p.id,None);p.closed=True;self.emit('logout',player=p);log.info('Left %s; online=%d',p.username,len(self.players))
 async def tick(self):
  begin=time.monotonic()
  async with self.lock:
   now=time.monotonic()
   for key,v in list(self.invites.items()):
    if v['expires']<now:
     for pid in (v['from'],v['to']):
      if pid in self.players:self.players[pid].send('invite_expired',id=key)
     self.invites.pop(key,None)
   for t in list(self.trades.values()):
    if t['deadline']<now:self.cancel_trade(t,'The trade timed out. Nothing was transferred.')
   for b in list(self.battles.values()):
    if b.timeout():await self.resolve_battle(b)
   buckets=collections.defaultdict(list)
   for q in self.players.values():
    s=q.state;buckets[(s['map'],s['x']//8,s['y']//8)].append(q)
   r=self.s.interest_radius;cell=math.ceil(r/8)
   for p in self.players.values():
    if p.closed:continue
    s=p.state;seen={};changed=[]
    for cy in range(s['y']//8-cell,s['y']//8+cell+1):
     for cx in range(s['x']//8-cell,s['x']//8+cell+1):
      for q in buckets.get((s['map'],cx,cy),()):
       if q.closed or not self.nearby(p,q,r):continue
       e=q.entity();signature=tuple(e.values());seen[q.id]=signature
       if p.seen.get(q.id)!=signature:changed.append(e)
    gone=[i for i in p.seen if i not in seen]
    if changed or gone or self.ticks%self.s.tick_hz==0:p.send('scene',map=s['map'],players=changed,gone=gone,online=len(self.players))
    p.seen=seen
   self.ticks+=1
  self.last_tick_ms=(time.monotonic()-begin)*1000;self.max_tick_ms=max(self.max_tick_ms,self.last_tick_ms)
 async def save_all(self):
  async with self.lock:
   sessions={p.id:p for p in self.players.values() if p.state['revision']>p.saved_revision}
   records=[(uid,copy.deepcopy(p.state)) for uid,p in sessions.items()]
  await asyncio.to_thread(self.db.save_many,records)
  async with self.lock:
   for uid,state in records:
    if self.players.get(uid) is sessions[uid]:sessions[uid].saved_revision=max(sessions[uid].saved_revision,state['revision'])
  return len(records)
