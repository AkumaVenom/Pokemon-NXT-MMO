"""Account-owned adventure progression. Commands transform detached save snapshots.

ROM trainer identity/teams live in the hashed content pack; reward and objective
rules are explicitly authored MMO rules. No command accepts a client state blob.
"""
from __future__ import annotations
import copy,time
from .security import require
from .field_moves import migrate_cuts,public_field_moves
from .story_events import migrate as migrate_story,public as public_story_events,refresh_rewards as refresh_story_rewards

class Adventure:
 def __init__(self,content):
  self.c=content;self.rules=content.data.get('adventure',{});rom=content.data.get('adventureRom',{})
  self.trainers=rom.get('trainers',{});self.gyms=sorted(rom.get('gyms',[]),key=lambda g:(g['region'],g['order']))
  self.by_npc={(t['map'],t['npc']):t for t in self.trainers.values()}
  self.gym_by_npc={(g['map'],g['npc']):g for g in self.gyms if g.get('map') is not None and g.get('npc') is not None}
 def region(self,value):return str(value).split('_',1)[0].lower()
 def badge_id(self,g):return f'{self.region(g["region"])}_{g["order"]}'
 def migrate(self,state):
  state=copy.deepcopy(state);a=state.setdefault('adventure',{})
  defaults={'format':1,'trainers':{},'badges':[],'claimed':[],'seen':[],'caught':[],'visited':[],'unlocks':[],'lastCenter':None}
  for k,v in defaults.items():a.setdefault(k,copy.deepcopy(v))
  require(a.get('format')==1,'This adventure save needs a newer server.')
  self.observe(state,[m['species'] for m in state['creatures']],caught=True)
  self.visit(state,state['map']);self.refresh_unlocks(state);migrate_cuts(state,self.c.maps);migrate_story(state,self.c);return state
 def observe(self,state,species,caught=False):
  a=state['adventure']
  for key in species:
   if key not in self.c.species:continue
   if key not in a['seen']:a['seen'].append(key)
   if caught and key not in a['caught']:a['caught'].append(key)
 def visit(self,state,key):
  if key not in state['adventure']['visited']:state['adventure']['visited'].append(key)
 def nearby_service(self,state,kind):
  m=self.c.maps[state['map']];center=self.c.data.get('centers',{}).get(m['id'],{})
  ids=list(center.get('nurseNpcIds',[])) if kind=='nurse' else list(center.get('pcNpcIds',[]))
  if kind=='pc' and center.get('nursePcAccess'):ids+=center.get('nurseNpcIds',[])
  return [o for o in m['objects'] if o['id'] in ids and max(abs(o['x']-state['x']),abs(o['y']-state['y']))<=2]
 def require_nurse(self,state,npc):require(any(o['id']==npc for o in self.nearby_service(state,'nurse')),'Speak to Nurse Joy at the nearby Pokemon Center counter.')
 def pc_available(self,state):return bool(self.nearby_service(state,'pc'))
 def gym(self,trainer):return self.gym_by_npc.get((trainer['map'],trainer['npc']))
 def can_challenge(self,state,trainer):
  a=state['adventure'];gym=self.gym(trainer)
  if gym:
   previous=[self.badge_id(g) for g in self.gyms if self.region(g['region'])==self.region(gym['region']) and g['order']<gym['order']]
   require(all(key in a['badges'] for key in previous),'Earn the earlier badges in this region before challenging this Gym Leader.')
  record=a['trainers'].get(trainer['id'],{})
  require(time.time()>=record.get('lastWin',0)+60,'This trainer is resting. Rematches are available one minute after victory.')
 def trainer_reward(self,trainer):return max(100,sum(e['level'] for e in trainer['team'])*20)
 def victory(self,state,trainer):
  a=state['adventure'];previous=a['trainers'].get(trainer['id'],{});first=not previous
  a['trainers'][trainer['id']]={'wins':previous.get('wins',0)+1,'lastWin':int(time.time())}
  if first:state['money']=min(2_000_000_000,state['money']+self.trainer_reward(trainer))
  g=self.gym(trainer)
  if g:
   badge=self.badge_id(g)
   if badge not in a['badges']:a['badges'].append(badge)
  self.refresh_unlocks(state);return first
 def refresh_unlocks(self,state):
  a=state['adventure']
  for rule in self.rules.get('unlocks',[]):
   if all(b in a['badges'] for b in rule.get('badges',[])) and len(a['badges'])>=rule.get('badgeCount',0) and rule['id'] not in a['unlocks']:a['unlocks'].append(rule['id'])
  refresh_story_rewards(state,self.c)
 def goal_current(self,state,goal):
  a=state['adventure'];metric=goal['metric']
  if metric=='caught':return len(a['caught'])
  if metric=='seen':return len(a['seen'])
  if metric=='visited':return len(a['visited'])
  if metric=='trainers':return len(a['trainers'])
  if metric=='badges':return sum(1 for b in a['badges'] if not goal.get('region') or b.startswith(goal['region']+'_'))
  return 0
 def claim(self,state,key):
  goal=next((g for g in self.rules.get('goals',[]) if g['id']==key),None);require(goal is not None,'That journal objective is unavailable.');a=state['adventure'];require(key not in a['claimed'],'This objective reward has already been claimed.');require(self.goal_current(state,goal)>=goal['target'],'Finish this objective before claiming its reward.')
  state=copy.deepcopy(state);reward=goal.get('reward',{});money=reward.get('money',0);require(state['money']+money<=2_000_000_000,'Spend some money before claiming this reward.')
  for item,n in reward.get('items',{}).items():require(item in self.c.items and state['items'].get(item,0)+n<=999,'Make room in your Bag before claiming this reward.')
  state['money']+=money
  for item,n in reward.get('items',{}).items():state['items'][item]=state['items'].get(item,0)+n
  state['adventure']['claimed'].append(key);return state
 def pc(self,state,action,uid):
  require(self.pc_available(state),'Use the PC service at a nearby Pokemon Center.');require(isinstance(uid,str) and any(m['uid']==uid for m in state['creatures']),'That Pokemon is not yours.');state=copy.deepcopy(state);party=state['party']
  if action=='deposit':
   require(uid in party,'That Pokemon is already in storage.');remaining=[m for m in state['creatures'] if m['uid'] in party and m['uid']!=uid];require(remaining and any(m['hp']>0 for m in remaining),'Keep at least one healthy Pokemon in your party.');party.remove(uid)
  elif action=='withdraw':require(uid not in party,'That Pokemon is already in your party.');require(len(party)<6,'Your party is full. Deposit a Pokemon first.');party.append(uid)
  else:require(False,'Choose deposit or withdraw.')
  return state
 def can_travel(self,state,destination):
  a=state['adventure'];require('travel_pass' in a['unlocks'],'Earn two badges to unlock travel between discovered waypoints.');require(self.c.maps[destination].get('mapType') in (1,2,3),'Waypoints are outdoors. Enter this building through its door.');require(destination in a['visited'] or destination in self.c.data['homes'].values(),'Visit that location on foot before using it as a waypoint.')
 def wild_allowed(self,state):
  return state['map'] not in self.c.data.get('centers',{}) and not any(g['map']==state['map'] for g in self.gyms)
 def surf_allowed(self,state):return 'surf_'+self.region(state['map']) in state['adventure']['unlocks']
 def public(self,state):
  a=state['adventure'];regions=[]
  labels=self.rules.get('badgeNames',{})
  for region,name in (('kanto','Kanto / FireRed'),('johto','Johto / Crystal encounters')):
   badges=[{'id':self.badge_id(g),'name':labels.get(self.badge_id(g),f'Badge {g["order"]}'),'leader':g['name'],'earned':self.badge_id(g) in a['badges'],'order':g['order'],'map':g['map']} for g in self.gyms if self.region(g['region'])==region]
   regions.append({'id':region,'name':name,'badges':badges,'nextGym':next((b for b in badges if not b['earned']),None)})
  goals=[]
  for goal in self.rules.get('goals',[]):
   current=self.goal_current(state,goal);goals.append({'id':goal['id'],'title':goal['title'],'description':goal['description'],'current':min(current,goal['target']),'target':goal['target'],'complete':current>=goal['target'],'claimed':goal['id'] in a['claimed'],'reward':goal.get('reward',{})})
  return {'fieldMoves':public_field_moves(state),'cutTrees':copy.deepcopy(a.get('cutTrees',{})),'storyEvents':list(a.get('storyEvents',[])),'story':public_story_events(state,self.c),'regions':regions,'goals':goals,'trainers':{'defeated':sorted(a['trainers']),'count':len(a['trainers'])},'dex':{'seen':sorted(a['seen']),'caught':sorted(a['caught']),'varieties':copy.deepcopy(a.get('varietyDex',{'seen':{},'caught':{}}))},'visited':list(a['visited']),'unlocks':list(a['unlocks']),'pcAvailable':self.pc_available(state),'stored':len(state['creatures'])-len(state['party'])}
