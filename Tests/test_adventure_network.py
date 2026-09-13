"""Real TCP adventure contracts against production sockets and isolated SQLite.

Fixture placement and trained levels shorten travel/combat; no tested gameplay
command, battle result, reward or network response is mocked. This is not a
Windows/MySQL/load test or an assertion of original campaign balance.
"""
from __future__ import annotations
import asyncio,copy,dataclasses,random,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import aiohttp
from aiohttp import web
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'));sys.path.insert(0,str(ROOT/'Tests'))
from test_replication_network import Peer,PASSWORD,ORIGIN
from nxt.config import Settings
from nxt.content import Content
from nxt.growth import Growth
from nxt.store import Store
from server import Service

class AdventureNetworkTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):
  cls.base_content=Content(ROOT/'Server/data/world.json')
  assert len(cls.base_content.data.get('adventureRom',{}).get('gyms',[]))==16,'Adventure content must be merged into the release world.json before integration tests.'
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();path=Path(self.tmp.name)/'config.ini';path.write_bytes((ROOT/'Build/config_templates/Server/config.ini').read_bytes());settings=Settings.load(path);settings.config.set('database','backend','sqlite');settings.config.set('security','auth_attempts_per_minute','100')
  self.settings=dataclasses.replace(settings,encounter_chance=0);self.content=copy.copy(self.base_content);self.content.rng=random.Random(253);self.content.growth=Growth(self.content);self.peers=[];self.session=aiohttp.ClientSession();await self.start_service()
 async def start_service(self):
  self.db=Store(self.settings);self.db.acquire_lease();self.service=Service(self.settings,self.content,self.db);self.world=self.service.world;app=web.Application();app.router.add_get('/world',self.service.socket);app.router.add_get('/health',self.service.health);self.runner=web.AppRunner(app);await self.runner.setup();site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start();self.base=f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
 async def stop_service(self):
  for peer in self.peers:
   await peer.socket.close()
  await self.runner.cleanup();self.db.close()
 async def asyncTearDown(self):
  await self.stop_service();await self.session.close();self.tmp.cleanup()
 async def auth(self,name,starter,mode='register'):
  socket=await self.session.ws_connect(self.base+'/world',headers={'Origin':ORIGIN},protocols=('nxt.v1',));peer=Peer(self,socket);self.peers.append(peer);await peer.until('hello');await peer.send(op='auth',mode=mode,username=name,password=PASSWORD,pack=self.content.pack,home='Johto',starter=starter,appearance=7 if name=='Akumavenom' else 0);joined=await peer.until('joined');state=await peer.until('state');return peer,joined['id'],state
 async def pair(self):return await asyncio.gather(self.auth('Akumavenom','fr_152'),self.auth('Spidermight','fr_4'))
 async def close_account(self,peer,uid):
  await peer.socket.close()
  async with asyncio.timeout(5):
   while uid in self.world.players:await asyncio.sleep(.005)
 async def put_near(self,peer,uid,map_id,npc):
  m=self.content.maps[map_id];obj=next(o for o in m['objects'] if o['id']==npc)
  tiles=[(abs(x-obj['x'])+abs(y-obj['y']),x,y) for y in range(max(0,obj['y']-2),min(m['height'],obj['y']+3)) for x in range(max(0,obj['x']-2),min(m['width'],obj['x']+3)) if (x,y)!=(obj['x'],obj['y']) and self.world.walkable(m,x,y)]
  self.assertTrue(tiles,f'No reachable service tile: {map_id}:{npc}');_,x,y=min(tiles)
  async with self.world.lock:await self.world.relocate_saved(self.world.players[uid],map_id,x,y)
  await peer.barrier()
 async def stage(self,peer,uid,change):
  async with self.world.lock:
   player=self.world.players[uid];candidate=copy.deepcopy(player.state);change(candidate);await self.world.commit(player,candidate)
  await peer.barrier()
 def first_gym(self,region):return next(g for g in self.world.adventure.gyms if g['region'].lower()==region and g['order']==1)
 def center(self,region):return next((k,v) for k,v in self.content.data['centers'].items() if k.startswith(region+'_') and v['kind']=='pokemon-center' and v['nurseNpcIds'] and v.get('nursePcAccess'))
 async def trained(self,peer,uid):
  def prepare(s):
   m=s['creatures'][0];self.content.gain_xp(m,self.content.xp(100,self.content.species[m['species']]['growth'])-m['exp']);self.content.heal(m)
  await self.stage(peer,uid,prepare)
 async def start_gym(self,peer,uid,gym):
  await self.put_near(peer,uid,gym['map'],gym['npc']);await peer.send(op='npc',npc=gym['npc'],action='battle');packet=await peer.until('battle');self.assertEqual(packet['battle']['opponentName'],gym['name']);self.assertFalse(packet['battle']['canRun']);return packet['battle']
 async def win(self,peer,battle):
  battle_id=battle['id']
  for _ in range(30):
   if battle['ended']:break
   usable=battle['usable'];moves=battle['you']['moves'];slot=next((i for i in usable if self.content.moves[str(moves[i]['id'])]['power']>0),usable[0] if usable else -1)
   await peer.send(op='battle',id=battle_id,action='attack',slot=slot);packet=await peer.until('battle',lambda p:p['battle']['id']==battle_id);battle=packet['battle']
  self.assertTrue(battle['ended'],'Bounded trained fixture did not finish the real battle.');self.assertEqual(battle['result'],'won');await peer.barrier();return battle
 async def test_two_clients_keep_starters_and_independent_regional_badges_after_cold_restart(self):
  (a,aid,ast),(b,bid,bst)=await self.pair();self.assertEqual(ast['creatures'][0]['species'],'fr_152');self.assertEqual(bst['creatures'][0]['species'],'fr_4');self.assertNotEqual(ast['party'][0],bst['party'][0]);await self.trained(a,aid);await self.trained(b,bid)
  for region in ('johto','kanto'):
   gym=self.first_gym(region);ab=await self.start_gym(a,aid,gym);bb=await self.start_gym(b,bid,gym);self.assertNotEqual(ab['id'],bb['id']);b_before=copy.deepcopy(self.db.load(bid));await self.win(a,ab)
   self.assertEqual(self.db.load(bid),b_before);self.assertIn(region+'_1',self.db.load(aid)['adventure']['badges']);self.assertNotIn(region+'_1',self.db.load(bid)['adventure']['badges'])
   other_packets=await b.barrier();self.assertFalse([p for p in other_packets if p['type']=='state']);self.assertFalse([p for p in other_packets if p['type']=='battle' and p['battle']['id']!=bb['id']]);await self.win(b,bb)
   for uid in (aid,bid):self.assertIn(region+'_1',self.db.load(uid)['adventure']['badges'])
  before={uid:self.db.load(uid) for uid in (aid,bid)};await self.close_account(a,aid);await self.close_account(b,bid);await self.stop_service();await self.start_service()
  (a,again_a,after_a),(b,again_b,after_b)=await asyncio.gather(self.auth('Akumavenom','fr_4','login'),self.auth('Spidermight','fr_152','login'))
  self.assertEqual((again_a,again_b),(aid,bid))
  for uid,packet,species in ((aid,after_a,'fr_152'),(bid,after_b,'fr_4')):
   saved=self.db.load(uid);self.assertEqual(saved['adventure'],before[uid]['adventure']);self.assertEqual(saved['creatures'],before[uid]['creatures']);self.assertEqual(packet['creatures'][0]['species'],species);self.assertEqual(packet['party'],before[uid]['party']);self.assertEqual(set(saved['adventure']['badges']),{'johto_1','kanto_1'})
 async def test_nurse_proximity_heal_and_pc_ownership_survive_relogin(self):
  (a,aid,ast),(b,bid,bst)=await self.pair();other_uid=bst['party'][0]
  def injure(s):
   mon=s['creatures'][0];mon.update(hp=1,status='poison',sleep=2)
   for move in mon['moves']:move['pp']=0
   reserve=self.content.new_mon('fr_7',5,'Akumavenom');reserve.update(hp=0,status='sleep',sleep=2)
   for move in reserve['moves']:move['pp']=0
   s['creatures'].append(reserve);s['party'].append(reserve['uid'])
  await self.stage(a,aid,injure);before=copy.deepcopy(self.db.load(aid));center_id,center=self.center('johto');nurse=center['nurseNpcIds'][0]
  await a.send(op='heal');await a.until('error');await a.send(op='npc',npc=nurse,action='heal');await a.until('error');self.assertEqual(self.db.load(aid),before)
  await a.send(op='pc',action='deposit',uid=ast['party'][0]);await a.until('error');self.assertEqual(self.db.load(aid),before)
  await self.put_near(a,aid,center_id,nurse);await a.send(op='npc',npc=nurse,action='heal');healed=await a.until('state');await a.until('dialog')
  for mon in healed['creatures']:
   self.assertEqual(mon['hp'],mon['maxHp']);self.assertEqual(mon['status'],'');self.assertTrue(all(move['pp']==self.content.moves[str(move['id'])]['pp'] for move in mon['moves']))
  self.assertTrue(all(m['sleep']==0 for m in self.db.load(aid)['creatures']));self.assertEqual(self.db.load(aid)['adventure']['lastCenter'],center_id);self.assertTrue(healed['adventure']['pcAvailable']);healthy=copy.deepcopy(self.db.load(aid));b_before=copy.deepcopy(self.db.load(bid))
  await a.send(op='pc',action='withdraw',uid=other_uid);await a.until('error');self.assertEqual(self.db.load(aid),healthy);self.assertEqual(self.db.load(bid),b_before)
  reserve=healed['party'][1];await a.send(op='pc',action='deposit',uid=reserve);deposited=await a.until('state');self.assertEqual(deposited['party'],[ast['party'][0]]);self.assertEqual(deposited['adventure']['stored'],1)
  await a.send(op='pc',action='deposit',uid=ast['party'][0]);await a.until('error');self.assertEqual(self.db.load(aid)['party'],[ast['party'][0]])
  await a.send(op='pc',action='withdraw',uid=reserve);withdrawn=await a.until('state');self.assertEqual(withdrawn['party'],healed['party']);before_relogin=self.db.load(aid);await self.close_account(a,aid);a,rejoined,reloaded=await self.auth('Akumavenom','fr_4','login');self.assertEqual(rejoined,aid);self.assertEqual(reloaded['party'],withdrawn['party']);self.assertEqual(self.db.load(aid)['creatures'],before_relogin['creatures']);self.assertEqual(self.db.load(bid),b_before)
 async def test_journal_claim_is_owner_only_idempotent_and_no_reward_on_save_failure(self):
  (a,aid,ast),(b,bid,bst)=await self.pair()
  await a.send(op='journal.claim',id='first_capture');await a.until('error')
  def capture_fixture(s):s['creatures'].append(self.content.new_mon('fr_7',5,'Akumavenom'))
  await self.stage(a,aid,capture_fixture);before=self.db.load(aid);other=self.db.load(bid)
  with patch.object(self.db,'save_many',side_effect=RuntimeError('injected objective storage outage')):
   with self.assertLogs('nxt.world',level='ERROR'):
    await a.send(op='journal.claim',id='first_capture');error=await a.until('error')
  self.assertIn('database',error['message'].lower());self.assertEqual(self.db.load(aid),before);self.assertEqual(self.world.players[aid].state,before);self.assertEqual(self.db.load(bid),other)
  await a.send(op='journal.claim',id='first_capture');awarded=await a.until('state');await a.until('notice');goal=next(g for g in self.content.data['adventure']['goals'] if g['id']=='first_capture');reward=goal['reward'];self.assertEqual(awarded['money'],before['money']+reward['money'])
  for item,count in reward['items'].items():self.assertEqual(awarded['items'][item],before['items'].get(item,0)+count)
  done=self.db.load(aid);self.assertIn('first_capture',done['adventure']['claimed']);await a.send(op='journal.claim',id='first_capture');await a.until('error');self.assertEqual(self.db.load(aid),done)
  await b.send(op='journal.claim',id='first_capture');await b.until('error');self.assertEqual(self.db.load(bid),other);packets=await b.barrier();self.assertFalse([p for p in packets if p['type']=='state'])
  await self.close_account(a,aid);a,rejoined,reloaded=await self.auth('Akumavenom','fr_4','login');self.assertEqual(rejoined,aid);self.assertEqual(reloaded['money'],done['money']);self.assertTrue(next(g for g in reloaded['adventure']['goals'] if g['id']=='first_capture')['claimed']);self.assertEqual(self.db.load(aid)['creatures'],done['creatures'])

if __name__=='__main__':unittest.main()
