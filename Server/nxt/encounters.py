"""Authoritative location/method/time encounter resolution, without fallback spawns.

Map zones are explicit, non-overlapping, half-open tile rectangles. An empty zone
is intentional (e.g. a laboratory below a merged ruin), not a reason to fall back.
Crystal uses the world server's local clock: morning 04-09, day 10-17, night 18-03.
"""
from __future__ import annotations
import time

WATER = {16,17,18,19,21,26,27}
LAND = {2,8,11}
FLOOR = {0,2,7,8,11,32,33,34,35,36,37,38,39}

def encounter_period(hour=None):
 if hour is None:hour=time.localtime().tm_hour
 if type(hour) is not int or not 0<=hour<24:raise ValueError('Encounter hour must be 0-23')
 return 'morning' if 4<=hour<10 else 'day' if 10<=hour<18 else 'night'

def encounter_area(m,x,y):
 for zone in m.get('encounterZones',[]):
  left,top,right,bottom=zone['rect']
  if left<=x<right and top<=y<bottom:return zone
 return m

def encounter_slots(m,state,*,hour=None):
 """Return only the eligible pool for this exact tile; does not mutate content."""
 x,y=state['x'],state['y']
 if not (0<=x<m['width'] and 0<=y<m['height']):return []
 i=y*m['width']+x
 if m['collision'][i]!=0:return []
 # Door/ladder/warp and healing tiles never become a manual encounter shortcut.
 if any(w['x']==x and w['y']==y for w in m.get('warps',[])):return []
 behavior=m['behavior'][i];area=encounter_area(m,x,y);tables=area.get('encounters',{})
 if behavior in WATER:
  return tables.get('water',[]) if state.get('surf',False) else []
 if behavior not in LAND and not (area.get('encounterTerrain')=='floor' and behavior in FLOOR):return []
 timed='land_'+encounter_period(hour)
 return tables.get(timed,tables.get('land',[]))

def select_encounter(slots,rng):
 """Select original ordered slot weights, then the slot's exact level model."""
 if not slots:raise ValueError('No eligible encounter slots')
 e=rng.choices(slots,weights=[s['weight'] for s in slots],k=1)[0]
 weights=e.get('levelWeights')
 level=e['min']+rng.choices(range(len(weights)),weights=weights,k=1)[0] if weights else rng.randint(e['min'],e['max'])
 return e['species'],level

def validate_encounter_map(m,species):
 def validate(area):
  if area.get('encounterTerrain','tiles') not in ('tiles','floor'):raise ValueError('Invalid encounter terrain: '+m['id'])
  for method,rows in area.get('encounters',{}).items():
   if not isinstance(rows,list):raise ValueError('Invalid encounter rows: '+m['id'])
   for e in rows:
    if e.get('species') not in species or not all(type(e.get(k)) is int for k in ('min','max','weight')) or not 1<=e['min']<=e['max']<=100 or e['weight']<=0:raise ValueError('Invalid encounter slot: '+m['id'])
    if 'levelWeights' in e:
     lw=e['levelWeights']
     if not isinstance(lw,list) or len(lw)!=e['max']-e['min']+1 or not all(type(v) is int and v>0 for v in lw):raise ValueError('Invalid encounter levels: '+m['id'])
   # The legacy combined FR fishing record contains 3 separately weighted rods.
   if rows and sum(e['weight'] for e in rows)!=(300 if method=='fishing' else 100):raise ValueError('Invalid encounter probability total: '+m['id']+'/'+method)
 validate(m)
 seen=[]
 for z in m.get('encounterZones',[]):
  rect=z.get('rect',[])
  if len(rect)!=4 or not all(type(v) is int for v in rect):raise ValueError('Invalid encounter zone: '+m['id'])
  x1,y1,x2,y2=rect
  if not(0<=x1<x2<=m['width'] and 0<=y1<y2<=m['height']):raise ValueError('Out-of-bounds encounter zone: '+m['id'])
  if any(max(x1,a)<min(x2,c) and max(y1,b)<min(y2,d) for a,b,c,d in seen):raise ValueError('Overlapping encounter zones: '+m['id'])
  seen.append(rect);validate(z)
