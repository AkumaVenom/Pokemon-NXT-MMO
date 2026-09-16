"""Pure plans for validated ROM portals and account-owned dynamic returns.

The caller persists the returned location and warpReturns together before sending
any map packet. This module never mutates content or another player's state.
"""
from __future__ import annotations
import copy

DIRECTIONS={'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}
MAX_RETURN_DEPTH=32


def _point(m,x,y):
 return (type(x) is int and type(y) is int and 0<=x<m['width'] and
         0<=y<m['height'] and m['collision'][y*m['width']+x]==0 and
         not any(o['x']==x and o['y']==y and o['graphics'] in (95,96,97) for o in m['objects']))


def return_stack(content,state):
 """Drop malformed/obsolete saved entries; never accept client portal state."""
 result=[];owned=set()
 raw=state.get('warpReturns',[])
 if not isinstance(raw,list):return result
 for entry in raw[-MAX_RETURN_DEPTH:]:
  if not isinstance(entry,dict):continue
  inner=content.maps.get(entry.get('inside'));outer=content.maps.get(entry.get('outside'))
  if inner is None or outer is None or not _point(outer,entry.get('x'),entry.get('y')):continue
  # Older builds could accidentally push the same shared room twice after an
  # internal upstairs/downstairs transition. Keep the first valid owner return
  # so an already-affected save exits to its real building entrance instead of
  # looping back into another interior room.
  if inner['id'] in owned:continue
  owned.add(inner['id'])
  result.append({k:copy.deepcopy(entry[k]) for k in ('inside','outside','x','y')})
 return result


def plan_warp(content,state,m,x,y,direction):
 """Return an atomic relocation plan, None, or a blocked-return notice.

This must run before generic collision rejection: animated source doors are solid
metatiles. Inert ordinary-floor events do not have an access descriptor and can
never trigger a portal, even if their destination record looks valid.
"""
 if direction not in DIRECTIONS or state.get('map')!=m['id']:return None
 dx,dy=DIRECTIONS[direction]
 if (state.get('x',-999)+dx,state.get('y',-999)+dy)!=(x,y):return None
 if not (0<=x<m['width'] and 0<=y<m['height']):return None
 for warp in m['warps']:
  access=warp.get('access')
  if (warp['x'],warp['y'])!=(x,y) or not access or direction not in access.get('directions',[]):continue
  stack=return_stack(content,state)
  if access.get('dynamic'):
   match=next((i for i in range(len(stack)-1,-1,-1) if stack[i]['inside']==m['id']),None)
   if match is None:
    return {'blocked':'This shared room has no saved entrance. Use Return home, then enter through its building door.'}
   entry=stack[match];target=content.maps[entry['outside']]
   return {'map':target['id'],'x':entry['x'],'y':entry['y'],'warpReturns':stack[:match]}
  target=content.maps.get(warp['target']);point=access.get('arrival')
  if target is None or not isinstance(point,list) or len(point)!=2 or not _point(target,*point):return None
  # An explicit return to a known parent also retires that context. A later
  # entrance to the same reused room gets this account's current doorway.
  matching=next((i for i in range(len(stack)-1,-1,-1)
                 if stack[i]['inside']==m['id'] and stack[i]['outside']==target['id']),None)
  if matching is not None:stack=stack[:matching]
  if target['id']!=m['id'] and any(e.get('access',{}).get('dynamic') for e in target['warps']):
   # A shared room owns one return context for the whole interior visit.
   # Internal stairs/rooms can lead back into that same shared room; treating
   # those links as a fresh building entrance overwrites the real exterior
   # return and traps the player in an interior loop (for example a Pokemon
   # Center upstairs -> downstairs transition).  Preserve the existing owner
   # context until its dynamic exit actually consumes it.
   owns_context=any(entry['inside']==target['id'] for entry in stack)
   if not owns_context:
    if _point(m,state['x'],state['y']):
     stack.append({'inside':target['id'],'outside':m['id'],'x':state['x'],'y':state['y']})
     stack=stack[-MAX_RETURN_DEPTH:]
    else:return None
  return {'map':target['id'],'x':point[0],'y':point[1],'warpReturns':stack}
 return None
