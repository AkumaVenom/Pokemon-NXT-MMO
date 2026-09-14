"""Real loopback aiohttp/WebSocket local-admin integration; no browser bridge.

Runs actual network authentication/dispatch and the real console/store path.
No admin endpoint is registered or required. Each test owns disposable SQLite.
"""
from __future__ import annotations
import asyncio
import copy
import dataclasses
import json
import re
import unittest
from unittest import mock
import test_network as fixture

class AdminNetworkTests(unittest.IsolatedAsyncioTestCase):
    setUpClass=classmethod(fixture.NetworkTests.setUpClass.__func__)
    asyncSetUp=fixture.NetworkTests.asyncSetUp
    connect=fixture.NetworkTests.connect
    until=fixture.NetworkTests.until
    login=fixture.NetworkTests.login
    async def asyncTearDown(self):
        await self.service.console_commands.close()
        await fixture.NetworkTests.asyncTearDown(self)
        if self.service.admin_disconnect_tasks:await asyncio.gather(*self.service.admin_disconnect_tasks,return_exceptions=True)
    async def console(self,line,confirm=False,ok=True):
        cmd=self.service.console_commands
        result=await cmd.execute(line,output=lambda _:None)
        if confirm:
            token=re.search(r'enter: confirm ([a-f0-9]+)','\n'.join(result))
            self.assertIsNotNone(token,(line,result))
            result=await cmd.execute('confirm '+token[1],output=lambda _:None)
        text='\n'.join(result)
        self.assertEqual(text.startswith('ERROR:'),not ok,(line,result))
        return text
    async def signed_in(self,name='NetworkAlice'):
        ws=await self.login(name);await self.until(ws,'joined');state=await self.until(ws,'state')
        await self.until(ws,'chat_history');await self.until(ws,'chat_history')
        return ws,state
    async def wait_offline(self,uid):
        for _ in range(100):
            if uid not in self.service.world.players:return
            await asyncio.sleep(.02)
        self.fail('Expected session cleanup')
    async def test_forged_network_admin_packets_and_urls_cannot_execute(self):
        ws,initial=await self.signed_in()
        for path in ('/admin','/console','/commands','/rcon'):
            async with self.session.post(self.base+path,json={'command':'givemoney NetworkAlice 999999'}) as response:
                self.assertEqual(response.status,404)
            async with self.session.get(self.base+path) as response:self.assertEqual(response.status,404)
        packets=[{'op':'admin','command':'givemoney NetworkAlice 999999','role':'OWNER'},
                 {'op':'console','text':'shutdown','local':True},
                 {'op':'givemoney','target':1,'amount':999999},
                 {'op':'setrank','rank':'OWNER'},
                 {'op':'command','command':'confirm whatever'}]
        for packet in packets:
            await ws.send_json(packet);response=await self.until(ws,'error');self.assertIn('Unknown',response['message'])
        player=self.service.world.players[initial['ownerId']]
        self.assertEqual(player.state['money'],initial['money']);self.assertFalse(self.service.stop.is_set())
        with self.db.transaction() as cur:cur.execute('SELECT COUNT(*) FROM admin_audit');self.assertEqual(cur.fetchone()[0],0)
    async def test_chat_slash_text_remains_plain_text_not_console_input(self):
        a,initial=await self.signed_in();b,_=await self.signed_in('NetworkBobby')
        await a.send_json({'op':'chat','channel':'general','text':'/givemoney NetworkAlice 9999999'})
        packet=await self.until(b,'chat')
        self.assertEqual(packet['text'],'/givemoney NetworkAlice 9999999')
        self.assertEqual(self.service.world.players[initial['ownerId']].state['money'],initial['money'])
    async def test_local_grants_owner_only_and_survive_relogin(self):
        a,initial=await self.signed_in();b,peer=await self.signed_in('NetworkBobby')
        await self.console('givepokemon NetworkAlice Pikachu 23 ancient')
        state=await self.until(a,'state');mon=state['creatures'][-1]
        self.assertEqual(mon['species'],'fr_25');self.assertEqual(mon['variety'],'ancient');self.assertEqual(mon['level'],23)
        self.assertEqual(len(self.service.world.players[peer['ownerId']].state['creatures']),1)
        await self.console('setvariety NetworkAlice party:1 shadow',confirm=True)
        state=await self.until(a,'state');self.assertEqual(state['creatures'][0]['variety'],'shadow')
        await self.service.world.tick();scene=await self.until(b,'scene')
        entity=next(p for p in scene['players'] if p['id']==initial['ownerId'])
        self.assertEqual(entity['followerVariety'],'shadow')
        for private in ('creatures','items','ivs','password_hash','locked','frozen','trade_blocked'):self.assertNotIn(private,entity)
        await a.close();await self.wait_offline(initial['ownerId'])
        again,_=await self.signed_in()
        p=self.service.world.players[initial['ownerId']]
        self.assertEqual(p.state['creatures'][-1]['uid'],mon['uid']);self.assertEqual(p.state['creatures'][-1]['variety'],'ancient')
    async def test_audit_failure_produces_no_network_state_or_grant(self):
        a,initial=await self.signed_in();before=copy.deepcopy(self.service.world.players[initial['ownerId']].state)
        with mock.patch.object(self.db,'_admin_audit',side_effect=OSError('injected failure')):await self.console('givepokemon NetworkAlice Pikachu',ok=False)
        await a.send_json({'op':'ping','nonce':23})
        packet=await a.receive_json(timeout=5);self.assertEqual(packet['type'],'pong');self.assertEqual(packet['nonce'],23)
        self.assertEqual(self.db.load(initial['ownerId']),before)
    async def test_live_ban_disconnects_rejects_auth_then_unban_reopens(self):
        a,initial=await self.signed_in()
        await self.console('ban NetworkAlice 2h integration-test',confirm=True)
        # Read the close/notice so the WebSocket close handshake can finish.
        for _ in range(5):
            msg=await a.receive(timeout=5)
            if msg.type in (fixture.aiohttp.WSMsgType.CLOSE,fixture.aiohttp.WSMsgType.CLOSED):break
        await self.wait_offline(initial['ownerId'])
        denied=await self.login();error=await self.until(denied,'error');self.assertIn('banned',error['message'])
        await self.console('unban NetworkAlice',confirm=True)
        again,_=await self.signed_in();self.assertFalse(again.closed)
    async def test_password_reset_racing_verified_login_wins_admission(self):
        entered=asyncio.Event();release=asyncio.Event();original=self.service.hash
        async def delayed(password,encoded=None):
            result=await original(password,encoded)
            if encoded is not None:entered.set();await release.wait()
            return result
        with mock.patch.object(self.service,'hash',side_effect=delayed):
            ws=await self.login();await asyncio.wait_for(entered.wait(),5)
            result=await self.console('resetpassword NetworkAlice',confirm=True)
            new_password=re.search(r'not logged\): (\S+)',result)[1]
            release.set();error=await self.until(ws,'error');self.assertIn('changed during login',error['message'])
        self.assertFalse(self.service.world.players)
        again=await self.login(password=new_password);joined=await self.until(again,'joined');self.assertEqual(joined['username'],'NetworkAlice')
    async def test_lock_racing_verified_login_cannot_publish_session(self):
        entered=asyncio.Event();release=asyncio.Event();original=self.service.hash
        async def delayed(password,encoded=None):
            result=await original(password,encoded)
            if encoded is not None:entered.set();await release.wait()
            return result
        with mock.patch.object(self.service,'hash',side_effect=delayed):
            ws=await self.login();await asyncio.wait_for(entered.wait(),5)
            await self.console('lockaccount NetworkAlice investigation',confirm=True)
            release.set();error=await self.until(ws,'error');self.assertIn('locked',error['message'])
        self.assertFalse(self.service.world.players)
        await self.console('unlockaccount NetworkAlice',confirm=True)
        again,_=await self.signed_in();self.assertFalse(again.closed)
    async def test_online_freeze_rejects_motion_but_does_not_affect_peer(self):
        a,initial=await self.signed_in();b,other=await self.signed_in('NetworkBobby')
        await self.console('freeze NetworkAlice',confirm=True)
        await a.send_json({'op':'move','direction':'right','seq':1})
        move=await self.until(a,'move');self.assertFalse(move['accepted']);self.assertEqual(move['reason'],'frozen')
        await b.send_json({'op':'move','direction':'right','seq':1})
        move2=await self.until(b,'move');self.assertTrue(move2['accepted'])
        await a.send_json({'op':'encounter'});self.assertIn('frozen',(await self.until(a,'error'))['message'])
        await self.console('unfreeze NetworkAlice')
        await a.send_json({'op':'move','direction':'right','seq':2});self.assertTrue((await self.until(a,'move'))['accepted'])
    async def test_kick_preview_cannot_disconnect_replacement_session(self):
        a,initial=await self.signed_in();preview=await self.console('kick NetworkAlice test')
        token=re.search(r'enter: confirm ([a-f0-9]+)',preview)[1]
        await a.close();await self.wait_offline(initial['ownerId'])
        newer,_=await self.signed_in()
        await self.console('confirm '+token,ok=False)
        await newer.send_json({'op':'ping','nonce':77});self.assertEqual((await self.until(newer,'pong'))['nonce'],77)
    async def test_actual_test_duel_actions_leave_saved_party_untouched(self):
        self.service.console_commands.policy=dataclasses.replace(self.service.console_commands.policy,allow_developer_commands=True)
        a,initial=await self.signed_in();before=copy.deepcopy(self.service.world.players[initial['ownerId']].state)
        await self.console('testbattle NetworkAlice Pikachu 5 shiny')
        packet=await self.until(a,'battle');battle=packet['battle']
        live=self.service.world.battles[self.service.world.players[initial['ownerId']].battle]
        # A valid move is resolved through the real client dispatcher, not a mocked battle.
        await a.send_json({'op':'battle','id':live.id,'action':'attack','slot':0})
        response=await self.until(a,'battle');self.assertEqual(response['battle']['id'],live.id)
        await self.console('endbattle NetworkAlice')
        await self.until(a,'battle')
        self.assertEqual(self.service.world.players[initial['ownerId']].state,before);self.assertEqual(self.db.load(initial['ownerId']),before)

if __name__=='__main__':unittest.main()
