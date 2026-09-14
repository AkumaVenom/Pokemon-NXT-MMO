"""Optional real-process console smoke checks using a POSIX pseudo-terminal.

This is supplementary to the mandatory cross-platform unit/network suite. It
runs server.py with a private temporary SQLite database, exercises real stdin,
clean shutdown and exit-75 restart requests, then proves piped commands inactive.
Requires pexpect on POSIX; no elevated privileges, user DB or network service.
Does NOT establish native Windows console or live MySQL acceptance.
"""
from __future__ import annotations
import argparse
import configparser
import json
import os
from contextlib import closing
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'))
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.security import password_hash
from nxt.world import World

def main(output=None):
    if os.name=='nt':raise SystemExit('This supplementary PTY fixture is POSIX-only; run the mandatory unit/network suite on Windows instead.')
    try:import pexpect
    except ImportError:raise SystemExit('Optional process QA requires pexpect in a testing environment; not a server dependency.') from None
    checks=[]
    with tempfile.TemporaryDirectory(prefix='nxt-console-process-') as temp:
        root=Path(temp);(root/'data').mkdir();shutil.copy2(ROOT/'Server/data/world.json',root/'data/world.json')
        cfg=configparser.ConfigParser(interpolation=None);cfg.read(ROOT/'Build/config_templates/Server/config.ini')
        cfg.set('database','backend','sqlite');cfg.set('network','bind_ip','127.0.0.1');cfg.set('network','tls','false');cfg.set('network','allow_insecure_lan','true')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        cfg.set('network','port',str(port));config=root/'config.ini'
        with config.open('w') as handle:cfg.write(handle)
        settings=Settings.load(config);content=Content(ROOT/'Server/data/world.json');db=Store(settings);db.acquire_lease()
        world=World(content,db,settings)
        uid=db.create('ProcessAlice',password_hash('Disposable_Process_Only_719!'),world.initial('ProcessAlice','Kanto','fr_1',0));db.close()
        args=[str(ROOT/'Server/server.py'),'--config',str(config)]
        # Preserve transaction handling and explicitly release every probe handle.
        def state():
            with closing(sqlite3.connect(root/'data/development.sqlite3')) as conn, conn:
                return json.loads(conn.execute('SELECT state_json FROM characters WHERE account_id=?',(uid,)).fetchone()[0])
        def leases():
            with closing(sqlite3.connect(root/'data/development.sqlite3')) as conn, conn:return conn.execute('SELECT COUNT(*) FROM world_leases').fetchone()[0]
        def child():
            p=pexpect.spawn(sys.executable,['-u',*args],encoding='utf-8',timeout=25)
            p.expect('Local console ready');p.expect('NXT>');return p
        p=child()
        try:
            p.sendline('givepokemon ProcessAlice Pikachu 20 ancient');p.expect('OK: Granted');p.expect('NXT>')
            selfstate=state();assert selfstate['creatures'][-1]['species']=='fr_25' and selfstate['creatures'][-1]['variety']=='ancient'
            p.sendline('setvariety ProcessAlice party:1 shadow');p.expect(r'enter: confirm ([0-9a-f]{8})');token=p.match.group(1);p.expect('NXT>')
            assert state()['creatures'][0]['variety']=='normal'
            p.sendline('confirm '+token);p.expect('OK:');p.expect('NXT>');assert state()['creatures'][0]['variety']=='shadow'
            checks.append('Actual TTY stdin grants a variety and applies confirmation only after preview; offline state is durable.')
            p.sendline('spawnwild ProcessAlice Pikachu');p.expect('Developer commands are disabled');p.expect('NXT>')
            p.sendline('announce not-a-command');p.expect('Unknown console command');p.expect('NXT>')
            checks.append('Real console rejects developer alias by default and has no announce/chat handler.')
            p.sendline('shutdown 1');p.expect(r'enter: confirm ([0-9a-f]{8})');token=p.match.group(1);p.expect('NXT>');p.sendline('confirm '+token)
            p.expect('owned database lease released');p.expect(pexpect.EOF);p.close();assert p.exitstatus==0 and leases()==0,(p.exitstatus,p.signalstatus)
            checks.append('Timed shutdown from actual terminal exits 0, closes resources and releases its lease while stdin reader waits.')
        finally:
            if p.isalive():p.terminate(force=True)
        p=child()
        try:
            p.sendline('restart 0');p.expect(r'enter: confirm ([0-9a-f]{8})');token=p.match.group(1);p.expect('NXT>');p.sendline('confirm '+token)
            p.expect('owned database lease released');p.expect(pexpect.EOF);p.close();assert p.exitstatus==75 and leases()==0,(p.exitstatus,p.signalstatus)
            checks.append('Actual server restart request exits 75 only after clean save/lease release; immediate next startup succeeds.')
        finally:
            if p.isalive():p.terminate(force=True)
        log=root/'pipe.log'
        with log.open('w') as handle:
            p=subprocess.Popen([sys.executable,'-u',*args],stdin=subprocess.PIPE,stdout=handle,stderr=handle,text=True)
            try:
                deadline=time.monotonic()+25
                while 'input is not an interactive terminal' not in log.read_text():
                    if p.poll() is not None or time.monotonic()>deadline:raise AssertionError('Non-TTY server did not become ready')
                    time.sleep(.05)
                before=state();p.stdin.write('givemoney ProcessAlice 999999\nshutdown\n');p.stdin.flush();time.sleep(.25)
                assert p.poll() is None and state()==before
                p.terminate();p.wait(timeout=20);assert p.returncode==0 and leases()==0
                checks.append('Real piped stdin never executes a grant/shutdown; OS SIGTERM still performs clean shutdown.')
            finally:
                if p.poll() is None:p.kill();p.wait()
                p.stdin.close()
        with closing(sqlite3.connect(root/'data/development.sqlite3')) as conn, conn:
            rows=conn.execute('SELECT command,payload FROM admin_audit ORDER BY entry_id').fetchall()
        assert [row[0] for row in rows]==['givepokemon','setvariety','shutdown','restart'],rows
        assert 'Disposable_Process_Only_719!' not in (root/'logs/admin-console.jsonl').read_text()
        checks.append('Only four successfully executed terminal actions enter the transaction audit; no piped grant or password leak.')
    result={'result':'PASS','platform':sys.platform,'backend':'temporary SQLite','transport':'actual server.py process with POSIX PTY / separate rejected PIPE','checks':checks}
    text=json.dumps(result,indent=2)+'\n'
    if output:Path(output).write_text(text)
    print(text)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);main(parser.parse_args().output)
