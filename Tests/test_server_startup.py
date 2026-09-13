"""Startup/cleanup regressions using temporary SQLite state and real local binds.
These do not claim Windows launcher execution or a production MySQL deployment.
"""
from __future__ import annotations
import asyncio,contextlib,dataclasses,io,logging,socket,sys,tempfile,threading,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'Server'))
import server
import doctor
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store,WorldLeaseBusy

class StartupTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):cls.content=Content(ROOT/'Server/data/world.json')
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.config=self.root/'config.ini'
  self.original=(ROOT/'Server/config.ini').read_bytes();self.config.write_bytes(self.original)
  settings=Settings.load(self.config);settings.config.set('database','backend','sqlite')
  self.settings=dataclasses.replace(settings,bind_ip='127.0.0.1',port=0)
  self.services=[]
 async def asyncTearDown(self):
  for service in self.services:
   service.stop.set()
   with contextlib.suppress(Exception):service.db.close()
  # main() owns root logging; close temporary test log files before cleanup.
  for handler in list(logging.getLogger().handlers):
   if isinstance(handler,logging.FileHandler) and str(self.root) in str(handler.baseFilename):logging.getLogger().removeHandler(handler);handler.close()
  self.assertEqual(self.config.read_bytes(),self.original,'Startup must not rewrite credentials or configuration.')
  self.tmp.cleanup()
 def make_service(self,settings=None):
  service=server.Service(settings or self.settings,self.content,Store(settings or self.settings));service.hash=mock.AsyncMock(return_value='test-timing-hash');self.services.append(service);return service
 async def assert_can_restart(self):
  service=self.make_service();original_acquire=service.acquire_world_lease
  # A new startup should really bind and tear down without waiting on old ownership.
  async def acquire_then_stop():await original_acquire();service.stop.set()
  service.acquire_world_lease=acquire_then_stop
  with contextlib.redirect_stdout(io.StringIO()):await service.run(no_console=True)
  self.assertTrue(service.world.stopping)
 async def test_real_bind_failure_logs_and_releases_lease_for_immediate_restart(self):
  with socket.socket() as occupied:
   occupied.bind(('127.0.0.1',0));occupied.listen();service=self.make_service(dataclasses.replace(self.settings,port=occupied.getsockname()[1]))
   with self.assertLogs('nxt',level='INFO') as captured:
    with self.assertRaises(OSError):await service.run(no_console=True)
  joined='\n'.join(captured.output);self.assertIn('binding the world listen address',joined);self.assertIn('port is already in use',joined)
  await self.assert_can_restart()
 async def test_extension_startup_failure_releases_lease(self):
  extensions=self.root/'extensions';extensions.mkdir();bad=extensions/'broken.py';bad.write_text("raise RuntimeError('extension configuration failed')\n")
  service=self.make_service()
  with self.assertLogs('nxt',level='ERROR') as captured:
   with self.assertRaises(RuntimeError):await service.run(no_console=True)
  self.assertIn('loading trusted extensions','\n'.join(captured.output));bad.unlink();await self.assert_can_restart()
 async def test_missing_tls_certificate_fails_before_lease_and_closes_store(self):
  self.settings.config.set('network','tls','true');service=self.make_service()
  with mock.patch.object(service,'acquire_world_lease',new=mock.AsyncMock()) as acquire,self.assertLogs('nxt',level='ERROR') as captured:
   with self.assertRaises(server.TLSConfigurationError):await service.run(no_console=True)
  acquire.assert_not_awaited();service.hash.assert_not_awaited();self.assertTrue(service.db.closed)
  joined='\n'.join(captured.output);self.assertIn(str(self.root/'certificates/server.crt'),joined);self.assertIn('2b - Configure Online Hosting.cmd',joined)
  self.settings.config.set('network','tls','false');await self.assert_can_restart()
 async def test_missing_tls_certificate_main_logs_exact_path_before_content_or_database(self):
  self.settings.config.set('network','tls','true')
  with mock.patch.object(server.Settings,'load',return_value=self.settings),mock.patch.object(server,'Content') as content,mock.patch.object(server,'Store') as store,contextlib.redirect_stderr(io.StringIO()) as output:
   result=await server.main(['--config',str(self.config),'--no-console'])
  self.assertEqual(result,1);content.assert_not_called();store.assert_not_called()
  text=(self.root/'logs/world.log').read_text()+output.getvalue();self.assertIn('loading TLS certificate and private key',text);self.assertIn(str(self.root/'certificates/server.crt'),text);self.assertIn('2b - Configure Online Hosting.cmd',text)
 def test_doctor_checks_tls_before_content_and_database(self):
  self.settings.config.set('network','tls','true')
  with mock.patch.object(doctor.Settings,'load',return_value=self.settings),mock.patch.object(doctor,'Content') as content,contextlib.redirect_stdout(io.StringIO()) as output:
   result=doctor.main(['--config',str(self.config)])
  self.assertEqual(result,1);content.assert_not_called();self.assertIn(str(self.root/'certificates/server.crt'),output.getvalue());self.assertIn('2b - Configure Online Hosting.cmd',output.getvalue())
 async def test_shutdown_save_failure_still_closes_listener_and_releases_lease(self):
  service=self.make_service();service.world.save_all=mock.AsyncMock(side_effect=RuntimeError('simulated failed final save'))
  original_acquire=service.acquire_world_lease
  async def acquire_then_stop():await original_acquire();service.stop.set()
  service.acquire_world_lease=acquire_then_stop
  with self.assertLogs('nxt',level='ERROR') as captured:
   with contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaisesRegex(RuntimeError,'shutdown encountered errors'):await service.run(no_console=True)
  self.assertIn('saving characters at shutdown','\n'.join(captured.output));await self.assert_can_restart()
 async def test_failed_config_creates_actual_log_before_parsing_without_password_leak(self):
  bad=self.root/'bad-config.ini';secret='SyntheticSecret_DoNotLog_123!';bad.write_text('[database]\npassword = '+secret+'\n'+secret+'\n')
  with contextlib.redirect_stderr(io.StringIO()) as output:result=await server.main(['--config',str(bad),'--no-console'])
  path=self.root/'logs/world.log';text=path.read_text();self.assertEqual(result,1);self.assertIn('reading configuration',text);self.assertIn(str(path),output.getvalue());self.assertNotIn(secret,text+output.getvalue());self.assertIn(secret,bad.read_text())
 async def test_missing_content_is_recorded_and_config_is_unchanged(self):
  with contextlib.redirect_stderr(io.StringIO()):result=await server.main(['--config',str(self.config),'--no-console'])
  self.assertEqual(result,1);self.assertIn('loading world content',(self.root/'logs/world.log').read_text())
 async def test_database_driver_error_does_not_log_exception_credentials(self):
  secret='SyntheticSecret_DoNotLog_456!'
  with mock.patch.object(server,'Content',return_value=self.content),mock.patch.object(server,'Store',side_effect=RuntimeError(1045,'password='+secret)):
   with contextlib.redirect_stderr(io.StringIO()) as output:result=await server.main(['--config',str(self.config),'--no-console'])
  text=(self.root/'logs/world.log').read_text()+output.getvalue();self.assertEqual(result,1);self.assertIn('database error 1045',text);self.assertNotIn(secret,text)
 async def test_failed_world_service_constructor_closes_open_store(self):
  db=Store(self.settings)
  with mock.patch.object(server,'Content',return_value=self.content),mock.patch.object(server,'Store',return_value=db),mock.patch.object(server,'Service',side_effect=RuntimeError('constructor failed')),mock.patch.object(db,'close',wraps=db.close) as close:
   with contextlib.redirect_stderr(io.StringIO()):result=await server.main(['--config',str(self.config),'--no-console'])
  self.assertEqual(result,1);close.assert_called_once()
 async def test_cancelled_database_constructor_closes_its_pending_result(self):
  db=Store(self.settings);entered=threading.Event();finish=threading.Event()
  def delayed_constructor(_settings):entered.set();finish.wait(timeout=3);return db
  try:
   with mock.patch.object(server,'Content',return_value=self.content),mock.patch.object(server,'Store',side_effect=delayed_constructor),mock.patch.object(db,'close',wraps=db.close) as close,contextlib.redirect_stderr(io.StringIO()):
    task=asyncio.create_task(server.main(['--config',str(self.config),'--no-console']))
    try:
     self.assertTrue(await asyncio.to_thread(entered.wait,3));task.cancel();finish.set()
     with self.assertRaises(asyncio.CancelledError):await task
    finally:
     finish.set()
     if not task.done():task.cancel()
     with contextlib.suppress(asyncio.CancelledError):await task
    close.assert_called_once();self.assertTrue(db.closed)
  finally:finish.set();db.close()
 def test_known_database_setup_errors_keep_their_actionable_guidance(self):
  for message in ('PyMySQL is missing. Run 1 - Install Server Dependencies.cmd.','Database is not configured. Run 2 - Configure MySQL.cmd.','Database is newer than this server; do not downgrade.'):
   with self.subTest(message=message):self.assertEqual(server.failure_summary(RuntimeError(message),'opening database'),message)
 async def test_live_lease_refresh_rejects_contender_without_touching_owner(self):
  service=self.make_service();owner=Store(self.settings);owner.acquire_lease()
  with owner.transaction() as cursor:cursor.execute('UPDATE world_leases SET heartbeat=heartbeat-10 WHERE id=1')
  original=service.db.acquire_lease;calls=0
  def acquire():
   nonlocal calls
   calls+=1
   if calls>1:
    with owner.transaction() as cursor:cursor.execute('UPDATE world_leases SET heartbeat=heartbeat+1 WHERE id=1')
   original()
  try:
   with mock.patch.object(service.db,'acquire_lease',side_effect=acquire),mock.patch.object(server.asyncio,'sleep',new=mock.AsyncMock()),self.assertLogs('nxt',level='WARNING'):
    with self.assertRaisesRegex(server.WorldStartupError,'still refreshing'):await service.run(no_console=True)
   with owner.transaction() as cursor:cursor.execute('SELECT owner FROM world_leases WHERE id=1');self.assertEqual(cursor.fetchone()[0],owner.lease_id)
  finally:owner.close()
 async def test_stale_lease_waits_then_recovers_without_forced_removal(self):
  service=self.make_service();owner=Store(self.settings);owner.acquire_lease()
  async def expire(_delay):
   with owner.transaction() as cursor:cursor.execute('UPDATE world_leases SET heartbeat=heartbeat-61 WHERE id=1')
  try:
   with mock.patch.object(server.asyncio,'sleep',side_effect=expire) as wait,self.assertLogs('nxt',level='INFO') as captured:await service.acquire_world_lease()
   wait.assert_awaited_once();self.assertTrue(service.db.lease_active);self.assertIn('ownership recovered','\n'.join(captured.output))
  finally:owner.close()
 async def test_future_lease_is_preserved_with_clock_guidance(self):
  service=self.make_service();owner=Store(self.settings);owner.acquire_lease()
  with owner.transaction() as cursor:cursor.execute('UPDATE world_leases SET heartbeat=heartbeat+300 WHERE id=1')
  try:
   with self.assertLogs('nxt',level='ERROR'):
    with self.assertRaisesRegex(server.WorldStartupError,'dated in the future'):await service.run(no_console=True)
   with owner.transaction() as cursor:cursor.execute('SELECT owner FROM world_leases WHERE id=1');self.assertEqual(cursor.fetchone()[0],owner.lease_id)
  finally:owner.close()
 async def test_lease_wait_stops_after_bounded_deadline_without_forcing_ownership(self):
  service=self.make_service();owner=Store(self.settings);owner.acquire_lease()
  try:
   with mock.patch.object(server,'time') as clock,mock.patch.object(server.asyncio,'sleep',new=mock.AsyncMock()) as wait,self.assertLogs('nxt',level='WARNING'):
    clock.monotonic.side_effect=[0,0,65]
    with self.assertRaisesRegex(server.WorldStartupError,'still unavailable after waiting'):await service.acquire_world_lease()
   wait.assert_awaited_once();self.assertFalse(service.db.lease_active)
   with owner.transaction() as cursor:cursor.execute('SELECT owner FROM world_leases WHERE id=1');self.assertEqual(cursor.fetchone()[0],owner.lease_id)
  finally:owner.close()
 async def test_cancelled_acquisition_finishes_worker_before_releasing_lease(self):
  service=self.make_service();entered=threading.Event();finish=threading.Event();original=service.db.acquire_lease
  def delayed_acquire():entered.set();finish.wait(timeout=3);original()
  with mock.patch.object(service.db,'acquire_lease',side_effect=delayed_acquire):
   task=asyncio.create_task(service.run(no_console=True))
   try:
    self.assertTrue(await asyncio.to_thread(entered.wait,3));task.cancel();finish.set()
    with self.assertRaises(asyncio.CancelledError):await task
   finally:
    finish.set()
    if not task.done():task.cancel()
    with contextlib.suppress(asyncio.CancelledError):await task
  await self.assert_can_restart()
 async def test_unwritable_preferred_log_directory_reports_real_fallback_path(self):
  (self.root/'logs').write_text('This file deliberately blocks the preferred logs directory.')
  with mock.patch.dict(server.os.environ,{'LOCALAPPDATA':str(self.root/'local-app-data')}),contextlib.redirect_stderr(io.StringIO()) as output:
   result=await server.main(['--config',str(self.config),'--no-console'])
  self.assertEqual(result,1);paths=list((self.root/'local-app-data/PokemonNXTMMO/logs').glob('world-*.log'));self.assertEqual(len(paths),1);self.assertIn(str(paths[0]),output.getvalue());self.assertIn('loading world content',paths[0].read_text())

if __name__=='__main__':unittest.main()
