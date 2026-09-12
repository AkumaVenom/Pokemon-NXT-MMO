"""Real TCP/WebSocket integration tests with isolated SQLite state (not a browser bridge).
No MySQL, Windows launch, TLS certificate deployment or 1,000-connection load claim.
"""
from __future__ import annotations
import asyncio,dataclasses,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
import aiohttp
from aiohttp import web
from server import Service
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.security import password_hash
PASSWORD='Network_Alpha_Test_987!'
ORIGIN='http://127.0.0.1:45210'
class NetworkTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):
  cls.content=Content(ROOT/'Server/data/world.json');cls.hashed=password_hash(PASSWORD)
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();p=Path(self.tmp.name)/'config.ini';p.write_text((ROOT/'Server/config.ini').read_text());self.s=Settings.load(p);self.s.config.set('database','backend','sqlite');self.s.config.set('security','auth_attempts_per_minute','100');self.s=dataclasses.replace(self.s,encounter_chance=0)
  self.db=Store(self.s);self.db.acquire_lease();self.service=Service(self.s,self.content,self.db);self.service.dummy=self.hashed
  for name in ('NetworkAlice','NetworkBobby'):
   self.db.create(name,self.hashed,self.service.world.initial(name,'Kanto','fr_1',0))
  app=web.Application();app.router.add_get('/health',self.service.health);app.router.add_get('/world',self.service.socket);self.runner=web.AppRunner(app);await self.runner.setup();site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start();port=site._server.sockets[0].getsockname()[1];self.base=f'http://127.0.0.1:{port}';self.session=aiohttp.ClientSession();self.sockets=[]
 async def asyncTearDown(self):
  for ws in self.sockets:await ws.close()
  await self.session.close();await self.runner.cleanup();self.db.close();self.tmp.cleanup()
 async def connect(self):
  ws=await self.session.ws_connect(self.base+'/world',headers={'Origin':ORIGIN},protocols=('nxt.v1',));self.sockets.append(ws);hello=await ws.receive_json(timeout=3);self.assertEqual(hello['type'],'hello');self.assertEqual(hello['cap'],1000);return ws
 async def until(self,ws,kind):
  for _ in range(25):
   v=await ws.receive_json(timeout=5)
   if v.get('type')==kind:return v
  self.fail('Expected packet '+kind)
 async def login(self,name='NetworkAlice',password=PASSWORD,pack=None,mode='login'):
  ws=await self.connect();await ws.send_json({'op':'auth','mode':mode,'username':name,'password':password,'pack':pack or self.content.pack,'home':'Kanto','starter':'fr_1','appearance':0});return ws
 async def test_health_identifies_world_and_content(self):
  async with self.session.get(self.base+'/health')as r:
   d=await r.json();self.assertEqual(r.status,200);self.assertEqual(d['game'],'Pokemon NXT MMO');self.assertEqual(d['capacity'],1000);self.assertEqual(d['pack'],self.content.pack);self.assertEqual(r.headers['Cache-Control'],'no-store')
 async def test_untrusted_web_origin_is_rejected(self):
  with self.assertRaises(aiohttp.WSServerHandshakeError)as e:await self.session.ws_connect(self.base+'/world',headers={'Origin':'https://untrusted.example'},protocols=('nxt.v1',))
  self.assertEqual(e.exception.status,403)
 async def test_gameplay_before_login_is_rejected(self):
  ws=await self.connect();await ws.send_json({'op':'move','direction':'right','seq':1});d=await self.until(ws,'error');self.assertTrue(d['login']);self.assertIn('Log in',d['message']);self.assertEqual(len(self.service.world.players),0)
 async def test_mismatched_content_is_rejected(self):
  ws=await self.login(pack='not-the-current-pack');d=await self.until(ws,'error');self.assertIn('out of date',d['message']);self.assertEqual(len(self.service.world.players),0)
 async def test_password_and_unknown_account_rejection(self):
  for name in ('NetworkAlice','DoesNotExist'):
   ws=await self.login(name,password='Definitely_wrong_997!');d=await self.until(ws,'error');self.assertEqual(d['message'],'Username or password is incorrect.')
 async def test_register_login_and_unique_active_account(self):
  ws=await self.login('NewNetworkTrainer',mode='register');joined=await self.until(ws,'joined');self.assertEqual(joined['username'],'NewNetworkTrainer');self.assertIsNotNone(self.db.account('newnetworktrainer'))
  second=await self.login('NewNetworkTrainer');d=await self.until(second,'error');self.assertIn('already',d['message'].lower());self.assertEqual(len(self.service.world.players),1)
 async def test_real_two_client_movement_replication_and_global_chat(self):
  a=await self.login();await self.until(a,'joined');b=await self.login('NetworkBobby');await self.until(b,'joined');await self.until(a,'state');await self.until(b,'state')
  await a.send_json({'op':'move','seq':1,'direction':'right'});await asyncio.sleep(.08);await self.service.world.tick();scene=await self.until(b,'scene');alice=next(p for p in scene['players'] if p['username']=='NetworkAlice');self.assertEqual((alice['x'],alice['y']),(11,10));self.assertEqual((alice['fx'],alice['fy']),(10,10));self.assertIn('follower',alice)
  await a.send_json({'op':'chat','channel':'trade','text':'Trading a Potion','username':'Forged'});chat=await self.until(b,'chat');self.assertEqual(chat['username'],'NetworkAlice');self.assertEqual(chat['channel'],'trade');self.assertEqual(chat['text'],'Trading a Potion')
 async def test_malformed_and_nonfinite_commands_fail_without_movement(self):
  ws=await self.login();await self.until(ws,'state')
  for raw in ('[]','{"op":"move","seq":NaN,"direction":"right"}','{"op":7}'):
   await ws.send_str(raw);d=await self.until(ws,'error');self.assertIn('command',d['message'].lower())
  p=next(iter(self.service.world.players.values()));self.assertEqual((p.state['x'],p.state['y']),(10,10))
 async def test_oversized_packet_closes_connection(self):
  ws=await self.connect();await ws.send_str('x'*9000);msg=await ws.receive(timeout=3);self.assertIn(msg.type,(aiohttp.WSMsgType.CLOSE,aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.ERROR));self.assertEqual(len(self.service.world.players),0)
 async def test_disconnected_character_can_rejoin_saved_location(self):
  ws=await self.login();await self.until(ws,'state');await ws.send_json({'op':'move','seq':1,'direction':'right'});await asyncio.sleep(.08);await ws.close()
  for _ in range(30):
   if not self.service.world.players:break
   await asyncio.sleep(.02)
  second=await self.login();d=await self.until(second,'map');self.assertEqual((d['entity']['x'],d['entity']['y']),(11,10))
if __name__=='__main__':unittest.main()
