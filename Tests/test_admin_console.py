"""Local-console contracts using real SQLite commits and the shipped content.

No privileged filesystem links, operator database, remote service or Windows
administrator rights are required. Network exposure is tested separately.
"""
from __future__ import annotations
import asyncio
import configparser
import copy
import dataclasses
import io
import json
import re
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'Server'),str(ROOT)]
from server import Service
from nxt.admin_console import LocalAdmin, AuditFile, MAX_LINE, parse, number
from nxt.admin_policy import ConsolePolicy
from nxt.admin_registry import COMMANDS, BY_NAME, ALIASES, canonical
from nxt.config import Settings
from nxt.content import Content, NATURES
from nxt.security import RequestError, password_hash, password_verify
from nxt.store import Store
from nxt.varieties import VARIETIES
from nxt.world import World

class ConsoleParsingTests(unittest.TestCase):
    def test_quotes_aliases_and_optional_slash(self):
        self.assertEqual(parse('/GP Trainer "Mr. Mime" 20 mystic'),('givepokemon',['Trainer','Mr. Mime','20','mystic']))
        self.assertEqual(parse('help'),('help',[]))
        self.assertEqual(parse('  '),('',[]))
        self.assertEqual(parse('playerinfo #42'),('playerinfo',['#42']))
    def test_control_characters_malformed_quotes_and_limits(self):
        for raw in ('who\nshutdown','who\rhelp','who\x1b[0m','help\x00','help "','x'*(MAX_LINE+1),'help '+' '.join(['x']*21)):
            with self.subTest(raw=repr(raw[:50])),self.assertRaises(RequestError):parse(raw)
        for raw in ('NaN','1.0','True','-1','99999999999999999'):
            with self.assertRaises(RequestError):number(raw,0,100)
        self.assertEqual(number('9007199254740991',1,2**53-1),2**53-1)
    def test_catalog_has_unique_names_and_no_chat_entries(self):
        self.assertEqual(len(COMMANDS),len(BY_NAME))
        self.assertEqual(sum(len(sp.aliases) for sp in COMMANDS),len(ALIASES))
        forbidden={'say','shout','global','whisper','w','reply','r','ignore','unignore','friends','friend','mute','unmute','announce','broadcast'}
        self.assertFalse(forbidden & (set(BY_NAME)|set(ALIASES)))
        for alias,name in ALIASES.items():self.assertEqual(canonical('/'+alias.upper()),name)
    def test_policy_defaults_and_alias_disabling(self):
        c=configparser.ConfigParser(interpolation=None)
        p=ConsolePolicy.load(c);self.assertTrue(p.enabled);self.assertFalse(p.allow_developer_commands)
        c['console']={'disabled_commands':'gp, /tp','allow_developer_commands':'true'}
        p=ConsolePolicy.load(c);self.assertEqual(p.disabled_commands,{'givepokemon','teleport'})
        self.assertFalse(p.allows(BY_NAME['givepokemon']));self.assertTrue(p.allows(BY_NAME['clonepokemon']))
    def test_invalid_policy_fails_closed(self):
        for fields in ({'disabled_commands':'madeup'},{'disabled_commands':'confirm'},{'confirmation_seconds':'0'},{'confirmation_seconds':'301'},{'enabled':'maybe'},{'allow_pipes':'true'}):
            c=configparser.ConfigParser();c['console']=fields
            with self.subTest(fields=fields),self.assertRaises(ValueError):ConsolePolicy.load(c)
    def test_windows_command_launchers_keep_crlf_and_explicit_restart(self):
        for name in ('3 - Start World Server.cmd','Start Developer SQLite World.cmd'):
            raw=(ROOT/'Server'/name).read_bytes()
            self.assertNotIn(b'\n',raw.replace(b'\r\n',b''));self.assertIn(b'"75"',raw);self.assertIn(b'goto start_world',raw)
    def test_release_versions_and_manual_catalog_stay_aligned(self):
        from server import VERSION
        from nxt import __version__
        data=json.loads((ROOT/'Server/data/world.json').read_text())
        self.assertEqual(data['version'],VERSION);self.assertEqual(__version__,VERSION)
        self.assertIn(VERSION,(ROOT/'Client/app/index.html').read_text())
        audit=json.loads((ROOT/'Docs/LOCAL_ADMIN_PROPOSAL_AUDIT.json').read_text())
        self.assertEqual(audit['gameplay'],VERSION);self.assertEqual(audit['canonicalCommands'],len(COMMANDS))
        self.assertEqual(audit['aliases'],len(ALIASES));self.assertEqual(len(audit['rows']),148)
        self.assertTrue(all(row['note'] and (not row['nxtCommand'] or row['nxtCommand'] in BY_NAME) for row in audit['rows']))
        manual=(ROOT/'Docs/LOCAL_ADMIN_CONSOLE.md').read_text()
        for sp in COMMANDS:self.assertIn('`'+sp.name+' ',manual)
    def test_schema_busy_guidance_is_explicit_without_driver_payload(self):
        from server import failure_summary
        from nxt.store import WorldSchemaUpgradeBusy
        text=failure_summary(WorldSchemaUpgradeBusy(),'opening database')
        self.assertIn('Stop the previous world',text);self.assertIn('no schema-2 upgrade',text)
    def test_local_audit_rotation_and_bounded_tail(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'audit.jsonl';audit=AuditFile(path)
            path.write_bytes(b'x'*4_000_001+b'\n')
            audit.write({'command':'who','outcome':'committed'})
            self.assertTrue(Path(str(path)+'.1').exists())
            self.assertEqual(json.loads(audit.tail(1)[0])['command'],'who')
    def test_new_modules_are_selected_without_runtime_audit_or_credentials(self):
        from Build.build import is_source_file as source_allowed
        for name in ('Server/nxt/admin_console.py','Server/nxt/admin_store.py','Server/nxt/admin_registry.py','Server/nxt/admin_policy.py','Tests/test_admin_console.py'):
            self.assertTrue(source_allowed(Path(name)),name)
        for name in ('Server/logs/admin-console.jsonl','Server/logs/admin-console.jsonl.1','Server/config.ini','Server/data/development.sqlite3'):
            self.assertFalse(source_allowed(Path(name)),name)


class LocalConsoleTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.content=Content(ROOT/'Server/data/world.json')
        cls.hashed=password_hash('Console_Regression_Secret_19!')
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='nxt-console-test-');self.root=Path(self.tmp.name)
        self.config=self.root/'config.ini';self.config.write_bytes((ROOT/'Build/config_templates/Server/config.ini').read_bytes())
        self.s=Settings.load(self.config);self.s.config.set('database','backend','sqlite');self.s=dataclasses.replace(self.s,encounter_chance=0)
        self.db=Store(self.s);self.db.acquire_lease();self.service=Service(self.s,self.content,self.db)
        self.w=self.service.world;self.admin=self.service.console_commands
        self.aid=self.db.create('ConsoleAlice',self.hashed,self.w.initial('ConsoleAlice','Kanto','fr_1',0))
        self.bid=self.db.create('ConsoleBobby',self.hashed,self.w.initial('ConsoleBobby','Johto','fr_152',7))
        self.a=await self.w.join(self.aid,'ConsoleAlice',None,asyncio.Queue())
        self.b=await self.w.join(self.bid,'ConsoleBobby',None,asyncio.Queue())
        self.drain(self.a);self.drain(self.b)
    async def asyncTearDown(self):
        await self.admin.close()
        for p in list(self.w.players.values()):
            await self.w.leave(p)
        if self.service.admin_disconnect_tasks:await asyncio.gather(*self.service.admin_disconnect_tasks,return_exceptions=True)
        self.db.close();self.tmp.cleanup()
    @staticmethod
    def drain(p):
        result=[]
        while not p.queue.empty():result.append(p.queue.get_nowait())
        return result
    async def command(self,line,*,confirm=False,ok=True):
        lines=await self.admin.execute(line,output=lambda _:None)
        if confirm:
            tokens=re.findall(r'enter: confirm ([0-9a-f]+)','\n'.join(lines))
            self.assertEqual(len(tokens),1,(line,lines))
            lines=await self.admin.execute('confirm '+tokens[0],output=lambda _:None)
        if ok:self.assertFalse(any(v.startswith('ERROR:') for v in lines),(line,lines))
        else:self.assertTrue(any(v.startswith('ERROR:') for v in lines),(line,lines))
        return '\n'.join(lines)
    def dev(self):self.admin.policy=dataclasses.replace(self.admin.policy,allow_developer_commands=True)
    async def preview(self,line):
        text=await self.command(line)
        return re.search(r'enter: confirm ([0-9a-f]+)',text)[1]
    async def test_help_readouts_and_catalog_pagination(self):
        for line in ('help','commands Pokemon','help gp','serverinfo','status','online','who','version','uptime','time','playerinfo ConsoleAlice','profile #1','stats id:1','where ConsoleBobby','location #2','team ConsoleAlice','pokemon ConsoleAlice','collection ConsoleBobby','pokemoninfo ConsoleAlice party:1','bag ConsoleAlice','money ConsoleAlice','balance ConsoleBobby','species "Mr. Mime"','items potion','moves tackle','maps pallet','iteminfo potion','economy','connections','ipinfo ConsoleAlice','threads','memory','logs 4','gc'):
            with self.subTest(line=line):await self.command(line)
        await self.command('species "" 2')
        await self.command('who 999',ok=False)
        text=await self.command('help');self.assertNotIn('[Developer]',text)
    async def test_default_dev_disabled_and_alias_cannot_bypass(self):
        for line in ('createaccount Example Kanto Bulbasaur','clonepokemon ConsoleAlice party:1','spawnwild ConsoleAlice Pikachu','battle ConsoleAlice Pikachu','sethp ConsoleAlice party:1 1','win ConsoleAlice','clearmoves ConsoleAlice party:1'):
            with self.subTest(line=line):self.assertIn('disabled',await self.command(line,ok=False))
        self.admin.policy=dataclasses.replace(self.admin.policy,disabled_commands=frozenset({'givepokemon'}))
        await self.command('gp ConsoleAlice Pikachu',ok=False)
        text=await self.command('help Pokemon');self.assertNotIn('givepokemon',text)
    async def test_chat_unknown_shell_and_unvalidated_secret_are_not_logged(self):
        secret='DoNotLog_This_Fake_Secret_123'
        for line in ('announce hello','mute ConsoleAlice 30','whisper ConsoleAlice test','__import__("os")','givemoney ConsoleAlice 1;who','who\nshutdown','resetpassword ConsoleAlice '+secret,'unrecognized '+secret):
            await self.command(line,ok=False)
        self.assertNotIn(secret,self.admin.audit.path.read_text())
        self.assertFalse(self.service.stop.is_set());self.assertEqual(self.a.state['money'],3000)
    async def test_exact_target_ids_and_no_ambiguous_catalog_guess(self):
        await self.command('givemoney #1 10');await self.command('givemoney id:2 20')
        self.assertEqual(self.a.state['money'],3010);self.assertEqual(self.b.state['money'],3020)
        await self.command('givemoney Console 10',ok=False);await self.command('givemoney #9999999 1',ok=False)
        duplicates={}
        for key,m in self.content.maps.items():duplicates.setdefault(m['name'].casefold(),[]).append(key)
        name,keys=next((name,keys) for name,keys in duplicates.items() if len(keys)>1)
        with self.assertRaises(RequestError):self.admin.exact(self.content.maps,name,'maps')
    async def test_grants_all_six_varieties_unique_uid_and_pc_overflow(self):
        before=len(self.a.state['creatures'])
        for value in VARIETIES:await self.command(f'givepokemon ConsoleAlice Pikachu 25 {value}')
        mons=self.a.state['creatures'][before:]
        self.assertEqual([m['variety'] for m in mons],list(VARIETIES))
        self.assertEqual(len({m['uid'] for m in mons}),6)
        self.assertEqual(len(self.a.state['party']),6);self.assertNotIn(mons[-1]['uid'],self.a.state['party'])
        self.assertEqual(self.db.load(self.aid),self.a.state)
        self.assertFalse(any(v['type']=='state' for v in self.drain(self.b)))
    async def test_collection_cap_and_bad_species_variety_level_leave_no_mutation(self):
        await self.command('givepokemon ConsoleAlice NotAPokemon 5',ok=False)
        await self.command('gp ConsoleAlice Pikachu 101',ok=False)
        await self.command('gp ConsoleAlice Pikachu 1 imaginary',ok=False)
        self.service.s=dataclasses.replace(self.service.s,max_owned=1)
        await self.command('gp ConsoleAlice Pikachu',ok=False)
        self.assertEqual(len(self.a.state['creatures']),1)
    async def test_owned_uid_and_viable_party_removal(self):
        original=copy.deepcopy(self.a.state)
        await self.command('removepokemon ConsoleAlice '+self.b.state['party'][0],ok=False)
        await self.command('removepokemon ConsoleAlice party:1',ok=False)
        await self.command('gp ConsoleAlice Pikachu 5 shadow')
        uid=self.a.state['party'][1]
        token=await self.preview('removepokemon ConsoleAlice '+uid)
        self.assertEqual(len(self.a.state['creatures']),2)
        await self.command('confirm '+token)
        self.assertEqual(self.a.state['party'],original['party']);self.assertEqual(len(self.a.state['creatures']),1)
    async def test_confirm_is_single_use_expires_and_can_be_cancelled(self):
        token=await self.preview('setmoney ConsoleAlice 100')
        self.assertEqual(self.a.state['money'],3000)
        await self.command('confirm '+token);await self.command('confirm '+token,ok=False)
        token=await self.preview('setmoney ConsoleAlice 200')
        self.admin.pending[token].expires=time.monotonic()-1
        await self.command('confirm '+token,ok=False);self.assertEqual(self.a.state['money'],100)
        token=await self.preview('setmoney ConsoleAlice 300');await self.command('cancel '+token)
        await self.command('confirm '+token,ok=False)
        await self.preview('setmoney ConsoleAlice 400');await self.command('cancel');self.assertFalse(self.admin.pending)
    async def test_confirm_rejects_character_changes_and_session_replacement(self):
        token=await self.preview('setmoney ConsoleAlice 10')
        await self.command('givemoney ConsoleAlice 1')
        self.assertIn('changed',await self.command('confirm '+token,ok=False))
        token=await self.preview('setmoney ConsoleAlice 10')
        await self.w.leave(self.a);self.a=await self.w.join(self.aid,'ConsoleAlice',None,asyncio.Queue())
        await self.command('confirm '+token,ok=False)
        self.assertEqual(self.a.state['money'],3001)
    async def test_confirm_rechecks_disabled_policy(self):
        token=await self.preview('setmoney ConsoleAlice 10')
        self.admin.policy=dataclasses.replace(self.admin.policy,disabled_commands=frozenset({'setmoney'}))
        await self.command('confirm '+token,ok=False);self.assertEqual(self.a.state['money'],3000)
    async def test_offline_edit_commits_and_preserves_cut_badges_and_varieties(self):
        await self.command('gp ConsoleBobby Pikachu 25 metallic')
        saved=copy.deepcopy(self.b.state);saved['adventure']['badges']=['johto_1','johto_2']
        # Use valid shipped tree identities, not invented collision overrides.
        tree=next((m,o) for m in self.content.maps.values() for o in m['objects'] if o['graphics']==95)
        await self.w.commit(self.b,saved);await self.w.leave(self.b)
        baseline=self.db.load(self.bid)
        await self.command('givemoney ConsoleBobby 77')
        after=self.db.load(self.bid)
        self.assertEqual(after['adventure'],baseline['adventure']);self.assertEqual(after['creatures'],baseline['creatures'])
        self.b=await self.w.join(self.bid,'ConsoleBobby',None,asyncio.Queue())
        self.assertEqual(self.b.state['money'],baseline['money']+77)
        self.assertEqual(self.b.state['creatures'][-1]['variety'],'metallic')
    async def test_inventory_and_money_bounds_exactness(self):
        await self.command('gi ConsoleAlice potion 3')
        qty=self.a.state['items']['potion']
        await self.command('removeitem ConsoleAlice potion 2',confirm=True);self.assertEqual(self.a.state['items']['potion'],qty-2)
        await self.command('setitem ConsoleAlice potion 999',confirm=True)
        await self.command('giveitem ConsoleAlice potion 1',ok=False)
        await self.command('removeitem ConsoleAlice potion 999',confirm=True)
        await self.command('removeitem ConsoleAlice potion 1',ok=False)
        await self.command('setmoney ConsoleAlice 2000000000',confirm=True)
        await self.command('givemoney ConsoleAlice 1',ok=False)
        await self.command('removemoney ConsoleAlice 1999999999',confirm=True)
        await self.command('removemoney ConsoleAlice 2',ok=False)
        self.assertEqual(self.a.state['money'],1)
        mons=copy.deepcopy(self.a.state['creatures'])
        await self.command('clearinventory ConsoleAlice',confirm=True)
        self.assertEqual(self.a.state['items'],{});self.assertEqual(self.a.state['creatures'],mons)
    async def test_hp_nature_ivs_growth_and_exact_level_one(self):
        self.dev();mon=self.a.state['creatures'][0]
        await self.command('sethp ConsoleAlice party:1 2',confirm=True)
        await self.command('setlevel ConsoleAlice party:1 20',confirm=True)
        mon=self.a.state['creatures'][0];self.assertEqual(mon['level'],20);self.assertEqual(mon['exp'],self.content.xp(20,3))
        await self.command('setivs ConsoleAlice party:1 1 2 3 4 5 6',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['ivs'],[1,2,3,6,4,5])
        await self.command('setnature ConsoleAlice party:1 Modest',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['nature'],NATURES.index('Modest'))
        await self.command('setlevel ConsoleAlice party:1 1',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['level'],1)
        await self.command('setlevel ConsoleAlice party:1 100',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['level'],100)
        await self.command('setexp ConsoleAlice party:1 1000',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['exp'],1000)
        await self.command('sethp ConsoleAlice party:1 0',confirm=True)
        await self.command('setlevel ConsoleAlice party:1 80',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['hp'],0)
    async def test_all_variety_changes_keep_combat_stats_and_replicate_follower(self):
        original=copy.deepcopy(self.a.state['creatures'][0])
        for value in VARIETIES:
            await self.command(f'setvariety ConsoleAlice party:1 {value}',confirm=True)
            m=self.a.state['creatures'][0];self.assertEqual(m['variety'],value);self.assertEqual(m['shiny'],value=='shiny')
            self.assertEqual(m['ivs'],original['ivs']);self.assertEqual(m['moves'],original['moves'])
            self.assertEqual(self.a.entity()['followerVariety'],value)
        await self.command('setshiny ConsoleAlice party:1 true',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['variety'],'shiny')
        await self.command('setshiny ConsoleAlice party:1 false',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['variety'],'normal')
    async def test_native_learning_forgetting_and_evolution_preserve_identity(self):
        await self.command('setlevel ConsoleAlice party:1 20',confirm=True)
        await self.command('setvariety ConsoleAlice party:1 mystic',confirm=True)
        mon=self.a.state['creatures'][0];uid=mon['uid'];known=mon['moves'][0]['id']
        await self.command('forget ConsoleAlice party:1 1',confirm=True)
        # Known native level-one move is now a legal reminder into an explicit slot.
        await self.command(f'learn ConsoleAlice party:1 {known} 1')
        await self.command('learn ConsoleAlice party:1 165 1',ok=False)
        await self.command('evolve ConsoleAlice party:1')
        mon=self.a.state['creatures'][0];self.assertEqual(mon['uid'],uid);self.assertEqual(mon['species'],'fr_2');self.assertEqual(mon['variety'],'mystic')
        await self.command('evolve ConsoleAlice party:1 Mewtwo',ok=False)
    async def test_stone_evolution_consumes_only_required_item(self):
        await self.command('gp ConsoleAlice Pikachu 20 ancient')
        await self.command('evolve ConsoleAlice party:2',ok=False)
        key=next(k for k,v in self.content.items.items() if v.get('name')=='Thunder Stone')
        await self.command(f'giveitem ConsoleAlice {key} 1')
        await self.command('evolve ConsoleAlice party:2')
        self.assertEqual(self.a.state['creatures'][1]['species'],'fr_26')
        self.assertEqual(self.a.state['items'].get(key,0),0)
        self.assertEqual(self.a.state['creatures'][1]['variety'],'ancient')
    async def test_healing_all_is_atomic_and_busy_players_are_skipped(self):
        self.a.state['creatures'][0].update(hp=1,status='poison');self.b.state['creatures'][0].update(hp=1,status='burn')
        self.b.battle='busy-test'
        await self.command('healall',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['status'],'');self.assertEqual(self.b.state['creatures'][0]['hp'],1)
        self.b.battle=None;await self.command('heal ConsoleBobby');self.assertEqual(self.b.state['creatures'][0]['status'],'')
    async def test_busy_gameplay_rejects_roster_inventory_money_and_teleport(self):
        before=copy.deepcopy(self.a.state);self.a.battle='active-test'
        for line in ('gp ConsoleAlice Pikachu','gi ConsoleAlice potion 1','givemoney ConsoleAlice 1','teleport ConsoleAlice kanto_3_0','setvariety ConsoleAlice party:1 shadow','freeze ConsoleAlice'):
            await self.command(line,ok=False)
        self.assertEqual(self.a.state,before);self.a.battle=None
    async def test_safe_teleport_rejects_walls_water_warps_and_preserves_home(self):
        oldhome=self.a.state['home'];target=self.content.data['homes']['Johto']
        await self.command(f'teleport ConsoleAlice {target}')
        self.assertEqual(self.a.state['map'],target);self.assertEqual(self.a.state['home'],oldhome)
        await self.command('goto ConsoleAlice ConsoleBobby')
        await self.command('bring ConsoleBobby ConsoleAlice')
        await self.command('unstuck ConsoleAlice');self.assertEqual(self.a.state['map'],self.content.data['homes'][oldhome])
        before=copy.deepcopy(self.a.state);m=self.content.maps[before['map']]
        x,y=next((x,y) for y in range(m['height']) for x in range(m['width']) if not self.w.walkable(m,x,y,False,state=before))
        await self.command(f'tp ConsoleAlice {m["id"]} {x} {y}',ok=False)
        await self.command(f'tp ConsoleAlice {m["id"]} 1',ok=False)
        self.assertEqual(self.a.state,before)
    async def test_all_hm_tree_destinations_remain_personal(self):
        # A console teleport never silently clears or globally opens an HM tree.
        for m in self.content.maps.values():
            for o in m['objects']:
                if o['graphics']==95 and m.get('playable',True):
                    before=copy.deepcopy(self.a.state)
                    await self.command(f'tp ConsoleAlice {m["id"]} {o["x"]} {o["y"]}',ok=False)
                    self.assertEqual(self.a.state,before)
        self.assertEqual(self.a.state['adventure'].get('cutTrees',{}),{})
    async def test_warn_ban_unban_and_independent_locks_persist(self):
        await self.command('warn ConsoleBobby "Testing a warning"')
        self.assertIn('Testing a warning',await self.command('warnings ConsoleBobby'))
        await self.w.leave(self.b)
        await self.command('ban ConsoleBobby 2h "Temporary restriction"',confirm=True)
        account=self.db.admin_account(uid=self.bid)
        self.assertTrue(self.db.account('ConsoleBobby')['banned']);self.assertGreater(account['ban_until'],int(time.time()))
        with self.assertRaises(RequestError):self.db.auth_guard(self.bid,self.hashed)
        await self.command('lockaccount ConsoleBobby review',confirm=True)
        await self.command('unban ConsoleBobby',confirm=True)
        self.assertFalse(self.db.account('ConsoleBobby')['banned'])
        with self.assertRaises(RequestError):self.db.auth_guard(self.bid,self.hashed)
        await self.command('unlockaccount ConsoleBobby',confirm=True)
        self.db.auth_guard(self.bid,self.hashed)
        self.b=await self.w.join(self.bid,'ConsoleBobby',None,asyncio.Queue())
    async def test_temporary_ban_expiry_and_permanent_ban(self):
        await self.w.leave(self.b)
        await self.command('ban ConsoleBobby 1s test',confirm=True)
        future=time.time()+2
        with mock.patch('time.time',return_value=future):self.assertFalse(self.db.account('ConsoleBobby')['banned']);self.db.auth_guard(self.bid,self.hashed)
        await self.command('ban ConsoleBobby permanent test',confirm=True)
        with mock.patch('time.time',return_value=future+20_000_000):self.assertTrue(self.db.account('ConsoleBobby')['banned'])
        await self.command('unban ConsoleBobby',confirm=True)
        self.b=await self.w.join(self.bid,'ConsoleBobby',None,asyncio.Queue())
    async def test_freeze_is_personal_persistent_and_move_is_nacked(self):
        await self.command('freeze ConsoleAlice',confirm=True);before=copy.deepcopy(self.a.state)
        await self.w.dispatch(self.a,{'op':'move','seq':1,'direction':'right'})
        packets=self.drain(self.a);move=next(p for p in packets if p['type']=='move');self.assertFalse(move['accepted']);self.assertEqual(move['reason'],'frozen')
        self.assertEqual(self.a.state,before)
        with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'encounter'})
        await self.w.dispatch(self.a,{'op':'chat','channel':'general','text':'A normal message still works'})
        await self.w.leave(self.a);self.a=await self.w.join(self.aid,'ConsoleAlice',None,asyncio.Queue());self.assertTrue(self.a.frozen)
        self.assertFalse(self.b.frozen);self.assertNotIn('frozen',self.a.entity())
        await self.command('unfreeze ConsoleAlice');self.assertFalse(self.a.frozen)
    async def test_trade_block_cancels_offer_and_blocks_both_invite_directions(self):
        await self.command('teleport ConsoleBobby kanto_3_0')
        await self.w.invite(self.a,{'kind':'trade','target':self.bid});inv=next(iter(self.w.invites))
        await self.w.answer_invite(self.b,{'id':inv,'accept':True});self.assertIsNotNone(self.a.trade)
        original=copy.deepcopy(self.a.state)
        await self.command('blocktrade ConsoleAlice true',confirm=True)
        self.assertIsNone(self.a.trade);self.assertIsNone(self.b.trade);self.assertEqual(self.a.state,original)
        for p,q in ((self.a,self.b),(self.b,self.a)):
            with self.assertRaises(RequestError):await self.w.invite(p,{'kind':'trade','target':q.id})
        await self.command('blocktrade ConsoleAlice false',confirm=True)
        await self.w.invite(self.a,{'kind':'trade','target':self.bid})
        await self.command('tradecancel ConsoleAlice');self.assertFalse(self.w.invites)
        await self.command('tradehistory ConsoleAlice')
    async def test_reset_password_secure_display_once_and_never_in_audits(self):
        await self.w.leave(self.b)
        result=await self.command('resetpassword ConsoleBobby',confirm=True)
        password=re.search(r'not logged\): (\S+)',result)[1]
        row=self.db.account('ConsoleBobby')
        self.assertTrue(password_verify(password,row['password_hash']));self.assertFalse(password_verify('Console_Regression_Secret_19!',row['password_hash']))
        with self.assertRaises(RequestError):self.db.auth_guard(self.bid,self.hashed)
        self.assertNotIn(password,self.admin.audit.path.read_text())
        self.assertNotIn(password,json.dumps(self.db.admin_history(self.bid)))
        self.assertNotIn(row['password_hash'],json.dumps(self.db.admin_history(self.bid)))
        self.b=await self.w.join(self.bid,'ConsoleBobby',None,asyncio.Queue(),auth_hash=row['password_hash'])
    async def test_create_account_is_ordinary_separate_and_duplicate_safe(self):
        self.dev();result=await self.command('createaccount ConsoleNew Johto Cyndaquil',confirm=True)
        password=re.search(r'not logged\): (\S+)',result)[1]
        account=self.db.account('ConsoleNew');self.assertTrue(password_verify(password,account['password_hash']))
        state=self.db.load(account['id']);self.assertEqual(state['home'],'Johto');self.assertEqual(state['creatures'][0]['species'],'fr_155')
        self.assertNotIn('rank',state);self.assertNotIn(password,self.admin.audit.path.read_text())
        self.assertEqual(self.db.admin_history(account['id'])[0]['command'],'createaccount')
        await self.command('createaccount ConsoleNew Kanto Bulbasaur',ok=False)
    async def test_developer_clone_status_and_moves_use_existing_mechanics(self):
        self.dev();before=self.a.state['creatures'][0]['uid']
        await self.command('clonepokemon ConsoleAlice party:1');self.assertNotEqual(before,self.a.state['creatures'][1]['uid'])
        for status in ('burn','poison','toxic','paralysis','sleep','none'):
            await self.command(f'setstatus ConsoleAlice party:1 {status}',confirm=True)
        await self.command('setstatus ConsoleAlice party:1 frozen',ok=False)
        await self.command('addmove ConsoleAlice party:1 165 1',confirm=True)
        await self.command('clearmoves ConsoleAlice party:1',confirm=True)
        self.assertEqual(self.a.state['creatures'][0]['moves'],[])
    async def test_sandbox_battle_win_loss_and_end_never_change_progress(self):
        self.dev();original=copy.deepcopy(self.a.state)
        for result in ('win','lose','endbattle'):
            await self.command('testbattle ConsoleAlice Pikachu 10 shadow')
            b=self.w.battles[self.a.battle]
            self.assertEqual(b.kind,'duel');self.assertEqual(b.rosters[1][0]['variety'],'shadow')
            with self.assertRaises(RequestError):b.choose(0,{'action':'capture','item':'pokeball'})
            await self.command(result+' ConsoleAlice')
            self.assertIsNone(self.a.battle);self.assertEqual(self.a.state,original);self.assertEqual(self.db.load(self.aid),original)
        await self.w.start_wild(self.a,('fr_25',5))
        for result in ('win','lose','endbattle'):await self.command(result+' ConsoleAlice',ok=False)
        self.assertIsNotNone(self.a.battle)
    async def test_save_and_audit_share_transaction_and_commit_before_publish(self):
        before=copy.deepcopy(self.a.state);self.drain(self.a)
        original=self.db._admin_audit
        def check(cursor,event):
            self.assertEqual(self.a.state,before)
            self.assertFalse(any(v['type']=='state' for v in list(self.a.queue._queue)))
            return original(cursor,event)
        with mock.patch.object(self.db,'_admin_audit',side_effect=check):await self.command('givemoney ConsoleAlice 25')
        self.assertEqual(self.a.state['money'],before['money']+25)
        self.assertEqual(self.db.load(self.aid),self.a.state)
        self.assertEqual(self.db.admin_history(self.aid)[0]['command'],'givemoney')
        for line in ('save ConsoleAlice','save','saveall','dbsave'):await self.command(line)
    async def test_audit_insert_failure_rolls_back_all_accounts_and_publishes_nothing(self):
        self.a.state['creatures'][0]['hp']=1;self.b.state['creatures'][0]['hp']=1
        for p in (self.a,self.b):p.state['revision']+=1
        await self.w.save_all();before=[copy.deepcopy(p.state) for p in (self.a,self.b)]
        token=await self.preview('healall');self.drain(self.a);self.drain(self.b)
        with mock.patch.object(self.db,'_admin_audit',side_effect=OSError('synthetic failure')):
            await self.command('confirm '+token,ok=False)
        for p,state in zip((self.a,self.b),before):
            self.assertEqual(p.state,state);self.assertEqual(self.db.load(p.id),state);self.assertFalse(self.drain(p))
    async def test_audit_file_failure_before_commit_denies_and_after_commit_warns(self):
        before=copy.deepcopy(self.a.state)
        with mock.patch.object(self.admin.audit,'write',side_effect=OSError('disk unavailable')):
            await self.command('givemoney ConsoleAlice 25',ok=False)
        self.assertEqual(self.a.state,before)
        original=self.admin.audit.write
        def fail_success(event):
            if event['outcome']=='committed':raise OSError('late file failure')
            return original(event)
        with mock.patch.object(self.admin.audit,'write',side_effect=fail_success):text=await self.command('givemoney ConsoleAlice 25')
        self.assertIn('COMMITTED',text);self.assertEqual(self.a.state['money'],before['money']+25)
        self.assertEqual(self.db.admin_history(self.aid)[0]['command'],'givemoney')
    async def test_newer_db_revision_rejects_entire_admin_write(self):
        before=copy.deepcopy(self.a.state);newer=copy.deepcopy(before);newer['revision']+=10;newer['money']+=100
        self.db.save_many([(self.aid,newer)])
        await self.command('givemoney ConsoleAlice 1',ok=False)
        self.assertEqual(self.a.state,before);self.assertEqual(self.db.load(self.aid),newer)
    async def test_world_lease_fence_cannot_be_bypassed(self):
        before=copy.deepcopy(self.a.state)
        with self.db.transaction() as cursor:cursor.execute("UPDATE world_leases SET owner='other-world' WHERE id=1")
        try:
            await self.command('givemoney ConsoleAlice 1',ok=False);self.assertEqual(self.a.state,before)
        finally:
            with self.db.transaction() as cursor:cursor.execute('UPDATE world_leases SET owner=? WHERE id=1',(self.db.lease_id,))
    async def test_cancelled_admin_waiter_finishes_admitted_transaction(self):
        entered=threading.Event();finish=threading.Event();original=self.db.admin_commit
        def delayed(*args,**kwargs):entered.set();finish.wait(timeout=10);return original(*args,**kwargs)
        with mock.patch.object(self.db,'admin_commit',side_effect=delayed):
            task=asyncio.create_task(self.admin.execute('givemoney ConsoleAlice 17',output=lambda _:None))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,5));task.cancel();await asyncio.sleep(.01)
                self.assertFalse(task.done());finish.set()
                with self.assertRaises(asyncio.CancelledError):await task
            finally:finish.set()
        self.assertEqual(self.a.state['money'],3017);self.assertEqual(self.db.load(self.aid),self.a.state)
    async def test_concurrent_commands_are_serial_and_leave_no_lost_updates(self):
        await asyncio.gather(*(self.command('givemoney ConsoleAlice 1') for _ in range(10)))
        self.assertEqual(self.a.state['money'],3010)
        self.assertEqual(sum(e['command']=='givemoney' for e in self.db.admin_history(self.aid)),10)
    async def test_reload_only_supported_fields_and_stale_preview_guard(self):
        cfg=self.admin._read_config(self.config)
        cfg['console']={'enabled':'true','allow_developer_commands':'true','disabled_commands':'gp','confirmation_seconds':'90'}
        cfg.set('world','registration_enabled','false')
        with self.config.open('w') as handle:cfg.write(handle)
        token=await self.preview('reloadconfig')
        text=self.config.read_text();await self.command('confirm '+token)
        self.assertEqual(self.config.read_text(),text)
        self.assertTrue(self.admin.policy.allow_developer_commands);self.assertFalse(self.service.s.flag('world','registration_enabled'))
        await self.command('gp ConsoleAlice Pikachu',ok=False)
        cfg.set('database','host','unrelated.example')
        with self.config.open('w') as handle:cfg.write(handle)
        await self.command('reloadconfig',ok=False)
        self.assertNotEqual(self.service.s.get('database','host'),'unrelated.example')
    async def test_shutdown_restart_schedule_cancel_and_no_immediate_action(self):
        token=await self.preview('shutdown 60');self.assertFalse(self.service.stop.is_set());self.assertIsNone(self.admin.scheduled)
        await self.command('confirm '+token);self.assertEqual(self.admin.scheduled['action'],'shutdown')
        await self.command('cancelshutdown');self.assertIsNone(self.admin.scheduled);self.assertFalse(self.service.stop.is_set())
        await self.command('restart 0',confirm=True)
        for _ in range(20):
            if self.service.stop.is_set():break
            await asyncio.sleep(.01)
        self.assertTrue(self.service.stop.is_set());self.assertTrue(self.service.restart_requested);self.assertTrue(self.w.stopping)
        await self.command('givemoney ConsoleAlice 1',ok=False)
    async def test_nonterminal_input_is_never_consumed_and_eof_keeps_world_online(self):
        pipe=io.StringIO('givemoney ConsoleAlice 100\n')
        with mock.patch('sys.stdin',pipe),mock.patch('builtins.print'):
            await self.admin.console()
        self.assertEqual(pipe.tell(),0);self.assertEqual(self.a.state['money'],3000)
        class Terminal(io.StringIO):
            def isatty(self):return True
        terminal=Terminal('online\n')
        with mock.patch('sys.stdin',terminal),mock.patch('builtins.print'):
            await asyncio.wait_for(self.admin.console(),5)
        self.assertFalse(self.service.stop.is_set())


    async def test_burst_input_is_ordered_bounded_and_keeps_its_eof(self):
        class Terminal(io.StringIO):
            def isatty(self):return True
        terminal=Terminal(''.join(f'givemoney ConsoleAlice {i}\n' for i in range(1,101)))
        with mock.patch('sys.stdin',terminal),mock.patch('builtins.print'):
            await asyncio.wait_for(self.admin.console(),20)
        self.assertFalse(self.service.stop.is_set())
        self.assertEqual(self.a.state['money'],3000+sum(range(1,101)))
        history=self.db.admin_history(self.aid,limit=100)
        self.assertEqual([e['arguments'][-1] for e in history],[str(i) for i in range(100,0,-1)])
        self.assertEqual(len({e['sequence'] for e in history}),100)
    async def test_long_input_drains_one_line_without_running_its_suffix(self):
        class Terminal(io.StringIO):
            def isatty(self):return True
        terminal=Terminal('x'*10000+'givemoney ConsoleAlice 500\n'+'givemoney ConsoleAlice 2\n')
        with mock.patch('sys.stdin',terminal),mock.patch('builtins.print'):
            await asyncio.wait_for(self.admin.console(),5)
        self.assertEqual(self.a.state['money'],3002)
    async def test_control_write_audit_failure_rolls_back_and_does_not_kick(self):
        before=self.db.admin_account(uid=self.aid)
        for line in ('ban ConsoleAlice permanent fixture','lockaccount ConsoleAlice fixture','freeze ConsoleAlice','blocktrade ConsoleAlice true'):
            token=await self.preview(line)
            with mock.patch.object(self.db,'_admin_audit',side_effect=OSError('injected failure')):
                await self.command('confirm '+token,ok=False)
            self.assertEqual(self.db.admin_account(uid=self.aid),before)
            self.assertFalse(self.a.closed);self.assertFalse(self.a.frozen);self.assertFalse(self.a.trade_blocked)
    async def test_failed_password_reset_keeps_old_password_and_session(self):
        token=await self.preview('resetpassword ConsoleAlice')
        with mock.patch.object(self.db,'_admin_audit',side_effect=OSError('injected failure')):
            text=await self.command('confirm '+token,ok=False)
        self.assertNotIn('NEW PASSWORD',text);self.assertFalse(self.a.closed)
        self.assertEqual(self.db.account('ConsoleAlice')['password_hash'],self.hashed)
    async def test_failed_account_creation_rolls_back_and_never_prints_secret(self):
        self.dev();token=await self.preview('createaccount ConsoleNew Johto Totodile')
        with mock.patch.object(self.db,'_admin_audit',side_effect=OSError('injected failure')):
            text=await self.command('confirm '+token,ok=False)
        self.assertIsNone(self.db.admin_account(login='ConsoleNew'));self.assertNotIn('NEW PASSWORD',text)
    async def test_committed_presentation_failure_stops_without_claiming_rollback(self):
        before=self.a.state['money']
        with mock.patch.object(self.w,'send_state',side_effect=RuntimeError('injected presentation failure')):
            text=await self.command('givemoney ConsoleAlice 42')
        self.assertIn('COMMITTED',text);self.assertIn('Do not repeat',text)
        self.assertEqual(self.db.load(self.aid)['money'],before+42)
        self.assertTrue(self.w.stopping);self.assertTrue(self.service.stop.is_set())
    async def test_schema_one_upgrade_preserves_accounts_state_and_existing_ban(self):
        from nxt.store import SCHEMA
        await self.w.leave(self.a);await self.w.leave(self.b)
        original={uid:self.db.load(uid) for uid in (self.aid,self.bid)}
        with self.db.transaction() as cur:
            cur.execute('DROP TABLE admin_audit_targets');cur.execute('DROP TABLE admin_audit');cur.execute('DROP TABLE account_controls')
            cur.execute('UPDATE nxt_schema SET version=1 WHERE id=1')
            cur.execute('UPDATE accounts SET banned=1 WHERE id=?',(self.bid,))
        self.db.close();fresh=Store(self.s)
        try:
            for uid,state in original.items():self.assertEqual(fresh.load(uid),state)
            self.assertEqual(fresh.account('ConsoleAlice')['password_hash'],self.hashed)
            self.assertTrue(fresh.account('ConsoleBobby')['banned'])
            with fresh.transaction() as cur:
                cur.execute('SELECT version FROM nxt_schema WHERE id=1');self.assertEqual(cur.fetchone()[0],SCHEMA)
                cur.execute('SELECT COUNT(*) FROM admin_audit');self.assertEqual(cur.fetchone()[0],0)
            fresh.migrate();self.assertEqual(fresh.load(self.aid),original[self.aid])
        finally:fresh.close()
    async def test_readouts_never_expose_password_hash_or_other_private_configuration(self):
        for line in ('playerinfo ConsoleAlice','pokemoninfo ConsoleAlice party:1','serverinfo','connections','history ConsoleAlice','warnings ConsoleAlice','logs 100'):
            text=await self.command(line)
            self.assertNotIn(self.hashed,text);self.assertNotIn('CHANGE_ME_WITH_SETUP',text)
    async def test_disabled_console_never_starts_input_or_executes(self):
        self.admin.policy=dataclasses.replace(self.admin.policy,enabled=False)
        terminal=io.StringIO('givemoney ConsoleAlice 100\n')
        with mock.patch('sys.stdin',terminal),mock.patch('builtins.print'):await self.admin.console()
        self.assertEqual(terminal.tell(),0);await self.command('help',ok=False)
        self.assertEqual(self.a.state['money'],3000)
    async def test_failed_grant_retry_creates_only_one_unique_pokemon(self):
        count=len(self.a.state['creatures'])
        with mock.patch.object(self.db,'_admin_audit',side_effect=OSError('fixture')):
            await self.command('givepokemon ConsoleAlice Eevee 8 metallic',ok=False)
        self.assertEqual(len(self.a.state['creatures']),count)
        await self.command('givepokemon ConsoleAlice Eevee 8 metallic')
        self.assertEqual(len(self.a.state['creatures']),count+1)
        self.assertEqual(len({m['uid'] for m in self.a.state['creatures']}),count+1)
    async def test_cancelled_stdin_consumer_exits_without_waiting_for_readline(self):
        started=threading.Event();release=threading.Event()
        class Terminal:
            def isatty(self):return True
            def readline(self,*args):started.set();release.wait(timeout=5);return ''
        with mock.patch('sys.stdin',Terminal()),mock.patch('builtins.print'):
            task=asyncio.create_task(self.admin.console())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait,2));task.cancel()
                with self.assertRaises(asyncio.CancelledError):await asyncio.wait_for(task,1)
            finally:release.set();await asyncio.sleep(.02)
        self.assertFalse(self.service.stop.is_set())

    async def test_schema_upgrade_refuses_recent_or_future_old_world_lease(self):
        import sqlite3
        from nxt.store import WorldSchemaUpgradeBusy
        await self.w.leave(self.a);await self.w.leave(self.b);before=self.db.load(self.aid);self.db.close()
        path=self.s.path('database','sqlite_path')
        # sqlite3's transaction context does not close the connection. Keep the
        # commit/rollback context inside closing so Windows can remove the file
        # even when a probe or an assertion raises before normal test teardown.
        with closing(sqlite3.connect(path)) as conn, conn:
            for table in ('admin_audit_targets','admin_audit','account_controls'):conn.execute('DROP TABLE '+table)
            conn.execute('UPDATE nxt_schema SET version=1 WHERE id=1')
            conn.execute('INSERT INTO world_leases VALUES(1,?,?)',('older-world',int(time.time())))
        for heartbeat in (int(time.time()),int(time.time())+86400):
            with closing(sqlite3.connect(path)) as conn, conn:conn.execute('UPDATE world_leases SET heartbeat=? WHERE id=1',(heartbeat,))
            with self.assertRaises(WorldSchemaUpgradeBusy):Store(self.s)
            with closing(sqlite3.connect(path)) as conn, conn:
                self.assertEqual(conn.execute('SELECT version FROM nxt_schema').fetchone()[0],1)
                self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='account_controls'").fetchone())
                self.assertEqual(json.loads(conn.execute('SELECT state_json FROM characters WHERE account_id=?',(self.aid,)).fetchone()[0]),before)
        # An abandoned old lease can expire normally; no forced takeover API.
        with closing(sqlite3.connect(path)) as conn, conn:conn.execute('UPDATE world_leases SET heartbeat=? WHERE id=1',(int(time.time())-61,))
        fresh=Store(self.s)
        try:
            fresh.acquire_lease();self.assertEqual(fresh.load(self.aid),before)
            with fresh.transaction() as cur:cur.execute('SELECT version FROM nxt_schema');self.assertEqual(cur.fetchone()[0],2)
        finally:fresh.close()

if __name__=='__main__':unittest.main()

