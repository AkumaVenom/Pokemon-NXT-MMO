#!/usr/bin/env python3
"""Pokemon NXT MMO world service. Run from the supplied Windows command launcher."""
from __future__ import annotations
import argparse,asyncio,configparser,contextlib,copy,importlib.util,ipaddress,json,logging,logging.handlers,os,re,shlex,signal,sys,tempfile,threading,time,traceback
from pathlib import Path
from aiohttp import web,WSMsgType
from nxt.config import Settings
from nxt.admin_console import LocalAdmin,RESTART_EXIT_CODE
from nxt.content import Content
from nxt.store import Store,WorldLeaseBusy,WorldSchemaUpgradeBusy
from nxt.world import World
from nxt.async_tasks import complete_before_cancelling
from nxt.security import RequestError,require,credentials,password_hash,password_verify,Bucket
from nxt.tls import TLSConfigurationError,load_server_tls
def reject_json_constant(value):raise ValueError('Non-finite JSON number')
VERSION='0.6.5-alpha'; ROOT=Path(__file__).resolve().parent
log=logging.getLogger('nxt')
_UNLOADED_TLS=object()
class WorldStartupError(RuntimeError):
 """Operator-facing startup guidance containing no database credentials."""
def configure_logging(config_path):
 """Create the log before reading configuration, content or opening a database."""
 preferred=config_path.resolve().parent/'logs'/'world.log';failure=None
 fallback=Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir())/'PokemonNXTMMO'/'logs'/f'world-{os.getpid()}.log'
 for path in (preferred,fallback):
  try:
   path.parent.mkdir(parents=True,exist_ok=True)
   file_handler=logging.handlers.RotatingFileHandler(path,maxBytes=4_000_000,backupCount=5,encoding='utf-8')
   break
  except OSError as e:failure=type(e).__name__
 else:
  logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',handlers=[logging.StreamHandler()],force=True)
  log.error('Cannot create a world log in either log directory (%s). Check folder permissions and disk space.',failure)
  return None
 logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',handlers=[logging.StreamHandler(),file_handler],force=True)
 if path!=preferred:log.warning('The server log folder is unavailable (%s); using %s',failure,path.resolve())
 log.info('World log: %s',path.resolve())
 return path.resolve()
def failure_summary(error,phase):
 """Report useful diagnostics without serializing passwords, SQL or config lines."""
 kind=type(error).__name__;code=error.args[0] if error.args and type(error.args[0]) is int else None
 if isinstance(error,(WorldStartupError,TLSConfigurationError,WorldSchemaUpgradeBusy)):return str(error)
 if type(error) is RuntimeError and str(error) in (
  'PyMySQL is missing. Run 1 - Install Server Dependencies.cmd.',
  'Database is not configured. Run 2 - Configure MySQL.cmd.',
  'Database is newer than this server; do not downgrade.'):
  return str(error)
 if phase=='opening database' or type(error).__module__.startswith(('pymysql','sqlite3')):
  hints={1044:'Database account does not have access to the configured database.',1045:'Database authentication was rejected; check the configured account and password.',1049:'The configured database does not exist; run Configure MySQL.',2002:'Cannot connect to MySQL; check that it is running and the configured host/port.',2003:'Cannot connect to MySQL; check that it is running and the configured host/port.'}
  return f'{kind}'+(f' (database error {code})' if code is not None else '')+': '+hints.get(code,'Check MySQL availability, configuration and database permissions. No database fallback was used.')
 if phase=='acquiring world ownership':return f'{kind}: World database ownership could not be acquired. Another world may still be running; check the other server consoles before retrying.'
 if phase=='reading configuration':return f'{kind}: Cannot read the server configuration. Check the config.ini file and its section names, values and syntax.'
 if phase=='loading world content':return f'{kind}: Cannot load data/world.json. Extract the complete matching server package and keep its data folder beside config.ini.'
 if phase=='loading trusted extensions':return f'{kind}: A trusted server extension failed to load. Check the extension filename above and the logged code locations.'
 if phase=='loading TLS certificate and private key':return f'{kind}: Cannot load TLS files. Check the network certificate/private_key paths, file permissions and certificate/key pair.'
 if isinstance(error,OSError):
  number=getattr(error,'winerror',None) or error.errno
  hints={13:'Access denied. Check folder permissions.',48:'The listen port is already in use. Stop the other listener or choose an unused world port in config.ini.',98:'The listen port is already in use. Stop the other listener or choose an unused world port in config.ini.',10048:'The listen port is already in use. Stop the other listener or choose an unused world port in config.ini.',99:'The configured listen IP is not available on this computer. Use this computer\'s LAN address or 0.0.0.0 as bind_ip.',10049:'The configured listen IP is not available on this computer. Use this computer\'s LAN address or 0.0.0.0 as bind_ip.',2:'A required file or folder is missing.'}
  return f'{kind}'+(f' (OS error {number})' if number is not None else '')+': '+hints.get(number,'Check the configured files, listen address and port.')
 return f'{kind}: Failure while {phase}. Review the configuration and the logged code locations.'
def record_failure(error,phase):
 # Traceback locations deliberately exclude source lines and exception reprs: both
 # can contain database credentials supplied by a driver or malformed config file.
 locations=' -> '.join(f'{frame.filename}:{frame.lineno} in {frame.name}' for frame in traceback.extract_tb(error.__traceback__))
 log.error('WORLD FAILURE while %s: %s%s',phase,failure_summary(error,phase),f' | Code locations: {locations}' if locations else '')
class Service:
 def __init__(self,settings,content,store,*,tls_context=_UNLOADED_TLS):
  self.s=settings;self.c=content;self.db=store;self.world=World(content,store,settings);self.stop=asyncio.Event();self.hash_slots=asyncio.Semaphore(2);self.pending=0;self.auth_rates={};self.sockets={};self.tasks=[];self.dummy=None
  self._tls_context=tls_context;self.restart_requested=False;self.admin_disconnect_tasks=set()
  self.console_commands=LocalAdmin(self)
 async def health(self,request):
  return web.json_response({'game':'Pokemon NXT MMO','version':VERSION,'status':'stopping' if self.world.stopping else 'online','online':len(self.world.players),'capacity':self.s.max_players,'pack':self.c.pack},headers={'Cache-Control':'no-store'})
 async def hash(self,pw,encoded=None):
  async with self.hash_slots:return await asyncio.to_thread(password_verify,pw,encoded) if encoded is not None else await asyncio.to_thread(password_hash,pw)
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
  ws=web.WebSocketResponse(protocols=('nxt.v1',),max_msg_size=self.s.int('security','max_packet_bytes'),heartbeat=20,receive_timeout=90,compress=False)
  await ws.prepare(request);p=None;writer=None;self.pending+=1;pending=True
  try:
   await ws.send_json({'type':'hello','game':'Pokemon NXT MMO','version':VERSION,'pack':self.c.pack,'world':self.s.get('world','name'),'online':len(self.world.players),'cap':self.s.max_players})
   message=await asyncio.wait_for(ws.receive(),timeout=60)
   require(message.type==WSMsgType.TEXT,'Login was cancelled.')
   try:d=json.loads(message.data,parse_constant=reject_json_constant)
   except (ValueError,TypeError):raise RequestError('Invalid login packet.')
   require(isinstance(d,dict) and d.get('op')=='auth','Log in before sending gameplay commands.')
   if not bucket.take():
    wait_seconds=max(1,int((1-bucket.tokens)/bucket.rate)+1)
    raise RequestError(f'Too many login attempts from this network. Wait {wait_seconds} seconds, then try again.')
   username,password=credentials(d.get('username'),d.get('password'))
   require(d.get('pack')==self.c.pack,'Client content is out of date. Install the matching client pack.')
   require(d.get('mode') in ('register','login'),'Invalid login mode.')
   require(len(self.world.players)<self.s.max_players,'The world is full. Try again later.')
   if d['mode']=='register':
    require(self.s.flag('world','registration_enabled'),'Account registration is disabled.')
    state=self.world.initial(username,d.get('home'),d.get('starter'),d.get('appearance',0))
    encoded=await self.hash(password);uid=await asyncio.to_thread(self.db.create,username,encoded,state)
   else:
    account=await asyncio.to_thread(self.db.account,username)
    verified=await self.hash(password,account['password_hash'] if account else self.dummy)
    require(account is not None and verified,'Username or password is incorrect.')
    require(not account['banned'],'This account has been banned. Contact the server administrator.')
    # Loading under World.join's lock prevents an overlapping old logout from
    # saving newer progress between this read and admission of the new session.
    uid=account['id'];username=account['username'];state=None;encoded=account['password_hash']
   password=None;d=None
   queue=asyncio.Queue(maxsize=self.s.int('security','max_outbound_messages'))
   p=await self.world.join(uid,username,state,queue,auth_hash=encoded);p.connection_peer=peer;self.sockets[uid]=ws;encoded=None
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
    if self.world.stopping:break
    if message.type==WSMsgType.TEXT:
     try:
      packet=json.loads(message.data,parse_constant=reject_json_constant);require(isinstance(packet,dict) and isinstance(packet.get('op'),str),'Invalid command packet.')
      await complete_before_cancelling(self.world.dispatch(p,packet))
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
   async def finish_connection():
    if pending:self.pending-=1
    try:
     if p:await self.world.leave(p)
    finally:
     if p and self.sockets.get(p.id) is ws:self.sockets.pop(p.id,None)
     if writer:
      writer.cancel()
      with contextlib.suppress(asyncio.CancelledError,Exception):await writer
     if not ws.closed:await ws.close()
   await complete_before_cancelling(finish_connection())
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
  """Trusted local console entry. Never called by HTTP, WebSocket or chat."""
  return await self.console_commands.execute(line,output=lambda text:print(text,flush=True))
 async def console(self):
  return await self.console_commands.console()
 async def acquire_world_lease(self):
  """Wait only for an unrefreshed lease; never evict another running world."""
  deadline=time.monotonic()+65;first_heartbeat=None;waiting=False
  while not self.stop.is_set():
   # A cancelled to_thread await leaves its worker running. Finish this short
   # transaction before run() closes the store so it cannot acquire a late lease.
   attempt=asyncio.create_task(asyncio.to_thread(self.db.acquire_lease))
   try:
    try:await asyncio.shield(attempt)
    except asyncio.CancelledError:
     with contextlib.suppress(Exception):await attempt
     raise
   except WorldLeaseBusy as e:
    if e.remaining_seconds>60:raise WorldStartupError('The stored world lease is dated in the future. Check the clocks on both server computers and stop any other running world before retrying.') from None
    if first_heartbeat is not None and e.heartbeat>first_heartbeat:raise WorldStartupError('Another NXT world is still refreshing its database lease. Stop that world first, then restart this server.') from None
    if first_heartbeat is None:first_heartbeat=e.heartbeat
    budget=deadline-time.monotonic()
    if budget<=0:raise WorldStartupError('World database ownership is still unavailable after waiting. Check for another running NXT world and verify the server clock before retrying.') from None
    delay=min(5,e.remaining_seconds,budget);waiting=True
    log.warning('World database lease is occupied: another world may be active, or an earlier process may have stopped unexpectedly. Waiting for safe expiry (about %d seconds remaining); no lease will be forcibly removed.',e.remaining_seconds)
    await asyncio.sleep(delay)
   else:
    if waiting:log.info('World database ownership recovered after the previous lease ended.')
    return
  raise asyncio.CancelledError
 async def run(self,no_console=False):
  runner=None;site=None;console_task=None;listening=False;failure=None;self.phase='loading TLS certificate and private key'
  try:
   # main() validates before opening storage. Direct Service callers get the
   # same preflight before any ownership lease is acquired.
   tls=load_server_tls(self.s) if self._tls_context is _UNLOADED_TLS or (self.s.flag('network','tls') and self._tls_context is None) else self._tls_context
   self.phase='initializing authentication'
   self.dummy=await self.hash('UnusedTimingOnly_'+os.urandom(16).hex())
   self.phase='acquiring world ownership';log.info('Acquiring exclusive world database ownership.')
   await self.acquire_world_lease()
   self.phase='initializing autonomous trainers';await self.world.autonomous.initialize()
   self.phase='loading trusted extensions'
   extension_dir=self.s.path('extensions','directory');extension_dir.mkdir(exist_ok=True)
   for path in sorted(extension_dir.glob('*.py')):
    if path.name.startswith('_'):continue
    log.info('Loading trusted extension %s',path.name)
    spec=importlib.util.spec_from_file_location('nxt_extension_'+path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if callable(getattr(module,'register',None)):module.register(self.world);log.info('Loaded trusted extension %s',path.name)
   self.phase='preparing the network listener'
   app=web.Application(client_max_size=self.s.int('security','max_packet_bytes'));app.router.add_get('/health',self.health);app.router.add_get('/world',self.socket)
   runner=web.AppRunner(app,access_log=None);await runner.setup()
   self.phase='binding the world listen address'
   log.info('Binding world listener at %s:%s.',self.s.bind_ip,self.s.port)
   site=web.TCPSite(runner,self.s.bind_ip,self.s.port,ssl_context=tls);await site.start();listening=True
   print('\n'+'='*66+'\n  POKEMON NXT MMO | WORLD SERVER | '+VERSION+'\n'+'='*66,flush=True)
   print(f'Listening: {self.s.bind_ip}:{self.s.port} ({"TLS" if tls else "PRIVATE LAN - PLAINTEXT"})\nDatabase: {self.s.get("database","backend")} | Capacity hard limit: {self.s.max_players}\nContent: {len(self.c.maps)} maps | pack {self.c.pack}\nType help for administrator commands. Ctrl+C safely stops the world.\n',flush=True)
   if not self.db.mysql:print('DEVELOPER SQLITE MODE: this is NOT the MySQL deployment.\n',flush=True)
   self.tasks=[asyncio.create_task(self.periodic('tick',1/self.s.tick_hz)),asyncio.create_task(self.periodic('save',self.s.save_seconds)),asyncio.create_task(self.periodic('lease',10))]
   if not no_console:
    console_task=asyncio.create_task(self.console());self.tasks.append(console_task)
   loop=asyncio.get_running_loop()
   for sig in (signal.SIGINT,signal.SIGTERM):
    try:loop.add_signal_handler(sig,self.stop.set)
    except NotImplementedError:signal.signal(sig,lambda *_:loop.call_soon_threadsafe(self.stop.set))
   self.phase='running the world';log.info('World online. Database ownership acquired and network listener ready.')
   await self.stop.wait()
  except BaseException as e:
   failure=e
   if isinstance(e,Exception):record_failure(e,self.phase)
   raise
  finally:
   # Every path after Store creation releases its own lease and database handle,
   # including extension, TLS and bind failures before the server is listening.
   self.world.stopping=True;self.stop.set();cleanup_errors=[]
   async def cleanup(label,operation):
    try:await operation
    except Exception as e:cleanup_errors.append(e);record_failure(e,label)
   if listening:log.info('World shutdown: stopping new work and saving characters.')
   if site is not None:await cleanup('stopping the network listener',site.stop())
   if console_task is not None:console_task.cancel()
   await cleanup('closing console schedules',self.console_commands.close())
   # Let in-flight database tasks finish. Cancelling to_thread() does not stop
   # its worker, so it must not race lease release or closing the connection.
   if self.tasks:await asyncio.gather(*self.tasks,return_exceptions=True)
   if listening:
    for p in list(self.world.players.values()):p.send('notice',message='World server is shutting down. Your character is being saved.')
    await cleanup('saving characters at shutdown',self.world.save_all())
    await asyncio.gather(*(ws.close(code=1001,message=b'World shutdown') for ws in list(self.sockets.values())),return_exceptions=True)
   if self.admin_disconnect_tasks:await asyncio.gather(*self.admin_disconnect_tasks,return_exceptions=True)
   if runner is not None:await cleanup('cleaning up network connections',runner.cleanup())
   await cleanup('closing the database and releasing world ownership',asyncio.to_thread(self.db.close))
   if cleanup_errors and failure is None:
    self.phase='shutting down the world'
    raise RuntimeError('World shutdown encountered errors; review the world log.') from None
   if not cleanup_errors:log.info('World resources closed; owned database lease released.')
async def main(argv=None):
 parser=argparse.ArgumentParser(description='Pokemon NXT MMO dedicated world server');parser.add_argument('--config',type=Path,default=ROOT/'config.ini');parser.add_argument('--dev-sqlite',action='store_true',help='Explicitly use separate developer SQLite state; never MySQL fallback');parser.add_argument('--no-console',action='store_true');args=parser.parse_args(argv)
 log_path=configure_logging(args.config);phase='reading configuration';service=None;db=None
 try:
  log.info('Starting world server %s. Configuration: %s',VERSION,args.config.resolve())
  s=Settings.load(args.config)
  if args.dev_sqlite:s.config.set('database','backend','sqlite')
  phase='loading TLS certificate and private key'
  tls=load_server_tls(s)
  if tls is not None:log.info('TLS certificate/key preflight passed. Player clients must trust the issuer and use the certificate hostname/IP.')
  phase='loading world content';log.info('Loading world content.')
  c=Content(s.root/'data/world.json')
  phase='opening database';log.info('Opening configured %s database.',s.get('database','backend'))
  opening=asyncio.create_task(asyncio.to_thread(Store,s))
  try:db=await asyncio.shield(opening)
  except asyncio.CancelledError:
   # A cancelled await does not stop its database worker. Recover its result
   # and close it before exiting, even though no world lease exists yet.
   try:db=await opening
   except Exception as e:record_failure(e,phase)
   if db is not None:
    try:await asyncio.to_thread(db.close)
    except Exception as e:record_failure(e,'closing database after cancelled startup')
   log.info('World startup cancelled; pending database setup completed and cleaned up.')
   raise
  phase='constructing the world service';service=Service(s,c,db,tls_context=tls)
  service.console_commands.config_path=args.config.resolve();service.console_commands.original_config=service.console_commands._read_config(args.config)
  await service.run(args.no_console)
  return RESTART_EXIT_CODE if service.restart_requested else 0
 except Exception as e:
  if service is None:
   record_failure(e,phase)
   if db is not None:
    try:await asyncio.to_thread(db.close)
    except Exception as close_error:record_failure(close_error,'closing database after startup failure')
  else:phase=service.phase
  location=str(log_path) if log_path else 'Log file unavailable; read the console errors above.'
  print(f'\nWORLD STARTUP / SHUTDOWN FAILED: {failure_summary(e,phase)}\nWorld log: {location}\nNo database fallback was used.',file=sys.stderr,flush=True)
  return 1
if __name__=='__main__':
 try:sys.exit(asyncio.run(main()))
 except KeyboardInterrupt:pass
