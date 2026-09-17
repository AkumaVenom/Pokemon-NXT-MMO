"""Local console administration, isolated from every client-facing dispatcher.

Parsing and validation build detached plans. Commands run on the world event
loop under its lock, never on the stdin reader thread. Durable character/control
changes and their successful audit are a single fenced database transaction;
private/public presentation changes are emitted only after that commit.
"""
from __future__ import annotations

import asyncio
import configparser
import copy
import gc
import getpass
import hashlib
import json
import logging
import os
import re
import secrets
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .admin_policy import ConsolePolicy
from .admin_registry import COMMANDS, BY_NAME, canonical
from .async_tasks import complete_before_cancelling
from .combat import Battle
from .content import NATURES
from .security import RequestError, require, credentials
from .varieties import VARIETIES, variety_key

log = logging.getLogger('nxt.console')
MAX_LINE = 1024
MAX_PENDING = 16
MAX_MONEY = 2_000_000_000
PAGE_SIZE = 50
RESTART_EXIT_CODE = 75


def safe_text(value):
    """Never let names, reasons or errors inject terminal controls."""
    return ''.join(ch if ch.isprintable() or ch == '\n' else '?' for ch in str(value))


def number(text, lo, hi, label='Value'):
    require(isinstance(text, str) and re.fullmatch(r'-?\d{1,16}', text, flags=re.ASCII) is not None,
            f'{label} must be an integer from {lo} to {hi}.')
    value = int(text)
    require(lo <= value <= hi, f'{label} must be {lo}..{hi}.')
    return value


def boolean(text):
    require(text.casefold() in ('true', 'false'), 'Use true or false.')
    return text.casefold() == 'true'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def parse(line):
    import shlex
    require(isinstance(line, str) and len(line) <= MAX_LINE, f'Command exceeds {MAX_LINE} characters.')
    require(all(ch.isprintable() or ch == '\t' for ch in line), 'Enter one command per line; control characters are forbidden.')
    try:
        parts = shlex.split(line, comments=False, posix=True)
    except ValueError:
        raise RequestError('Unclosed quote. Put names containing spaces inside double quotes.') from None
    require(len(parts) <= 20, 'Too many command arguments.')
    return (canonical(parts[0]), parts[1:]) if parts else ('', [])


@dataclass
class Target:
    account: dict
    before: dict
    player: object = None
    after: dict | None = None

    @property
    def uid(self):
        return self.account['id']

    def candidate(self):
        if self.after is None:
            self.after = copy.deepcopy(self.before)
        return self.after


@dataclass
class Plan:
    name: str
    args: list
    targets: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)
    controls: list = field(default_factory=list)
    effects: list = field(default_factory=list)
    details: dict = field(default_factory=dict)
    guard: object = None

    def fingerprint(self):
        return digest({'command': self.name, 'args': self.args, 'guard': self.guard,
                       'targets': {str(uid): {
                           'account': t.account, 'state': t.before,
                           'session': t.player.audio_session if t.player else None,
                           'battle': t.player.battle if t.player else None,
                           'trade': t.player.trade if t.player else None}
                           for uid, t in sorted(self.targets.items())}})


@dataclass
class Pending:
    name: str
    args: list
    fingerprint: str
    expires: float


class AuditFile:
    """Bounded rotating local audit. Persistent successes also live in the DB."""
    def __init__(self, path):
        self.path = Path(path)

    def write(self, event):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > 4_000_000:
            for index in range(4, 0, -1):
                previous = Path(str(self.path) + f'.{index}')
                if previous.exists():
                    os.replace(previous, Path(str(self.path) + f'.{index + 1}'))
            os.replace(self.path, Path(str(self.path) + '.1'))
        raw = json.dumps(event, ensure_ascii=True, separators=(',', ':'), allow_nan=False) + '\n'
        with self.path.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())

    def tail(self, count):
        if not self.path.exists():
            return []
        # The bounded read avoids loading even an externally enlarged file.
        with self.path.open('rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - 256_000)
            handle.seek(start)
            raw = handle.read(256_000)
        lines = raw.decode('utf-8', errors='replace').splitlines()
        if start and lines:
            lines = lines[1:]
        return lines[-count:]


class LocalAdmin:
    def __init__(self, service):
        self.service = service
        self.w = service.world
        self.c = service.c
        self.db = service.db
        self.policy = ConsolePolicy.load(service.s.config)
        self.pending = {}
        self.audit = AuditFile(service.s.root / 'logs' / 'admin-console.jsonl')
        self.actor = safe_text(f'LOCAL:{getpass.getuser()}@{socket.gethostname()}')[:160]
        self.serial = asyncio.Lock()
        self.scheduled = None
        self.schedule_task = None
        self.config_path = service.s.root / 'config.ini'
        self.original_config = None
        if self.config_path.is_file():
            self.original_config = self._read_config(self.config_path)

    @staticmethod
    def _read_config(path):
        cfg = configparser.ConfigParser(interpolation=None)
        with Path(path).open('r', encoding='utf-8-sig') as handle:
            cfg.read_file(handle)
        return cfg

    def event(self, command, outcome, **extra):
        return {'id': str(uuid.uuid4()), 'timestamp': int(time.time()),
                'actor': self.actor, 'command': command, 'outcome': outcome, **extra}

    async def log_event(self, event, *, required=True):
        try:
            await asyncio.to_thread(self.audit.write, event)
            return True
        except (OSError, ValueError):
            if required:
                raise RequestError('Console audit is unavailable. No command was executed; check Server/logs permissions and free space.') from None
            log.error('Local console audit write failed after processing an operation; consult the transactional admin_audit table.')
            return False

    def expire(self):
        now = time.monotonic()
        self.pending = {k: v for k, v in self.pending.items() if v.expires > now}

    def available(self, name):
        spec = BY_NAME.get(name)
        require(spec is not None, 'Unknown console command. Type help; chat commands and unsupported mechanics are not installed.')
        require(self.policy.enabled, 'The local console is disabled in configuration.')
        require(name not in self.policy.disabled_commands, 'This command is disabled by the local console policy.')
        require(not spec.developer or self.policy.allow_developer_commands,
                'Developer commands are disabled. Set [console] allow_developer_commands = true, then reloadconfig.')
        return spec

    async def execute(self, line, output=print):
        """Trusted local entry point, also used by isolated integration tests.

        No client packet or HTTP route calls this method. Shield the complete
        command so admitted persistence cannot outlive shutdown's final save.
        """
        lines = await complete_before_cancelling(self._execute(line))
        for value in lines:
            output(safe_text(value))
        return lines

    async def _execute(self, line):
        name = 'invalid'
        spec = None
        try:
            async with self.serial:
                name, args = parse(line)
                if not name:
                    return []
                spec = self.available(name)
                self.expire()
                # Do not write raw unvalidated input or authentication secrets.
                await self.log_event(self.event(name, 'requested'))
                if name == 'cancel':
                    require(len(args) <= 1, 'Usage: cancel [token]')
                    if args:
                        require(args[0] in self.pending, 'No such pending confirmation.')
                        self.pending.pop(args[0])
                    else:
                        self.pending.clear()
                    await self.log_event(self.event(name, 'cancelled'))
                    return ['Pending confirmation cancelled.']
                if name == 'confirm':
                    require(len(args) == 1, 'Usage: confirm <token>')
                    pending = self.pending.pop(args[0], None)
                    require(pending is not None, 'Confirmation is missing, expired or already used. Preview the command again.')
                    name, args = pending.name, pending.args
                    spec = self.available(name)
                else:
                    pending = None
                async with self.w.lock:
                    require(not self.w.stopping and not self.service.stop.is_set(), 'World shutdown has started; no new commands are accepted.')
                    plan = await self.prepare(name, args)
                    fingerprint = plan.fingerprint()
                    if pending:
                        require(pending.expires > time.monotonic(), 'Confirmation expired; preview again.')
                        require(secrets.compare_digest(fingerprint, pending.fingerprint),
                                'The target, session, character, controls or configuration changed. Nothing was executed; preview again.')
                    if spec.confirm and not pending:
                        require(len(self.pending) < MAX_PENDING, 'Too many pending confirmations. Use cancel first.')
                        token = secrets.token_hex(4)
                        await self.log_event(self.event(name, 'confirmation_required', targets=list(plan.targets), details=plan.details))
                        self.pending[token] = Pending(name, list(args), fingerprint, time.monotonic() + self.policy.confirmation_seconds)
                        return [f'PREVIEW {name}: ' + ('; '.join(plan.lines) or spec.summary),
                                f'No change made. Within {self.policy.confirmation_seconds}s enter: confirm {token}',
                                'Any target/session change invalidates this single-use confirmation.']
                    return await self.apply(plan)
        except RequestError as error:
            await self.log_event(self.event(name if name in BY_NAME else 'invalid', 'rejected'), required=False)
            usage = f' Syntax: {spec.name} {spec.usage}'.rstrip() if spec and name not in ('help', 'confirm') else ''
            return [f'ERROR: {error}{usage}']
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            await self.log_event(self.event(name if name in BY_NAME else 'invalid', 'failed', error=type(error).__name__), required=False)
            return [f'ERROR: Invalid command data ({type(error).__name__}). No requested change was published. Type help {name if name in BY_NAME else ""}.']
        except Exception as error:
            await self.log_event(self.event(name if name in BY_NAME else 'invalid', 'failed', error=type(error).__name__), required=False)
            # Drivers may include credentials in exception messages: no repr or traceback content here.
            log.error('Local command %s failed (%s); no exception payload was logged.', name if name in BY_NAME else 'invalid', type(error).__name__)
            return [f'ERROR: Command failed ({type(error).__name__}). Check database ownership/availability and local audit storage.']

    async def target(self, plan, text, *, online=False, idle=False):
        if text.startswith('#') or text.casefold().startswith('id:'):
            uid = number(text[1:] if text.startswith('#') else text[3:], 1, 2**53-1, 'Account ID')
            account = await asyncio.to_thread(self.db.admin_account, uid=uid)
        else:
            require(re.fullmatch(r'[A-Za-z0-9_]{3,20}', text) is not None, 'Select an exact username, #ID or id:ID.')
            account = await asyncio.to_thread(self.db.admin_account, login=text)
        require(account is not None, 'That account does not exist.')
        uid = account['id']
        if uid not in plan.targets:
            player = self.w.players.get(uid)
            require(player is None or not player.closed, 'This account is disconnecting; retry after logout completes.')
            state = copy.deepcopy(player.state) if player else await asyncio.to_thread(self.db.load, uid)
            plan.targets[uid] = Target(account, state, player)
        target = plan.targets[uid]
        require(not online or target.player is not None, 'That player must be online for this operation.')
        require(not idle or target.player is None or not (target.player.battle or target.player.trade),
                'Finish the target\'s battle/trade first; live gameplay is never overwritten.')
        return target

    def exact(self, table, text, label):
        if text in table:
            return text
        keys = [k for k, value in table.items() if value.get('name', '').casefold() == text.casefold()]
        require(bool(keys), f'Unknown {label}; use the {label} catalog search and exact ID.')
        require(len(keys) == 1, f'Ambiguous {label} name; select an ID: ' + ', '.join(keys[:12]))
        return keys[0]

    def mon(self, target, text, *, edit=False):
        state = target.candidate() if edit else target.before
        if text.casefold().startswith('party:'):
            slot = number(text[6:], 1, 6, 'Party slot') - 1
            require(slot < len(state['party']), 'That party slot is empty.')
            text = state['party'][slot]
        mon = next((m for m in state['creatures'] if m['uid'] == text), None)
        require(mon is not None, 'Use a Pokémon UID owned by this account, or party:1 through party:6.')
        if edit:
            self.c.growth.ensure(mon)
            self.c.growth.migrate_move_namespace(mon)
        return mon

    def mon_line(self, mon):
        return f'{mon["uid"]} | {self.c.varieties.display_name(mon)} [{mon["species"]}] Lv.{mon["level"]} HP {mon["hp"]}/{self.c.stats(mon)[0]}'

    @staticmethod
    def count(args, lo, hi=None):
        require(lo <= len(args) <= (lo if hi is None else hi), 'Incorrect number of arguments.')

    @staticmethod
    def page(rows, page):
        pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
        require(1 <= page <= pages, f'Page must be 1..{pages}.')
        return [f'{len(rows)} results | page {page}/{pages}', *rows[(page-1)*PAGE_SIZE:page*PAGE_SIZE]]

    def adjust_hp(self, mon, old_max, old_hp):
        maximum = self.c.stats(mon)[0]
        mon['hp'] = min(maximum, max(1, old_hp + maximum - old_max)) if old_hp > 0 else 0

    def safe_destination(self, target, key, x, y):
        m = self.c.maps[key]
        require(m.get('playable', True), 'This map is not playable.')
        require(self.w.walkable(m, x, y, False, state=target.before), 'Destination is not walkable land for this character; choose another tile.')
        require(not any(w['x'] == x and w['y'] == y for w in m.get('warps', [])), 'Do not teleport onto a warp; choose an adjacent walkable tile.')
        # Preserve home, badges, Cut flags, collection and every other private field.
        state = target.candidate()
        state.update(map=key, x=x, y=y, surf=False, direction='down', warpReturns=[])
        self.w.adventure.visit(state, key)

    async def prepare(self, name, args):
        plan = Plan(name, list(args))
        c, w, s = self.c, self.w, self.service.s
        if name == 'help':
            self.count(args, 0, 1)
            visible = [sp for sp in COMMANDS if self.policy.allows(sp)]
            if args:
                key = canonical(args[0])
                if key in BY_NAME:
                    sp = self.available(key)
                    plan.lines = [f'{sp.name} {sp.usage}'.rstrip(), sp.summary,
                                  'Aliases: ' + (', '.join(sp.aliases) or 'none'),
                                  'Safety: ' + ('single-use confirmation required' if sp.confirm else 'validated before execution')]
                    return plan
                visible = [sp for sp in visible if sp.category.casefold() == args[0].casefold()]
                require(bool(visible), 'Unknown command/category; type help.')
            plan.lines = ['LOCAL SERVER CONSOLE ONLY | exact username or #accountID | quote multi-word names',
                          'Optional leading / is accepted HERE, not in player chat. Developer commands are ' + ('ENABLED.' if self.policy.allow_developer_commands else 'disabled.'),
                          *[f'[{sp.category}] {sp.name} {sp.usage} — {sp.summary}' for sp in visible]]
        elif name in ('serverinfo', 'online', 'version', 'uptime', 'time'):
            self.count(args, 0)
            if name == 'online': plan.lines = [f'Online {len(w.players)}/{s.max_players}']
            elif name == 'uptime': plan.lines = [f'World uptime: {int(time.monotonic()-w.started)} seconds']
            elif name == 'version': plan.lines = [f'Pokémon NXT MMO {c.data["version"]} | content {c.pack} | local console 1']
            elif name == 'time':
                now = datetime.now().astimezone()
                period = 'morning' if 4 <= now.hour < 10 else 'day' if 10 <= now.hour < 18 else 'night'
                plan.lines = [f'{now.isoformat(timespec="seconds")} | Crystal encounters: {period} | no clock override']
            else:
                plan.lines = [f'Pokémon NXT MMO {c.data["version"]} | pack {c.pack}',
                              f'Online {len(w.players)}/{s.max_players} | pending logins {self.service.pending} | maps {len(c.maps)}',
                              f'Battles {len(w.battles)} | trades {len(w.trades)} | tick {w.last_tick_ms:.2f}ms / max {w.max_tick_ms:.2f}ms',
                              f'Uptime {int(time.monotonic()-w.started)}s | backend {s.get("database","backend")} | local-only administration']
        elif name == 'who':
            self.count(args, 0, 1)
            rows = [f'#{p.id} {p.username} | {p.state["map"]} ({p.state["x"]},{p.state["y"]})' for p in sorted(w.players.values(), key=lambda p: p.id)]
            plan.lines = self.page(rows, number(args[0], 1, 1000, 'Page') if args else 1)
        elif name in ('species', 'items', 'moves', 'maps'):
            self.count(args, 0, 2)
            query = args[0].casefold() if args else ''
            page = number(args[1], 1, 10000, 'Page') if len(args) == 2 else 1
            table = {'species': c.species, 'items': c.items, 'moves': c.moves, 'maps': c.maps}[name]
            rows = []
            for key, value in sorted(table.items()):
                if query and query not in key.casefold() and query not in value.get('name', '').casefold(): continue
                if name == 'maps' and not value.get('playable', True): continue
                suffix = ''
                if name == 'species': suffix = ' | ' + ','.join(v for v in VARIETIES if c.varieties.supported(key, v))
                elif name == 'maps': suffix = f' | {value["region"]} spawn {value["spawn"]}'
                rows.append(f'{key}: {value.get("name",key)}{suffix}')
            plan.lines = self.page(rows, page)
        elif name == 'iteminfo':
            self.count(args, 1)
            key = self.exact(c.items, args[0], 'items')
            plan.lines = [f'{key}: ' + json.dumps(c.items[key], ensure_ascii=False, sort_keys=True)]
        elif name in ('playerinfo', 'where', 'team', 'collection', 'pokemoninfo', 'bag', 'money', 'ipinfo'):
            self.count(args, 2 if name == 'pokemoninfo' else 1, 2 if name in ('collection', 'pokemoninfo') else 1)
            t = await self.target(plan, args[0], online=name == 'ipinfo')
            state, account = t.before, t.account
            if name == 'playerinfo':
                effective_ban = bool(account['banned_raw']) and (not account['ban_until'] or account['ban_until'] > int(time.time()))
                plan.lines = [f'#{t.uid} {account["username"]} | ' + ('online' if t.player else 'offline'),
                              f'Home {state["home"]} | owned {len(state["creatures"])} | party {len(state["party"])} | money {state["money"]}',
                              f'Badges: {state.get("adventure",{}).get("badges",[])} | revision {state["revision"]}',
                              f'Banned {effective_ban} | locked {bool(account["locked"])} | frozen {bool(account["frozen"])} | trade blocked {bool(account["trade_blocked"])}']
            elif name == 'where': plan.lines = [f'#{t.uid} {account["username"]}: {state["map"]} ({state["x"]}, {state["y"]}) | {"live" if t.player else "saved"}']
            elif name == 'money': plan.lines = [f'#{t.uid} {account["username"]}: {state["money"]}']
            elif name == 'bag': plan.lines = [f'Bag for #{t.uid} {account["username"]}', *[f'{key}: {value}' for key, value in sorted(state['items'].items()) if value]]
            elif name == 'team':
                byid = {m['uid']: m for m in state['creatures']}
                plan.lines = [f'party:{i+1} | {self.mon_line(byid[uid])}' for i, uid in enumerate(state['party'])]
            elif name == 'collection':
                plan.lines = self.page([self.mon_line(m) for m in state['creatures']], number(args[1], 1, 1000, 'Page') if len(args)>1 else 1)
            elif name == 'pokemoninfo':
                mon = self.mon(t, args[1]); plan.details['pokemon'] = mon['uid']
                plan.lines = [self.mon_line(mon), f'EXP {mon["exp"]} | nature {NATURES[mon["nature"]]} | original trainer {mon["originalTrainer"]}',
                              'IVs HP/ATK/DEF/SPA/SPD/SPE: ' + '/'.join(str(mon['ivs'][i]) for i in (0,1,2,4,5,3)),
                              *[f'slot {i+1}: {mv["id"]} {c.moves[str(mv["id"])]["name"]} PP {mv["pp"]}' for i,mv in enumerate(mon['moves'])],
                              'Eligible evolutions: ' + json.dumps(c.growth.options(mon), ensure_ascii=False)]
            else: plan.lines = [f'#{t.uid} {account["username"]} direct peer: {getattr(t.player,"connection_peer","unavailable")}']
        elif name in ('givepokemon', 'clonepokemon', 'testbattle'):
            self.count(args, 2, 2 if name == 'clonepokemon' else 4)
            t = await self.target(plan, args[0], online=name=='testbattle', idle=True)
            if name == 'clonepokemon':
                mon = copy.deepcopy(self.mon(t, args[1])); mon['uid'] = str(uuid.uuid4())
            else:
                key = self.exact(c.species, args[1], 'species')
                level = number(args[2], 1, 100, 'Level') if len(args)>2 else 5
                variety = args[3].casefold() if len(args)>3 else 'normal'
                require(variety in VARIETIES and c.varieties.supported(key, variety), 'This species has no verified front for that variety.')
                mon = c.new_mon(key, level, 'Console test' if name=='testbattle' else t.account['username'], variety=variety)
            plan.details['pokemon'] = mon['uid']; plan.details['species'] = mon['species']; plan.details['variety'] = variety_key(mon)
            if name == 'testbattle':
                require(any(m['hp']>0 for m in t.before['creatures'] if m['uid'] in t.before['party']), 'The party needs healing before a test duel.')
                plan.effects.append(('testbattle', t.uid, mon))
                plan.lines = [f'Started isolated test duel for {t.account["username"]}: {self.mon_line(mon)}. No progression rewards or capture.']
            else:
                state = t.candidate(); require(len(state['creatures'])<s.max_owned, 'The collection is full; no Pokémon was granted.')
                state['creatures'].append(mon)
                if len(state['party'])<6: state['party'].append(mon['uid'])
                plan.lines = [f'Granted to {t.account["username"]}: {self.mon_line(mon)} | ' + ('party' if mon['uid'] in state['party'] else 'PC storage')]
        elif name in ('removepokemon','setlevel','setexp','learn','forget','setnature','setivs','setvariety','setshiny','sethp','setstatus','addmove','clearmoves','evolve'):
            limits = {'removepokemon':(2,2),'clearmoves':(2,2),'learn':(4,4),'addmove':(4,4),'setivs':(8,8),'evolve':(2,3)}
            self.count(args, *limits.get(name, (3,3)))
            t = await self.target(plan, args[0], idle=True)
            state = t.candidate(); mon = self.mon(t, args[1], edit=True)
            old_max, old_hp = c.stats(mon)[0], mon['hp']
            plan.details['pokemon'] = mon['uid']
            if name == 'removepokemon':
                state['creatures'] = [m for m in state['creatures'] if m['uid'] != mon['uid']]
                state['party'] = [uid for uid in state['party'] if uid != mon['uid']]
                require(state['party'] and any(m['hp']>0 for m in state['creatures'] if m['uid'] in state['party']), 'Keep at least one healthy party Pokémon; this removal is refused.')
            elif name in ('setlevel', 'setexp'):
                growth = c.species[mon['species']]['growth']
                old_level = mon['level']
                if name=='setlevel':
                    desired = number(args[2],1,100,'Level')
                    total = c.xp(desired,growth)
                else:
                    total = number(args[2],0,c.xp(100,growth),'Total EXP')
                    desired = max(n for n in range(1,101) if c.xp(n,growth)<=total)
                mon['exp'] = total; mon['level'] = desired
                if desired > old_level:
                    c.growth.queue_moves(mon,old_level,desired)
                elif desired < old_level:
                    mon['pendingLearn'] = [entry for entry in mon.get('pendingLearn',[]) if c.growth.earned_entry(mon,entry)]
                self.adjust_hp(mon,old_max,old_hp)
                plan.details.update(level=mon['level'], total_exp=mon['exp'])
            elif name in ('learn', 'addmove'):
                move = int(self.exact(c.moves, args[2], 'moves')); slot = number(args[3],1,4,'Move slot')-1
                if name == 'learn':
                    if mon.get('pendingLearn') and mon['pendingLearn'][0]['move']==move: t.after = c.growth.learn(state,mon['uid'],move,slot)
                    else: t.after = c.growth.remember(state,mon['uid'],move,slot)
                else:
                    require(slot<=len(mon['moves']), 'Choose an existing slot or the next empty slot.')
                    require(not any(m['id']==move for i,m in enumerate(mon['moves']) if i!=slot), 'Duplicate known moves are not allowed.')
                    entry = {'id':move,'pp':c.moves[str(move)]['pp']}
                    if slot==len(mon['moves']): mon['moves'].append(entry)
                    else: mon['moves'][slot] = entry
                    mon['pendingLearn'] = [e for e in mon['pendingLearn'] if e.get('move')!=move]
                plan.details.update(move=move, slot=slot+1)
            elif name == 'forget':
                slot = number(args[2],1,4,'Move slot')-1; require(slot<len(mon['moves']), 'That move slot is empty.'); mon['moves'].pop(slot)
            elif name == 'clearmoves': mon['moves'] = []
            elif name == 'setnature':
                natures = {v.casefold():i for i,v in enumerate(NATURES)}
                mon['nature'] = natures[args[2].casefold()] if args[2].casefold() in natures else number(args[2],0,24,'Nature ID')
                self.adjust_hp(mon,old_max,old_hp)
            elif name == 'setivs':
                vals = [number(v,0,31,'IV') for v in args[2:]]
                mon['ivs'] = [vals[i] for i in (0,1,2,5,3,4)]; self.adjust_hp(mon,old_max,old_hp)
            elif name in ('setvariety', 'setshiny'):
                value = ('shiny' if boolean(args[2]) else 'normal') if name=='setshiny' else args[2].casefold()
                require(value in VARIETIES and c.varieties.supported(mon['species'],value), 'No verified front exists for that species/variety.')
                mon.update(variety=value, shiny=value=='shiny'); plan.details['variety'] = value
            elif name == 'sethp': mon['hp'] = number(args[2],0,old_max,'HP')
            elif name == 'setstatus':
                value = args[2].casefold(); require(value in ('none','burn','poison','toxic','paralysis','sleep'), 'Unsupported status; no battle mechanic is invented.')
                mon['status'] = '' if value=='none' else value; mon['sleep'] = 3 if value=='sleep' else 0
            else:
                options = [v for v in c.growth.options(mon) if not v['deferred']]
                require(options, 'No eligible authored evolution exists. Meet its level/item/trade condition and resume any paused choice.')
                targets = list(dict.fromkeys(v['target'] for v in options))
                target = self.exact(c.species,args[2],'species') if len(args)>2 else targets[0] if len(targets)==1 else None
                require(target is not None, 'Choose an evolution target explicitly: '+', '.join(v['target'] for v in options))
                eligible = [v for v in options if v['target']==target]
                selected = next((v for v in eligible if not v.get('item') or state['items'].get(v['item'],0)>0), eligible[0] if eligible else {})
                t.after = c.growth.evolve(state,mon['uid'],target,item=selected.get('item')); plan.details['target_species'] = target
            plan.lines = [f'{name} for #{t.uid} {t.account["username"]}, Pokémon {mon["uid"]}' + (f': {plan.details}' if len(plan.details)>1 else '')]
        elif name in ('heal', 'healall'):
            self.count(args, 1 if name=='heal' else 0)
            if name=='heal': targets = [await self.target(plan,args[0],idle=True)]
            else:
                targets = []
                for p in sorted(w.players.values(),key=lambda p:p.id):
                    if p.closed or p.battle or p.trade:
                        plan.lines.append(f'Skipped busy/disconnecting player #{p.id} {p.username}'); continue
                    targets.append(await self.target(plan,f'#{p.id}',idle=True))
            for t in targets:
                state = t.candidate()
                for mon in state['creatures']:
                    if mon['uid'] in state['party']: c.heal(mon)
            plan.lines.insert(0,f'Heal {len(targets)} party/parties atomically.')
        elif name in ('giveitem','removeitem','setitem','clearinventory','givemoney','removemoney','setmoney'):
            self.count(args, 1 if name=='clearinventory' else 3 if 'item' in name else 2)
            t = await self.target(plan,args[0],idle=True); state = t.candidate()
            if name == 'clearinventory': state['items'] = {}; plan.details['bag_stacks'] = len(t.before['items'])
            elif 'item' in name:
                key = self.exact(c.items,args[1],'items'); amount = number(args[2],0 if name=='setitem' else 1,999,'Quantity')
                old = state['items'].get(key,0); new = old+amount if name=='giveitem' else old-amount if name=='removeitem' else amount
                require(0<=new<=999,'This would underflow the inventory or exceed the 999 stack cap.')
                state['items'][key] = new; plan.details.update(item=key,before=old,after=new)
            else:
                amount = number(args[1],0 if name=='setmoney' else 1,MAX_MONEY,'Currency'); old = state['money']
                new = old+amount if name=='givemoney' else old-amount if name=='removemoney' else amount
                require(0<=new<=MAX_MONEY,'This would underflow the balance or exceed its existing currency cap.')
                state['money'] = new; plan.details.update(before=old,after=new)
            plan.lines = [f'{name} for #{t.uid} {t.account["username"]}: {plan.details}']
        elif name == 'economy':
            self.count(args,0)
            totals = await asyncio.to_thread(self.db.admin_economy,{p.id:p.state['money'] for p in w.players.values()})
            plan.lines = [json.dumps(totals,sort_keys=True)]
        elif name in ('teleport','goto','unstuck'):
            self.count(args,1 if name=='unstuck' else 2,1 if name=='unstuck' else 2 if name=='goto' else 4)
            t = await self.target(plan,args[0],idle=True)
            if name=='goto':
                destination = await self.target(plan,args[1]); require(t.uid!=destination.uid,'Select two different players.')
                key = destination.before['map']; x,y = destination.before['x'],destination.before['y']
                m = c.maps[key]
                points = [(x+dx,y+dy) for dx,dy in ((0,1),(1,0),(0,-1),(-1,0),(0,0))]
                points = [(a,b) for a,b in points if w.walkable(m,a,b,False,state=t.before) and not any(v['x']==a and v['y']==b for v in m.get('warps',[]))]
                require(points,'There is no safe land tile beside that player.'); x,y = points[0]
            else:
                require(len(args) != 3, 'Provide both x and y, or neither.')
                key = c.data['homes'][t.before['home']] if name=='unstuck' else self.exact(c.maps,args[1],'maps')
                m = c.maps[key]
                x,y = (number(args[2],0,m['width']-1,'X'), number(args[3],0,m['height']-1,'Y')) if len(args)==4 else m['spawn']
            self.safe_destination(t,key,x,y); plan.effects.append(('teleport',t.uid)); plan.details.update(map=key,x=x,y=y)
            plan.lines = [f'Move #{t.uid} {t.account["username"]} to {key} ({x},{y}); home, badges and personal Cut state are preserved.']
        elif name in ('warn','kick','ban','unban','lockaccount','unlockaccount','resetpassword','freeze','unfreeze','blocktrade','tradecancel'):
            limits = {'warn':(2,20),'kick':(1,20),'ban':(3,20),'lockaccount':(2,20),'blocktrade':(2,2)}
            self.count(args,*limits.get(name,(1,1)))
            t = await self.target(plan,args[0],online=name in ('kick','tradecancel'),idle=name in ('freeze',))
            reason = ' '.join(args[2:] if name=='ban' else args[1:]) if name in ('warn','kick','ban','lockaccount') else ''
            require(len(reason)<=240,'Reason must be at most 240 characters.')
            plan.details['reason'] = reason
            if name=='ban':
                duration = args[1].casefold()
                if duration=='permanent': seconds=0
                else:
                    match = re.fullmatch(r'([1-9]\d{0,5})([smhd])',duration)
                    require(match is not None,'Duration must be permanent, 10m, 2h, 7d, or another s/m/h/d value.')
                    seconds=int(match[1])*{'s':1,'m':60,'h':3600,'d':86400}[match[2]]
                    require(1<=seconds<=365*86400,'Temporary bans must be at most 365 days.')
                # Duration is applied at execution, not at preview time.
                plan.effects.append(('ban_duration',t.uid,seconds)); plan.details['duration_seconds']=seconds
            elif name=='unban': plan.controls.append((t.uid,{'banned_raw':0,'ban_until':0}))
            elif name in ('lockaccount','unlockaccount'): plan.controls.append((t.uid,{'locked':int(name=='lockaccount')}))
            elif name in ('freeze','unfreeze'): plan.controls.append((t.uid,{'frozen':int(name=='freeze')}))
            elif name=='blocktrade': plan.controls.append((t.uid,{'trade_blocked':int(boolean(args[1]))}))
            elif name=='resetpassword': plan.effects.append(('password',t.uid))
            elif name=='tradecancel': plan.effects.append(('tradecancel',t.uid))
            if name in ('kick','ban','lockaccount','resetpassword') and t.player: plan.effects.append(('kick',t.uid))
            if name=='warn': plan.effects.append(('warn',t.uid,reason))
            plan.lines = [f'{name}: #{t.uid} {t.account["username"]}' + (f' | {reason}' if reason else '')]
        elif name in ('history','warnings','tradehistory'):
            self.count(args,1,2); t=await self.target(plan,args[0]); limit=number(args[1],1,100,'Limit') if len(args)>1 else 20
            if name=='tradehistory': rows=await asyncio.to_thread(self.db.admin_trade_history,t.uid,limit)
            else: rows=await asyncio.to_thread(self.db.admin_history,t.uid,command='warn' if name=='warnings' else None,limit=limit)
            plan.lines=[f'{len(rows)} recent {name} records for #{t.uid}',*[json.dumps(row,ensure_ascii=False,sort_keys=True) for row in rows]]
        elif name=='connections':
            self.count(args,0)
            plan.lines=[f'{len(w.players)} authenticated sessions; {self.service.pending} pending.',*[f'#{p.id} {p.username}: {getattr(p,"connection_peer","unavailable")}' for p in sorted(w.players.values(),key=lambda p:p.id)]]
        elif name in ('save','saveall'):
            self.count(args,0,1 if name=='save' else 0)
            ids=[args[0]] if args else [f'#{p.id}' for p in w.players.values() if not p.closed]
            for text in ids:
                t=await self.target(plan,text); t.candidate()
            plan.lines=[f'Checkpoint {len(plan.targets)} character(s) in one transaction.']
        elif name=='reloadconfig':
            self.count(args,0)
            require(self.original_config is not None,'Original config was not loaded; restart through the supplied server launcher.')
            try: cfg=self._read_config(self.config_path); policy=ConsolePolicy.load(cfg); registration=cfg.getboolean('world','registration_enabled')
            except (OSError,ValueError,configparser.Error): raise RequestError('Configuration cannot be parsed safely. No live setting was changed.') from None
            def restricted(config):
                return {section:{key:value for key,value in config.items(section) if not (section=='world' and key=='registration_enabled')}
                        for section in config.sections() if section!='console'}
            require(restricted(cfg)==restricted(self.original_config),'Only [console] and world.registration_enabled can be reloaded. Restore other edits or perform a clean restart.')
            plan.guard=digest({section:dict(cfg.items(section)) for section in cfg.sections()})
            plan.effects.append(('reload',cfg,policy,registration)); plan.lines=['Reload supported console policy and registration_enabled only; no content, script, network or database reload.']
        elif name in ('gc','memory','threads','logs'):
            self.count(args,0,1 if name=='logs' else 0)
            if name=='gc': plan.effects.append(('gc',))
            elif name=='memory': plan.lines=self.memory_lines()
            elif name=='threads': plan.lines=[f'{t.name}: id={t.ident}, daemon={t.daemon}, alive={t.is_alive()}' for t in threading.enumerate()]
            else: plan.lines=await asyncio.to_thread(self.audit.tail,number(args[0],1,100,'Lines') if args else 20)
        elif name in ('shutdown','restart','cancelshutdown'):
            self.count(args,0,0 if name=='cancelshutdown' else 1)
            plan.guard=self.scheduled
            if name=='cancelshutdown': require(self.scheduled is not None,'No shutdown or restart is scheduled.'); plan.effects.append(('cancelshutdown',)); plan.lines=['Cancel the pending shutdown/restart.']
            else:
                require(self.scheduled is None,'A shutdown/restart is already scheduled. Cancel it first.')
                seconds=number(args[0],0,3600,'Delay') if args else 0
                plan.effects.append(('schedule',name,seconds)); plan.details['delay_seconds']=seconds
                plan.lines=[f'{name} in {seconds} seconds, after clean character saves and lease release.']
        elif name=='createaccount':
            self.count(args,3)
            username,_=credentials(args[0],'Valid-console-placeholder-password')
            region=args[1].capitalize(); require(region in c.data['homes'],'Choose Kanto or Johto.')
            starter=self.exact(c.species,args[2],'species'); require(starter in c.data['starters'],'Choose an existing selectable starter.')
            require(await asyncio.to_thread(self.db.admin_account,login=username) is None,'That account already exists.')
            plan.effects.append(('create',username,region,starter)); plan.details.update(username=username,home=region,starter=starter)
            plan.lines=[f'Create ordinary test account {username}, {region}, {c.species[starter]["name"]}. Generated password will be shown only after confirmation/commit.']
        elif name in ('win','lose','endbattle'):
            self.count(args,1); t=await self.target(plan,args[0],online=True)
            b=w.battles.get(t.player.battle)
            require(b is not None and getattr(b,'console_test',False) and b.kind=='duel' and b.players==[t.uid,None],
                    'This command only controls an isolated console-created test duel, never a live wild/trainer/player battle.')
            plan.effects.append(('endbattle',t.uid,b.id,0 if name=='win' else 1 if name=='lose' else None)); plan.guard=(b.id,b.turn)
            plan.lines=[f'End console test duel for #{t.uid}: {name}. Real progress is unchanged.']
        else:
            raise RequestError('This command has no installed handler.')
        return plan

    async def apply(self, plan):
        """Called under the world lock. Failure before commit publishes nothing."""
        event=self.event(plan.name,'committed',targets=list(plan.targets),arguments=plan.args,details=plan.details,
                         source_revisions={str(t.uid):t.before['revision'] for t in plan.targets.values()})
        await self.log_event({**event,'outcome':'validated'})
        passwords=[]; create=None; secrets_to_show=[]
        controls=list(plan.controls)
        for effect in plan.effects:
            if effect[0]=='password':
                password=secrets.token_urlsafe(24); encoded=await self.service.hash(password)
                passwords.append((effect[1],encoded)); secrets_to_show.append(f'NEW PASSWORD for #{effect[1]} (shown once, not logged): {password}')
            elif effect[0]=='create':
                _,username,region,starter=effect
                password=secrets.token_urlsafe(24); encoded=await self.service.hash(password)
                create=(username,encoded,self.w.initial(username,region,starter,0))
                secrets_to_show.append(f'NEW PASSWORD for {username} (shown once, not logged): {password}')
            elif effect[0]=='ban_duration':
                controls.append((effect[1],{'banned_raw':1,'ban_until':int(time.time())+effect[2] if effect[2] else 0}))
        records=[]
        for t in plan.targets.values():
            if t.after is not None:
                self.w.validate_state(t.after)
                self.w.adventure.observe(t.after,[m['species'] for m in t.after['creatures']],caught=True)
                self.c.varieties.observe(t.after,t.after['creatures'],caught=True)
                self.w.adventure.refresh_unlocks(t.after)
                t.after['revision']=t.before['revision']+1
                records.append((t.uid,t.before['revision'],t.after))
        created=await asyncio.to_thread(self.db.admin_commit,event,records=records,controls=controls,passwords=passwords,
                                        expected_epochs=[(t.uid,t.account['epoch']) for t in plan.targets.values()],create=create)
        # The DB ledger is durable now. Never misreport an ancillary audit-file
        # failure as a rollback or retry a successful grant/password operation.
        published=True
        try:
            for t in plan.targets.values():
                if t.after is not None and t.player:
                    t.player.state=t.after; t.player.saved_revision=t.after['revision']; self.w.send_state(t.player)
            for uid,changes in controls:
                t=plan.targets[uid]; p=t.player
                if p:
                    if 'frozen' in changes:
                        p.frozen=bool(changes['frozen']); p.send('notice',message='Your gameplay has been frozen by the local administrator.' if p.frozen else 'Your gameplay freeze has been removed.')
                    if 'trade_blocked' in changes:
                        p.trade_blocked=bool(changes['trade_blocked'])
                        if p.trade_blocked: self.cancel_trade(p)
                        p.send('notice',message='Your account trading restriction was updated by the local administrator.')
            for effect in plan.effects:
                kind=effect[0]
                if kind=='teleport':
                    p=plan.targets[effect[1]].player
                    if p:
                        self.w.follower_anchor(p); p.last_encounter=time.monotonic(); self.w.send_map(p,'home'); p.send('notice',message='Your location was updated by the local administrator.')
                elif kind=='testbattle':
                    p=plan.targets[effect[1]].player
                    b=Battle(self.c,'duel',[p.id,None],[p.username,'Console test'],[self.w.party(p),[effect[2]]],[{},{}],self.service.s.int('gameplay','battle_turn_seconds'),audio_source=p.state['map'].split('_',1)[0])
                    b.console_test=True; self.w.battles[b.id]=b; p.battle=b.id; p.send('battle',battle=b.view(0))
                elif kind=='endbattle':
                    p=plan.targets[effect[1]].player; b=self.w.battles.pop(effect[2]); b.ended=True; b.winner=effect[3]; b.logs=['Local console test ended; no real rewards or progress were changed.']; b.reset_audio(); b.audio('battle_end',reason='console_test'); p.battle=None; p.send('battle',battle=b.view(0))
                elif kind=='tradecancel': self.cancel_trade(plan.targets[effect[1]].player)
                elif kind=='warn':
                    p=plan.targets[effect[1]].player
                    if p: p.send('notice',message='Administrator warning: '+effect[2])
                elif kind=='kick':
                    p=plan.targets[effect[1]].player
                    if p:
                        p.closed=True
                        ws=self.service.sockets.get(p.id)
                        if ws is not None:
                            task=asyncio.create_task(self.disconnect(ws))
                            self.service.admin_disconnect_tasks.add(task); task.add_done_callback(self.service.admin_disconnect_tasks.discard)
                elif kind=='reload':
                    _,cfg,policy,registration=effect
                    self.policy=policy; self.original_config=cfg
                    self.service.s.config.set('world','registration_enabled','true' if registration else 'false')
                    self.pending.clear()
                elif kind=='schedule': self.schedule(effect[1],effect[2])
                elif kind=='cancelshutdown':
                    if self.schedule_task: self.schedule_task.cancel()
                    self.schedule_task=None; self.scheduled=None
                elif kind=='gc': plan.lines=[f'Collected {gc.collect()} unreachable Python objects. This is not a guaranteed OS-memory release.']
        except Exception as error:
            published=False
            self.w.stopping=True; self.service.stop.set()
            log.error('Committed admin command %s needs presentation recovery (%s). No automatic retry.',plan.name,type(error).__name__)
        if created is not None:event={**event,'targets':[created]}
        file_ok=await self.log_event(event,required=False)
        lines=['OK: '+line for line in plan.lines] or ['OK: '+plan.name]
        if created is not None: lines.append(f'Created account #{created}.')
        lines.extend(secrets_to_show)
        if not published: lines.append('WARNING: Database change and audit COMMITTED, but a live presentation operation failed. Do not repeat the command; the world is stopping safely. Inspect the world log before restarting.')
        if not file_ok: lines.append('WARNING: Change COMMITTED; local audit file could not be appended. The admin_audit database record is authoritative. Do not repeat this command.')
        return lines

    async def disconnect(self, ws):
        try:
            if not ws.closed:
                await asyncio.wait_for(ws.send_json({'type':'notice','message':'Your session was disconnected by the local server administrator.'}),3)
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            if not ws.closed:
                try: await asyncio.wait_for(ws.close(code=1008,message=b'Local administrator action'),5)
                except Exception: pass

    def cancel_trade(self, player):
        if player is None: return
        if player.trade in self.w.trades: self.w.cancel_trade(self.w.trades[player.trade],'The local administrator cancelled this trade. No uncommitted assets were transferred.')
        for key,invite in list(self.w.invites.items()):
            if invite['kind']=='trade' and player.id in (invite['from'],invite['to']):
                self.w.invites.pop(key,None)
                for uid in (invite['from'],invite['to']):
                    peer=self.w.players.get(uid)
                    if peer: peer.send('invite_expired',id=key)

    def schedule(self, action, seconds):
        self.scheduled={'action':action,'deadline':time.monotonic()+seconds}
        async def finish():
            try:
                await asyncio.sleep(seconds)
                async with self.w.lock:
                    if self.service.stop.is_set(): return
                    self.w.stopping=True
                    self.service.restart_requested=action=='restart'
                    self.service.stop.set()
            except asyncio.CancelledError:
                return
        self.schedule_task=asyncio.create_task(finish(),name='NXT-Scheduled-Shutdown')
        for p in self.w.players.values(): p.send('notice',message=f'World server {action} scheduled in {seconds} seconds. Your character will be saved.')

    async def close(self):
        self.pending.clear()
        if self.schedule_task:
            self.schedule_task.cancel()
            await asyncio.gather(self.schedule_task,return_exceptions=True)
        self.schedule_task=None

    @staticmethod
    def memory_lines():
        lines=[f'Python GC allocation counters: {gc.get_count()}']
        try:
            if os.name=='nt':
                import ctypes
                from ctypes import wintypes
                class Counters(ctypes.Structure):
                    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD), *[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]]
                counters=Counters(); counters.cb=ctypes.sizeof(counters)
                kernel=ctypes.WinDLL('kernel32',use_last_error=True); psapi=ctypes.WinDLL('psapi',use_last_error=True)
                kernel.GetCurrentProcess.restype=wintypes.HANDLE
                psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
                psapi.GetProcessMemoryInfo.restype=wintypes.BOOL
                if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb): raise OSError('Memory query failed')
                lines.insert(0,f'Current working set: {counters.WorkingSetSize} bytes | peak: {counters.PeakWorkingSetSize} bytes')
            elif Path('/proc/self/status').is_file():
                rows=Path('/proc/self/status').read_text().splitlines()
                lines[:0]=[v for v in rows if v.startswith(('VmRSS:','VmHWM:'))]
            else: lines.insert(0,'Process resident-memory measurement is unavailable on this platform.')
        except (OSError,AttributeError): lines.insert(0,'Process resident-memory measurement is unavailable on this platform.')
        return lines

    async def console(self):
        """TTY-only bounded reader; stdin EOF disables input, not the world.

        A daemon thread handles blocking platform console input. It never reads
        or mutates gameplay. Reserving a slot BEFORE posting to the event loop
        bounds both the input queue and the scheduled-callback backlog. A paste
        waits for space instead of dropping its EOF marker or queuing unbounded
        callbacks. Shutdown never waits on a blocked platform readline().
        """
        if not self.policy.enabled:
            print('Local administrator console disabled by configuration.',flush=True); return
        if sys.stdin is None or not sys.stdin.isatty():
            print('Local administrator console inactive: input is not an interactive terminal. Redirected/piped commands are not accepted.',flush=True); return
        queue=asyncio.Queue(maxsize=32); loop=asyncio.get_running_loop(); stopped=threading.Event()
        slots=threading.BoundedSemaphore(32)
        def enqueue(value):
            if stopped.is_set():
                slots.release(); return
            # Every scheduled callback owns exactly one capacity reservation.
            queue.put_nowait(value)
        def submit(value):
            while not stopped.is_set():
                if not slots.acquire(timeout=.25): continue
                if stopped.is_set():
                    slots.release(); return False
                try: loop.call_soon_threadsafe(enqueue,value)
                except RuntimeError:
                    slots.release(); return False
                return True
            return False
        def reader():
            try:
                while not stopped.is_set():
                    raw=sys.stdin.readline(MAX_LINE+2)
                    if raw=='':
                        submit(None); return
                    if len(raw)>MAX_LINE and not raw.endswith('\n'):
                        while raw and not raw.endswith('\n'): raw=sys.stdin.readline(MAX_LINE+2)
                        if not submit('\x00'): return
                        continue
                    if not submit(raw.rstrip('\r\n')): return
            except (OSError,ValueError,RuntimeError):
                submit(None)
        threading.Thread(target=reader,name='NXT-Local-Console',daemon=True).start()
        print('Local console ready. Type help. No commands are available through player chat or the network.',flush=True)
        try:
            while not self.service.stop.is_set():
                print('NXT> ',end='',flush=True)
                line=await queue.get()
                slots.release()
                if line is None:
                    print('\nConsole input ended; world remains online.',flush=True); return
                await self.execute(line,output=lambda text:print(text,flush=True))
        finally:
            stopped.set()
