#!/usr/bin/env python3
"""Pokemon NXT MMO world service. Run from the supplied Windows command launcher."""
from __future__ import annotations
import argparse,asyncio,configparser,contextlib,copy,importlib.util,ipaddress,json,logging,logging.handlers,os,re,shlex,signal,ssl,sys,threading,time
from pathlib import Path
from aiohttp import web,WSMsgType
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.world import World
from nxt.security import RequestError,require,credentials,password_hash,password_verify,Bucket
def reject_json_constant(value):raise ValueError('Non-finite JSON number')
VERSION='0.1.0-alpha'; ROOT=Path(__file__).resolve().parent
log=logging.getLogger('nxt')
class Service:
 def __init__(self,settings,content,store):
  self.s=settings;self.c=content;self.db=store;self.world=World(content,store,settings);self.stop=asyncio.Event();self.hash_slots=asyncio.Semaphore(2);self.pending=0;self.auth_rates={};self.sockets={};self.tasks=[];self.dummy=None
 async def health(self,request):
  return web.json_response({'game':'Pokemon NXT MMO','version':VERSION,'status':'stopping' if self.world.stopping else 'online','online':len(self.world.players),'capacity':self.s.max_players,'pack':self.c.pack},headers={'Cache-Control':'no-store'})
 async def hash(self,pw,encoded=None):
  async with self.hash_slots:return await asyncio.to_thread(password_verify,pw,encoded) if encoded else await asyncio.to_thread(password_hash,pw)
 async def socket(self,request):
  origin=request.headers.get('Origin','')
  if not re.fullmatch(self.s.get('security','allowed_origin_pattern'),origin):raise web.HTTPForbidden(text='Connect using the Pokemon NXT MMO client.')
  peer=request.remote or ''
  try:private=ipaddress.ip_address(peer).is_private or ipaddress.ip_address(peer).is_loopback
  except ValueError:private=False
  if not self.s.flag('network','tls') and not private:raise web.HTTPForbidden(text='Public connections require TLS.')
  if self.pending>=self.s.int('network','max_pending_connections'):raise web.HTTPServiceUnavailable(text='Login queue is full.')
  if self.world.stopping:raise web.HTTPServiceUnavailable(text='World is shutting down.')
  if len(self.auth_rates)>4096:
   now=time.monotonic();self.auth_rates={k:v for k,v in self.auth_rates.items() if now-v.at<300}
   if len(self.auth_rates)>4096:raise web.HTTPTooManyRequests()
  bucket=self.auth_rates.setdefault(peer,Bucket(self.s.int('security','auth_attempts_per_minute'),60))
  if not bucket.take():raise web.HTTPTooManyRequests(text='Too many login attempts. Please wait a minute.')
  ws=web.WebSocketResponse(protocols=('nxt.v1',),max_msg_size=self.s.int('security','max_packet_bytes'),heartbeat=20,receive_timeout=90,compress=False)
  await ws.prepare(request);p=None;writer=None;self.pending+=1;pending=True
  try:
   await ws.send_json({'type':'hello','game':'Pokemon NXT MMO','version':VERSION,'pack':self.c.pack,'world':self.s.get('world','name'),'online':len(self.world.players),'cap':self.s.max_players})
   message=await asyncio.wait_for(ws.receive(),timeout=60)
   require(message.type==WSMsgType.TEXT,'Login was cancelled.')
   try:d=json.loads(message.data,parse_constant=reject_json_constant)
   except (ValueError,TypeError):raise RequestError('Invalid login packet.')
   require(isinstance(d,dict) and d.get('op')=='auth','Log in before sending gameplay commands.')
   username,password=credentials(d.get('username'),d.get('password'))
   require(d.get('pack')==self.c.pack,'Client content is out of date. Install the matching client pack.')
   require(d.get('mode') in ('register','login'),'Invalid login mode.')
   require(len(self.world.players)<self.s.max_players,'The world is full. Try again later.')
   if d['mode']=='register':
    require(self.s.flag('world','registration_enabled'),'Account registration is disabled.')
    state=self.world.initial(username,d.get('home','Kanto'),d.get('starter','fr_1'),d.get('appearance',0))
    encoded=await self.hash(password);uid=await asyncio.to_thread(self.db.create,username,encoded,state)
   else:
    account=await asyncio.to_thread(self.db.account,username)
    verified=await self.hash(password,account['password_hash'] if account else self.dummy)
    require(account is not None and verified,'Username or password is incorrect.')
    require(not account['banned'],'This account has been banned. Contact the server administrator.')
    uid=account['id'];username=account['username'];state=await asyncio.to_thread(self.db.load,uid)
   password=None;d=None
   queue=asyncio.Queue(maxsize=self.s.int('security','max_outbound_messages'))
   p=await self.world.join(uid,username,state,queue);self.sockets[uid]=ws
   self.pending-=1;pending=False
   async def pump():
    try:
     while not ws.closed and not p.closed:
      try:packet=await asyncio.wait_for(queue.get(),1)
      except asyncio.TimeoutError:continue
      await asyncio.wait_for(ws.send_json(packet),10)
    except (ConnectionError,asyncio.TimeoutError):pass
    finally:
     if p.closed or not ws.closed:await ws.close(code=1001,message=b'Connection ended')
   writer=asyncio.create_task(pump())
   async for message in ws:
    if message.type==WSMsgType.TEXT:
     try:
      packet=json.loads(message.data,parse_constant=reject_json_constant);require(isinstance(packet,dict) and isinstance(packet.get('op'),str),'Invalid command packet.')
      await self.world.dispatch(p,packet)
     except RequestError as e:p.send('error',message=str(e))
     except (ValueError,TypeError,KeyError,OverflowError) as e:
      log.warning('Rejected command structure from account %d (%s)',p.id,type(e).__name__);p.send('error',message='Malformed command. No requested change was accepted.')
     except Exception:
      log.exception('Command failed for account %s',p.id);p.send('error',message='The server could not complete that action. Contact the administrator.')
    elif message.type in (WSMsgType.ERROR,WSMsgType.CLOSE,WSMsgType.CLOSED):break
  except RequestError as e:
   if not ws.closed:await ws.send_json({'type':'error','message':str(e),'login':True})
  except asyncio.TimeoutError:
   if not ws.closed:await ws.send_json({'type':'error','message':'Login timed out. Reconnect to try again.','login':True})
  except (ConnectionError,asyncio.CancelledError):pass
  except Exception:
   log.exception('Connection failure')
   if not ws.closed:await ws.send_json({'type':'error','message':'Server storage or authentication is unavailable. Contact the administrator.','login':True})
  finally:
   if pending:self.pending-=1
   if p:
    await self.world.leave(p);self.sockets.pop(p.id,None)
   if writer:
    writer.cancel()
    with contextlib.suppress(asyncio.CancelledError,Exception):await writer
   if not ws.closed:await ws.close()
  return ws
 async def periodic(self,kind,seconds):
  while not self.stop.is_set():
   start=time.monotonic()
   try:
    if kind=='tick':await self.world.tick()
    elif kind=='save':await self.world.save_all()
    else:await asyncio.to_thread(self.db.heartbeat)
   except Exception:
    log.exception('%s service failed',kind)
    if kind in ('lease','save'):
     log.critical('Stopping world rather than accepting unsaved or conflicting ownership changes.');self.stop.set();break
   try:await asyncio.wait_for(self.stop.wait(),max(.005,seconds-(time.monotonic()-start)))
   except asyncio.TimeoutError:pass
 async def admin(self,line):
  try:
   parts=shlex.split(line);cmd=parts[0].lower() if parts else '';args=parts[1:]
   if not cmd:return
   if cmd=='help':print('\nCommands: help | status | players | save | announce <message> | kick <username>\n  ban <username> | unban <username> | mute <username> <seconds>\n  teleport <username> <map_id> | spawnwild <username> <species_key> <level>\n  shutdown\n',flush=True)
   elif cmd=='status':print(f'Online {len(self.world.players)}/{self.s.max_players} | maps {len(self.c.maps)} | battles {len(self.world.battles)} | trades {len(self.world.trades)} | tick {self.world.last_tick_ms:.2f}ms (max {self.world.max_tick_ms:.2f}ms) | uptime {int(time.monotonic()-self.world.started)}s',flush=True)
   elif cmd=='players':
    for p in self.world.players.values():print(f'{p.id:6} {p.username:20} {p.state["map"]:18} ({p.state["x"]},{p.state["y"]})',flush=True)
   elif cmd=='save':print(f'Saved {await self.world.save_all()} changed characters.',flush=True)
   elif cmd=='announce':
    text=' '.join(args)[:240];require(bool(text),'Usage: announce <message>')
    for p in self.world.players.values():p.send('notice',message='ADMIN: '+text)
   elif cmd in ('ban','unban'):
    require(len(args)==1,f'Usage: {cmd} <username>');count=await asyncio.to_thread(self.db.ban,args[0],cmd=='ban');print(f'Updated {count} account(s).',flush=True)
    if cmd=='ban':await self.kick(args[0],'Your account was banned by the administrator.')
   elif cmd=='kick':require(len(args)==1,'Usage: kick <username>');await self.kick(args[0],'Disconnected by the administrator.')
   elif cmd in ('mute','teleport','spawnwild'):
    require(len(args)>=2,f'Usage: {cmd} <username> <argument>');p=next((p for p in self.world.players.values() if p.username.lower()==args[0].lower()),None);require(p is not None,'Trainer is not online.')
    async with self.world.lock:
     if cmd=='mute':p.muted_until=time.monotonic()+max(0,min(int(args[1]),86400));p.send('notice',message='Your chat permissions were updated by the administrator.')
     elif cmd=='teleport':self.world.free(p);self.world.relocate(p,args[1])
     else:require(len(args)==3 and args[1] in self.c.species,'Usage: spawnwild <username> <species_key> <level>');level=int(args[2]);require(1<=level<=100,'Level must be 1..100.');await self.world.start_wild(p,(args[1],level))
   elif cmd in ('shutdown','stop','quit'):self.stop.set()
   else:print('Unknown command. Type help.',flush=True)
  except (RequestError,ValueError) as e:print(f'Admin: {e}',flush=True)
  except Exception:log.exception('Admin command failed')
 async def kick(self,name,message):
  p=next((p for p in self.world.players.values() if p.username.lower()==name.lower()),None)
  if p and p.id in self.sockets:
   await self.sockets[p.id].send_json({'type':'notice','message':message});await self.sockets[p.id].close(code=1008,message=b'Administrator action')
 async def console(self):
  queue=asyncio.Queue();loop=asyncio.get_running_loop()
  def reader():
   try:
    for line in sys.stdin:
     if loop.is_closed():break
     loop.call_soon_threadsafe(queue.put_nowait,line.strip())
   except (OSError,ValueError):pass
  threading.Thread(target=reader,name='NXT-Admin-Console',daemon=True).start()
  while not self.stop.is_set():await self.admin(await queue.get())
 async def run(self,no_console=False):
  self.dummy=await self.hash('UnusedTimingOnly_'+os.urandom(16).hex())
  await asyncio.to_thread(self.db.acquire_lease)
  extension_dir=self.s.path('extensions','directory');extension_dir.mkdir(exist_ok=True)
  for path in sorted(extension_dir.glob('*.py')):
   if path.name.startswith('_'):continue
   spec=importlib.util.spec_from_file_location('nxt_extension_'+path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
   if callable(getattr(module,'register',None)):module.register(self.world);log.info('Loaded trusted extension %s',path.name)
  app=web.Application(client_max_size=self.s.int('security','max_packet_bytes'));app.router.add_get('/health',self.health);app.router.add_get('/world',self.socket)
  runner=web.AppRunner(app,access_log=None);await runner.setup();tls=None
  if self.s.flag('network','tls'):
   tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.minimum_version=ssl.TLSVersion.TLSv1_2;tls.load_cert_chain(self.s.path('network','certificate'),self.s.path('network','private_key'))
  site=web.TCPSite(runner,self.s.bind_ip,self.s.port,ssl_context=tls);await site.start()
  print('\n'+'='*66+'\n  POKEMON NXT MMO | WORLD SERVER | '+VERSION+'\n'+'='*66,flush=True)
  print(f'Listening: {self.s.bind_ip}:{self.s.port} ({"TLS" if tls else "PRIVATE LAN - PLAINTEXT"})\nDatabase: {self.s.get("database","backend")} | Capacity hard limit: {self.s.max_players}\nContent: {len(self.c.maps)} maps | pack {self.c.pack}\nType help for administrator commands. Ctrl+C safely stops the world.\n',flush=True)
  if not self.db.mysql:print('DEVELOPER SQLITE MODE: this is NOT the MySQL deployment.\n',flush=True)
  self.tasks=[asyncio.create_task(self.periodic('tick',1/self.s.tick_hz)),asyncio.create_task(self.periodic('save',self.s.save_seconds)),asyncio.create_task(self.periodic('lease',10))]
  if not no_console:self.tasks.append(asyncio.create_task(self.console()))
  loop=asyncio.get_running_loop()
  for sig in (signal.SIGINT,signal.SIGTERM):
   try:loop.add_signal_handler(sig,self.stop.set)
   except NotImplementedError:signal.signal(sig,lambda *_:loop.call_soon_threadsafe(self.stop.set))
  try:await self.stop.wait()
  finally:
   self.world.stopping=True;log.info('World shutdown: stopping new work and saving characters.')
   for p in list(self.world.players.values()):p.send('notice',message='World server is shutting down. Your character is being saved.')
   await self.world.save_all()
   await asyncio.gather(*(ws.close(code=1001,message=b'World shutdown') for ws in list(self.sockets.values())),return_exceptions=True)
   for task in self.tasks:task.cancel()
   await asyncio.gather(*self.tasks,return_exceptions=True);await runner.cleanup();await asyncio.to_thread(self.db.close)
async def main():
 parser=argparse.ArgumentParser(description='Pokemon NXT MMO dedicated world server');parser.add_argument('--config',type=Path,default=ROOT/'config.ini');parser.add_argument('--dev-sqlite',action='store_true',help='Explicitly use separate developer SQLite state; never MySQL fallback');parser.add_argument('--no-console',action='store_true');args=parser.parse_args()
 s=Settings.load(args.config)
 if args.dev_sqlite:s.config.set('database','backend','sqlite')
 logs=s.root/'logs';logs.mkdir(exist_ok=True)
 handlers=[logging.StreamHandler(),logging.handlers.RotatingFileHandler(logs/'world.log',maxBytes=4_000_000,backupCount=5,encoding='utf-8')]
 logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',handlers=handlers)
 c=Content(s.root/'data/world.json');db=await asyncio.to_thread(Store,s);await Service(s,c,db).run(args.no_console)
if __name__=='__main__':
 try:asyncio.run(main())
 except KeyboardInterrupt:pass
 except Exception as e:print(f'\nWORLD STARTUP FAILED: {e}\nSee logs/world.log and Docs/QUICK_START.md. No database fallback was used.',file=sys.stderr);sys.exit(1)
