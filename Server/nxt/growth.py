"""Durable owner-scoped move choices and validated ROM evolution rules.

Every player action returns a detached state. The world owns locking and commits;
this module never writes a database, trusts a client species, or awards experience.
"""
from __future__ import annotations
import copy
from .security import require, integer

SUPPORTED_EVOLUTIONS=frozenset(('level','stone','trade'))
MOVE_NAMESPACE_VERSION=1

class Growth:
 def __init__(self,content):self.c=content
 def ensure(self,mon):
  """Add fields to a detached/new creature, preserving all existing progression."""
  for key in ('pendingLearn','pendingEvolution','evolutionDeferred','evolutionHistory'):mon.setdefault(key,[])
  return mon
 def migrate(self,state):
  candidate=copy.deepcopy(state)
  for mon in candidate['creatures']:
   self.ensure(mon);self.migrate_move_namespace(mon);known={m['id'] for m in mon['moves']};seen=set();pending=[]
   # Corrected content can invalidate an old queued row. Do not leave that row
   # blocking every later choice, and never rebuild the owner's chosen moves.
   for entry in mon['pendingLearn'] if isinstance(mon['pendingLearn'],list) else []:
    if not self.earned_entry(mon,entry):continue
    move=entry['move']
    if move in known or move in seen:continue
    pending.append(entry);seen.add(move)
   mon['pendingLearn']=pending
  return candidate
 def stamp_move_namespace(self,mon):
  mon['moveNamespaceVersion']=MOVE_NAMESPACE_VERSION
  return mon
 def native_move_alias(self,species,move,maximum,exact_level=None):
  """Require native source evidence before reinterpreting a legacy numeric ID."""
  if not isinstance(species,str) or species not in self.c.species or type(move) is not int:return None
  profile=self.c.species[species]
  if profile.get('source')!='johto':return None
  alias=self.c.data.get('learnsets',{}).get('moveIdAliases',{}).get('johto',{}).get(str(move))
  definition=self.c.moves.get(str(alias))
  if type(alias) is not int or not 1<=alias<=65535 or not definition or definition.get('source')!='johto' or definition.get('sourceMoveId')!=move:return None
  for level,raw in profile.get('learnsetProvenance',{}).get('rawLearnset',[]):
   if type(level) is int and 1<=level<=maximum and raw==move and (exact_level is None or level==exact_level) and [level,alias] in profile['learnset']:return alias
  return None
 def migrate_move_namespace(self,mon):
  version=mon.get('moveNamespaceVersion')
  if type(version) is int and version>=MOVE_NAMESPACE_VERSION:return
  known={entry['id'] for entry in mon['moves']}
  for entry in mon['moves']:
   raw=entry['id'];alias=self.native_move_alias(mon['species'],raw,mon['level'])
   # A mixed raw/aliased set has ambiguous provenance. Keep those existing
   # slots intact instead of creating duplicate IDs or deleting a chosen move.
   if alias is not None and alias not in known:
    entry['id']=alias;entry['pp']=min(entry['pp'],self.c.moves[str(alias)]['pp']);known.discard(raw);known.add(alias)
  for entry in mon['pendingLearn'] if isinstance(mon['pendingLearn'],list) else []:
   if not isinstance(entry,dict) or type(entry.get('level')) is not int:continue
   alias=self.native_move_alias(entry.get('species'),entry.get('move'),mon['level'],entry['level'])
   if alias is not None:entry['move']=alias
  self.stamp_move_namespace(mon)
 def earned_entry(self,mon,entry):
  if not isinstance(entry,dict):return False
  source=entry.get('species');level=entry.get('level');move=entry.get('move')
  return (isinstance(source,str) and source in self.c.species and
          source in [mon['species'],*mon.get('evolutionHistory',[])] and
          type(level) is int and 1<=level<=mon['level'] and
          type(move) is int and 1<=move<=65535 and str(move) in self.c.moves and
          [level,move] in self.c.species[source]['learnset'])
 def owned(self,state,uid):
  require(isinstance(uid,str),'Select a Pokemon you own.')
  mon=next((m for m in state['creatures'] if m['uid']==uid),None)
  require(mon is not None,'That Pokemon is not yours.')
  return self.ensure(mon)
 def rules(self,mon):
  source=mon['species'];rules=self.c.data.get('adventureRom',{}).get('evolutions',self.c.data.get('evolutions',{})).get(source,[])
  # Unsupported ROM methods remain provenance, never approximated as a level rule.
  return [r for r in rules if r.get('method') in SUPPORTED_EVOLUTIONS and r.get('target') in self.c.species and r['target']!=source]
 def queue_moves(self,mon,old_level,new_level,source=None):
  self.ensure(mon);source=source or mon['species'];known={m['id'] for m in mon['moves']};queued={m['move'] for m in mon['pendingLearn']}
  for level,move in sorted(self.c.species[source]['learnset'],key=lambda v:v[0]):
   if not old_level<level<=new_level or str(move) not in self.c.moves or move in known or move in queued:continue
   if len(mon['moves'])<4 and not mon['pendingLearn']:
    mon['moves'].append({'id':move,'pp':self.c.moves[str(move)]['pp']});known.add(move)
   else:
    mon['pendingLearn'].append({'move':move,'level':level,'species':source});queued.add(move)
 def pending_moves(self,mon):
  return [{**entry,'name':self.c.moves[str(entry['move'])]['name']} for entry in mon.get('pendingLearn',[]) if str(entry.get('move')) in self.c.moves]
 def level_up_moves(self,mon):
  """Expose the current native profile in ROM order, including repeated rows."""
  return [{'move':move,'name':self.c.moves[str(move)]['name'],'level':level}
          for level,move in self.c.species[mon['species']]['learnset']
          if type(level) is int and 1<=level<=100 and type(move) is int and
          1<=move<=65535 and str(move) in self.c.moves]
 def reminder_options(self,mon):
  # History stores species but not the level of evolution. Only the current
  # species can authorize reminders without inventing ancestor progression.
  excluded={m['id'] for m in mon['moves']}
  excluded.update(entry.get('move') for entry in mon.get('pendingLearn',[]) if isinstance(entry,dict) and type(entry.get('move')) is int)
  choices=[]
  for entry in self.level_up_moves(mon):
   if entry['level']<=mon['level'] and entry['move'] not in excluded:
    choices.append(entry);excluded.add(entry['move'])
  return choices
 def remember(self,state,uid,move,slot):
  candidate=copy.deepcopy(state);mon=self.owned(candidate,uid);integer(move,1,65535,'Move')
  require(any(entry['move']==move for entry in self.reminder_options(mon)),"This move is not available from this Pokemon's current earned learnset.")
  integer(slot,0,3,'Move slot');require(slot<=len(mon['moves']),'Select an existing move or the next empty slot.')
  value={'id':move,'pp':self.c.moves[str(move)]['pp']}
  if slot==len(mon['moves']):mon['moves'].append(value)
  else:mon['moves'][slot]=value
  return candidate
 def options(self,mon):
  choices=[];pending=mon.get('pendingEvolution',[]);deferred=mon.get('evolutionDeferred',[])
  for rule in self.rules(mon):
   method=rule['method'];target=rule['target']
   if method=='level' and (type(rule.get('level')) is not int or not 1<=rule['level']<=100 or mon['level']<rule['level']):continue
   if method=='trade' and not any(p.get('source')==mon['species'] and p.get('target')==target and p.get('method')=='trade' for p in pending):continue
   if method=='stone' and (rule.get('item') not in self.c.items or self.c.items[rule['item']].get('evolutionStone') is not True):continue
   choice={'target':target,'name':self.c.species[target]['name'],'method':method,'deferred':target in deferred}
   if method=='level':choice['level']=rule['level']
   if method=='stone':choice['item']=rule['item']
   if not any(v['target']==target for v in choices):choices.append(choice)
  return choices
 def mark_trade(self,mon):
  """World calls only on transferred copies inside the atomic two-owner trade."""
  self.ensure(mon)
  for rule in self.rules(mon):
   offer={'source':mon['species'],'target':rule['target'],'method':'trade'}
   if rule['method']=='trade' and offer not in mon['pendingEvolution']:mon['pendingEvolution'].append(offer)
  return mon
 def learn(self,state,uid,move,slot=None):
  candidate=copy.deepcopy(state);mon=self.owned(candidate,uid);integer(move,1,65535,'Move')
  queue=mon['pendingLearn'];require(bool(queue) and queue[0].get('move')==move,'That move choice has expired. Review the next pending move.')
  require(self.earned_entry(mon,queue[0]),'This move is not in this Pokemon\'s earned learnset.')
  if slot is not None:
   integer(slot,0,3,'Move slot');require(slot<=len(mon['moves']),'Select an existing move or the next empty slot.')
   require(move not in [m['id'] for m in mon['moves']],'This Pokemon already knows that move.')
   value={'id':move,'pp':self.c.moves[str(move)]['pp']}
   if slot==len(mon['moves']):mon['moves'].append(value)
   else:mon['moves'][slot]=value
  queue.pop(0)
  return candidate
 def defer_evolution(self,state,uid,target):
  candidate=copy.deepcopy(state);mon=self.owned(candidate,uid)
  require(isinstance(target,str) and any(v['target']==target for v in self.options(mon)),'That evolution is not available.')
  require(target not in mon['evolutionDeferred'],'That evolution is already paused.')
  mon['evolutionDeferred'].append(target);return candidate
 def resume_evolution(self,state,uid,target):
  candidate=copy.deepcopy(state);mon=self.owned(candidate,uid)
  require(isinstance(target,str) and any(v['target']==target and v['deferred'] for v in self.options(mon)),'That paused evolution is not available.')
  mon['evolutionDeferred'].remove(target);return candidate
 def evolve(self,state,uid,target):
  candidate=copy.deepcopy(state);mon=self.owned(candidate,uid)
  require(isinstance(target,str),'Select an available evolution.')
  option=next((v for v in self.options(mon) if v['target']==target),None)
  require(option is not None and not option['deferred'],'That evolution is not available. Resume a paused evolution first.')
  source=mon['species']
  # A malformed ROM mapping must never change the meaning of saved EXP.
  require(self.c.species[source]['growth']==self.c.species[target]['growth'],'This evolution uses an unsupported experience-growth transition.')
  if option['method']=='stone':
   item=option['item'];require(candidate['items'].get(item,0)>0,'You do not have the required evolution item.');candidate['items'][item]-=1
  old_hp=self.c.stats(mon)[0];hp=mon['hp'];mon['species']=target;new_hp=self.c.stats(mon)[0]
  mon['hp']=min(new_hp,max(1,hp+new_hp-old_hp)) if hp>0 else 0
  if source not in mon['evolutionHistory']:mon['evolutionHistory'].append(source)
  mon['pendingEvolution']=[];mon['evolutionDeferred']=[]
  self.queue_moves(mon,mon['level']-1,mon['level'],target)
  return candidate
