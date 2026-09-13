"""Native entrance, destination fidelity and per-account return regression tests."""
from __future__ import annotations
import asyncio,collections,copy,dataclasses,hashlib,json,struct,sys,tempfile,unittest,zlib
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'));sys.path.insert(0,str(ROOT/'Tools'))
from nxt.content import Content
from nxt.config import Settings
from nxt.store import Store
from nxt.world import World
from nxt.security import Bucket,RequestError
from nxt.portals import plan_warp,return_stack
from repair_interiors import apply,apply_navigation,standable,ENTRY


def decode_png(path):
 """Decode the source's non-interlaced 8-bit PNGs using only build stdlib."""
 blob=path.read_bytes()
 if blob[:8]!=b'\x89PNG\r\n\x1a\n':raise AssertionError('Invalid PNG signature')
 offset=8;compressed=bytearray();header=None
 while offset<len(blob):
  length=struct.unpack_from('>I',blob,offset)[0];kind=blob[offset+4:offset+8];data=blob[offset+8:offset+8+length]
  checksum=struct.unpack_from('>I',blob,offset+8+length)[0]
  if zlib.crc32(kind+data)&0xffffffff!=checksum:raise AssertionError('PNG chunk CRC mismatch')
  if kind==b'IHDR':header=struct.unpack('>IIBBBBB',data)
  elif kind==b'IDAT':compressed.extend(data)
  elif kind==b'IEND':break
  offset+=12+length
 if header is None:raise AssertionError('Missing PNG header')
 width,height,depth,color,compression,filter_method,interlace=header
 if depth!=8 or color not in (2,6) or compression or filter_method or interlace:
  raise AssertionError('Expected non-interlaced 8-bit RGB/RGBA source PNG')
 channels=3 if color==2 else 4;stride=width*channels;raw=zlib.decompress(compressed)
 if len(raw)!=(stride+1)*height:raise AssertionError('PNG scanline length mismatch')
 previous=bytearray(stride);rows=[]
 for y in range(height):
  start=y*(stride+1);method=raw[start];row=bytearray(raw[start+1:start+1+stride])
  if method not in (0,1,2,3,4):raise AssertionError('Unknown PNG filter')
  if method:
   for i in range(stride):
    left=row[i-channels] if i>=channels else 0;up=previous[i]
    if method==1:predictor=left
    elif method==2:predictor=up
    elif method==3:predictor=(left+up)//2
    else:
     corner=previous[i-channels] if i>=channels else 0;p=left+up-corner
     pa,pb,pc=abs(p-left),abs(p-up),abs(p-corner)
     predictor=left if pa<=pb and pa<=pc else (up if pb<=pc else corner)
    row[i]=(row[i]+predictor)&255
  rows.append(bytes(row));previous=row
 return width,height,channels,rows


class InteriorMetadataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=apply(json.loads((ROOT/'Server/data/world.json').read_text()))
  cls.content=SimpleNamespace(maps=cls.data['maps'])
  cls.report=json.loads((ROOT/'Server/data/interior_repairs.json').read_text())
 def test_all_active_portals_have_safe_native_arrivals(self):
  total=0
  for key,m in self.content.maps.items():
   for warp in m['warps']:
    access=warp.get('access')
    if not access:continue
    with self.subTest(map=key,index=warp['index']):
     self.assertTrue(0<=warp['x']<m['width'] and 0<=warp['y']<m['height'])
     behavior=m['behavior'][warp['y']*m['width']+warp['x']]
     self.assertIn(behavior,ENTRY)
     if access.get('dynamic'):self.assertTrue(warp['target'].endswith('_127_127'));continue
     target=self.content.maps[warp['target']]
     self.assertTrue(0<=warp['targetIndex']<len(target['warps']))
     self.assertTrue(standable(target,*access['arrival']))
     native=target['warps'][warp['targetIndex']]
     self.assertLessEqual(abs(native['x']-access['arrival'][0])+abs(native['y']-access['arrival'][1]),1)
     total+=1
  self.assertGreater(total,3500)
 def test_all_ordinary_floor_events_remain_inert(self):
  count=0
  for m in self.content.maps.values():
   for warp in m['warps']:
    x,y=warp['x'],warp['y']
    if 0<=x<m['width'] and 0<=y<m['height'] and m['behavior'][y*m['width']+x] not in ENTRY:
     self.assertNotIn('access',warp,(m['id'],warp));count+=1
  self.assertGreater(count,1000)
 def test_new_bark_four_buildings_are_correct_native_interiors(self):
  m=self.content.maps['johto_3_0']
  expected={(13,4):'johto_4_3',(17,15):'johto_33_0',(22,7):'johto_4_0',(7,13):'johto_32_2'}
  for point,target in expected.items():
   with self.subTest(point=point):
    state={'map':m['id'],'x':point[0],'y':point[1]+1}
    self.assertEqual(plan_warp(self.content,state,m,*point,'up')['map'],target)
    for direction,dx,dy in [('left',1,0),('right',-1,0),('down',0,-1)]:
     wrong=dict(state,x=point[0]+dx,y=point[1]+dy)
     self.assertIsNone(plan_warp(self.content,wrong,m,*point,direction))
 def test_leaf_frontstep_does_not_enter_battle_frontier(self):
  m=self.content.maps['johto_3_0'];state={'map':m['id'],'x':22,'y':9}
  self.assertIsNone(plan_warp(self.content,state,m,22,8,'up'))
 def test_recovered_leaf_upstairs_and_chuck_gym_keep_native_assets(self):
  for key,shape in [('johto_1_93',(14,11)),('johto_1_88',(20,60))]:
   m=self.content.maps[key];self.assertEqual((m['width'],m['height']),shape)
   self.assertTrue((ROOT/'Client/app/assets'/m['image']).is_file())
   self.assertIn('sourceHeader',m);self.assertIn('musicId',m)
  self.assertEqual(len(self.content.maps['johto_7_1']['warps']),147)
  self.assertEqual(self.content.maps['johto_1_58']['warps'][10]['target'],'johto_1_58')
 def test_saved_return_validation_drops_corrupt_records(self):
  m=self.content.maps['johto_3_0'];base={'inside':'johto_32_0','outside':m['id'],'x':17,'y':10}
  state={'warpReturns':[base,dict(base,x=-1),dict(base,inside='missing'),dict(base,x=True),None]}
  self.assertEqual(return_stack(self.content,state),[base])
 def test_gym_navigation_changes_only_declared_cells_and_boulders(self):
  original=copy.deepcopy(self.data);changed=apply_navigation(copy.deepcopy(original));nav=json.loads((ROOT/'Server/data/interior_navigation.json').read_text())
  for key,m in original['maps'].items():
   change=nav['maps'].get(key,{});allowed={p['y']*m['width']+p['x'] for p in change.get('tiles',[])}
   for field in ('collision','behavior','elevation'):
    self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(m[field],changed['maps'][key][field]))),(key,field))
   removed=change.get('clearObjects',[])
   expected=[o for o in m['objects'] if not any(all(o.get(f)==point[f] for f in ('x','y','graphics')) for point in removed)]
   self.assertEqual(changed['maps'][key]['objects'],expected)
 def test_open_gate_graphics_change_only_audited_tiles_keep_original_images(self):
  nav=json.loads((ROOT/'Server/data/interior_navigation.json').read_text());assets=ROOT/'Client/app/assets'
  for key,change in nav['maps'].items():
   if 'assets' not in change:continue
   with self.subTest(map=key):
    native=assets/change['nativeImage'];self.assertEqual(hashlib.sha256(native.read_bytes()).hexdigest(),change['nativeImageSha256'])
    width,height,channels,source=decode_png(native);tw,th,tc,target=decode_png(assets/change['assets']['image'])
    self.assertEqual((width,height,channels),(tw,th,tc));self.assertNotEqual(source,target)
    for y,(before,after) in enumerate(zip(source,target)):
     intervals=sorted((p['x']*16*channels,(p['x']+1)*16*channels) for p in change['tiles'] if p['y']*16<=y<(p['y']+1)*16)
     cursor=0
     for start,end in intervals:
      self.assertEqual(before[cursor:start],after[cursor:start],f'Undeclared pixel changes on row {y}')
      cursor=max(cursor,end)
     self.assertEqual(before[cursor:],after[cursor:],f'Undeclared pixel changes on row {y}')
 def test_source_collision_arrays_are_not_globally_opened(self):
  original=json.loads((ROOT/'Server/data/world.json').read_text())
  for key,m in original['maps'].items():self.assertEqual(m['collision'],self.content.maps[key]['collision'])


class InteriorMovementTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):
  cls.content=Content(ROOT/'Server/data/world.json')
  apply(cls.content.data);apply_navigation(cls.content.data);cls.content.maps=cls.content.data['maps']
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();path=Path(self.tmp.name)/'config.ini'
  path.write_text((ROOT/'Build/config_templates/Server/config.ini').read_text())
  settings=Settings.load(path);settings.config.set('database','backend','sqlite')
  self.settings=dataclasses.replace(settings,encounter_chance=0)
  self.db=Store(self.settings);self.db.acquire_lease();self.world=World(self.content,self.db,self.settings)
  state=self.world.initial('DoorTester','Johto','fr_4',0);self.uid=self.db.create('DoorTester','test',state)
  self.player=await self.world.join(self.uid,'DoorTester',state,asyncio.Queue(maxsize=10000))
 async def asyncTearDown(self):
  self.world.players.clear();self.db.close();self.tmp.cleanup()
 def locate(self,player,key,x,y):
  player.state.update(map=key,x=x,y=y,surf=False);self.world.follower_anchor(player)
 async def step(self,player,direction):
  player.last_move=0;player.move_bucket=Bucket(100,1)
  await self.world.move(player,{'seq':player.last_seq+1,'direction':direction})
 def packets(self,player):
  result=[]
  while not player.queue.empty():result.append(player.queue.get_nowait())
  return result
 async def test_outside_walk_leaf_home_upstairs_and_back(self):
  p=self.player;self.locate(p,'johto_3_0',22,9)
  await self.step(p,'up');self.assertEqual((p.state['map'],p.state['x'],p.state['y']),('johto_3_0',22,8))
  await self.step(p,'up');self.assertEqual((p.state['map'],p.state['x'],p.state['y']),('johto_4_0',10,7))
  self.assertEqual(self.db.load(p.id)['map'],'johto_4_0')
  # Walk across actual lower-room floor to the native staircase.
  for direction in ['up']*5:await self.step(p,direction)
  self.assertEqual(p.state['map'],'johto_1_93')
  await self.step(p,'down');await self.step(p,'up');self.assertEqual(p.state['map'],'johto_4_0')
  for direction in ['down']*6:await self.step(p,direction)
  self.assertEqual((p.state['map'],p.state['x'],p.state['y']),('johto_3_0',22,8))
 async def test_both_regions_center_enter_and_exit_from_real_front_step(self):
  p=self.player
  for region in ['kanto','johto']:
   with self.subTest(region=region):
    self.locate(p,region+'_3_1',26,27);await self.step(p,'up')
    self.assertEqual((p.state['map'],p.state['x'],p.state['y']),(region+'_5_4',7,7))
    await self.step(p,'down');self.assertEqual((p.state['map'],p.state['x'],p.state['y']),(region+'_3_1',26,27))
 async def test_two_accounts_shared_center_returns_stay_independent_after_relogin(self):
  p=self.player;state=self.world.initial('OtherDoor','Johto','fr_152',7);uid=self.db.create('OtherDoor','test',state)
  q=await self.world.join(uid,'OtherDoor',state,asyncio.Queue(maxsize=10000))
  self.locate(p,'johto_3_47',43,6);self.locate(q,'johto_3_47',28,46)
  await self.step(p,'up');await self.step(q,'up')
  self.assertEqual(p.state['map'],'johto_32_0');self.assertEqual(q.state['map'],'johto_32_0')
  self.assertEqual(p.state['warpReturns'][-1]['x'],43);self.assertEqual(q.state['warpReturns'][-1]['x'],28)
  await self.world.leave(p);p=await self.world.join(p.id,p.username,None,asyncio.Queue(maxsize=10000))
  self.player=p
  await self.step(p,'down');await self.step(q,'down')
  self.assertEqual((p.state['map'],p.state['x'],p.state['y']),('johto_3_47',43,6))
  self.assertEqual((q.state['map'],q.state['x'],q.state['y']),('johto_3_47',28,46))
  self.assertEqual(p.state['warpReturns'],[]);self.assertEqual(q.state['warpReturns'],[])
 async def test_all_sixteen_native_gym_doors_reach_the_correct_leader_by_walking(self):
  registry=json.loads((ROOT/'Server/data/adventure_rom.json').read_text());gyms=registry['gyms'];self.assertEqual(len(gyms),16)
  p=self.player
  for gym in gyms:
   with self.subTest(region=gym['region'],leader=gym['name']):
    key=gym['map'];m=self.content.maps[key];npc=next(o for o in m['objects'] if o['id']==gym['npc'])
    sources=[(src,e) for src in self.content.maps.values() for e in src['warps']
             if e['target']==key and e.get('access',{}).get('kind')=='door' and src['mapType'] in (0,1,2,3)]
    self.assertTrue(sources)
    outside,door=next(((src,e) for src,e in sources if src['id'].startswith(gym['source']+'_3_')),sources[0])
    self.locate(p,outside['id'],door['x'],door['y']+1);p.state['warpReturns']=[]
    await self.step(p,'up');self.assertEqual(p.state['map'],key)
    path=self.leader_path(p.state,(key,npc['x'],npc['y']));self.assertIsNotNone(path,'Leader has no walkable native entrance route')
    for direction in path:await self.step(p,direction)
    self.assertEqual(p.state['map'],key)
    self.assertLessEqual(max(abs(p.state['x']-npc['x']),abs(p.state['y']-npc['y'])),2)
    self.assertIsNone(p.battle);self.packets(p)
 def leader_path(self,start,goal):
  goalmap,gx,gy=goal;region=self.content.maps[goalmap]['name']
  q=collections.deque([(start['map'],start['x'],start['y'],[])]);seen={(start['map'],start['x'],start['y'])}
  directions={'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}
  while q:
   key,x,y,path=q.popleft();m=self.content.maps[key]
   if key==goalmap and max(abs(x-gx),abs(y-gy))<=2:return path
   elevation=m['elevation'][y*m['width']+x]
   for direction,(dx,dy) in directions.items():
    xx,yy=x+dx,y+dy;nkey=key
    if not(0<=xx<m['width'] and 0<=yy<m['height']):continue
    plan=plan_warp(self.content,dict(start,map=key,x=x,y=y),m,xx,yy,direction)
    if plan:
     if 'blocked' in plan:continue
     target=self.content.maps[plan['map']]
     if target['id']!=key and (target['name']!=region or target['mapType'] not in (0,8)):continue
     nkey,xx,yy=target['id'],plan['x'],plan['y']
    else:
     behavior=m['behavior'][yy*m['width']+xx]
     if behavior=={'up':58,'down':59,'left':57,'right':56}[direction]:xx+=dx;yy+=dy
     if not self.world.walkable(m,xx,yy,False,None if behavior in (56,57,58,59) else elevation):continue
    point=(nkey,xx,yy)
    if point not in seen:seen.add(point);q.append((*point,path+[direction]))
  return None
 async def test_every_registered_center_building_door_round_trips_by_walking(self):
  centers=json.loads((ROOT/'Server/data/centers.json').read_text())['centers'];p=self.player;checked=0
  for key,m in self.content.maps.items():
   for e in m['warps']:
    if e['target'] not in centers or e.get('access',{}).get('kind')!='door':continue
    with self.subTest(outside=key,door=e['index'],center=e['target']):
     outside=(key,e['x'],e['y']+1);self.assertTrue(self.world.walkable(m,outside[1],outside[2]))
     self.locate(p,*outside);p.state['warpReturns']=[];await self.step(p,'up')
     self.assertEqual(p.state['map'],e['target'])
     path=self.exit_path(p.state,outside);self.assertIsNotNone(path,'No reachable return to this building entrance')
     for direction in path:await self.step(p,direction)
     self.assertEqual((p.state['map'],p.state['x'],p.state['y']),outside)
     self.packets(p);checked+=1
  self.assertGreaterEqual(checked,60)
 def exit_path(self,start,outside):
  m=self.content.maps[start['map']];q=collections.deque([(start['x'],start['y'],[])]);seen={(start['x'],start['y'])}
  for_loop={'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}
  while q:
   x,y,path=q.popleft();state=dict(start,x=x,y=y);elevation=m['elevation'][y*m['width']+x]
   for direction,(dx,dy) in for_loop.items():
    xx,yy=x+dx,y+dy
    if not(0<=xx<m['width'] and 0<=yy<m['height']):continue
    plan=plan_warp(self.content,state,m,xx,yy,direction)
    if plan:
     if 'blocked' in plan:continue
     if (plan['map'],plan['x'],plan['y'])==outside:return path+[direction]
     if plan['map']!=m['id']:continue
     xx,yy=plan['x'],plan['y']
    elif not self.world.walkable(m,xx,yy,False,elevation):continue
    if (xx,yy)not in seen:seen.add((xx,yy));q.append((xx,yy,path+[direction]))
  return None
 async def test_failed_portal_save_does_not_move_or_publish_destination(self):
  p=self.player;self.locate(p,'johto_3_0',22,8);previous=copy.deepcopy(p.state);self.packets(p)
  with mock.patch.object(self.db,'save_many',side_effect=OSError('disk unavailable')):
   with self.assertRaises(RequestError):await self.step(p,'up')
  self.assertEqual(p.state,previous)
  self.assertFalse(any(v['type']=='map' for v in self.packets(p)))
 async def test_adjacent_wall_and_incorrect_door_approach_do_not_bypass_collision(self):
  p=self.player;self.locate(p,'johto_3_0',22,8);await self.step(p,'right')
  self.assertEqual(p.state['map'],'johto_3_0')
  # House wall directly beside the door remains solid.
  await self.step(p,'up');self.assertEqual((p.state['map'],p.state['x'],p.state['y']),('johto_3_0',23,8))

if __name__=='__main__':unittest.main()
