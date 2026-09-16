"""Route 36 Sudowoodo story gate: canonical encounter and owner-only persistence."""
import asyncio
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'Server'),str(ROOT/'Tests'),str(ROOT)]
import test_adventure as fixture
from nxt.content import Content
from nxt.security import RequestError
from nxt.story_events import mark_cleared
from nxt.world import World

EVENT='johto_sudowoodo';ROUTE='johto_2_23';NPC=3;SUDOWOODO='fr_185';BOTTLE='squirtbottle'


class Route36PublishedContentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.c=Content(ROOT/'Server/data/world.json')
 def test_canonical_crystal_event_is_bound_to_real_route_object(self):
  event=next(e for e in self.c.data['adventure']['storyEvents'] if e['id']==EVENT);m=self.c.maps[ROUTE];obj=next(o for o in m['objects'] if o['id']==NPC);sp=self.c.species[SUDOWOODO]
  self.assertEqual((event['map'],event['npc'],event['graphics']),(ROUTE,NPC,98));self.assertEqual((obj['x'],obj['y'],obj['storyEvent']),(24,11,EVENT));self.assertEqual(m['collision'][11*m['width']+24],0)
  self.assertEqual((event['species'],event['level'],event['moves']),(SUDOWOODO,20,[88,102,175,67]));self.assertEqual(sp['name'],'Sudowoodo');self.assertEqual(sp['types'],[5,5])
  self.assertEqual([self.c.moves[str(mid)]['name'] for mid in event['moves']],['Rock Throw','Mimic','Flail','Low Kick'])
 def test_whitney_plain_badge_and_unique_key_item_are_authored(self):
  gym=next(g for g in self.c.data['adventureRom']['gyms'] if g.get('source')=='johto' and g['order']==3);item=self.c.items[BOTTLE]
  self.assertEqual(gym['name'],'Whitney');self.assertEqual(self.c.data['adventure']['badgeNames']['johto_3'],'Plain Badge')
  self.assertTrue(item['keyItem']);self.assertFalse(item['buyable']);self.assertFalse(item['tradable']);self.assertEqual(item['price'],0)
 def test_client_map_keeps_story_binding(self):
  import json
  m=json.loads((ROOT/'Client/app/assets/world/maps/johto_2_23.json').read_text())
  self.assertEqual(next(o for o in m['objects'] if o['id']==NPC)['storyEvent'],EVENT)


class Route36RuntimeTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):cls.base=Content(ROOT/'Server/data/world.json')
 asyncSetUp=fixture.AdventureTests.asyncSetUp
 asyncTearDown=fixture.AdventureTests.asyncTearDown
 add=fixture.AdventureTests.add
 packets=fixture.AdventureTests.packets
 win=fixture.AdventureTests.win

 async def place(self,p,badge=True):
  state=copy.deepcopy(p.state);state.update(map=ROUTE,x=23,y=11,surf=False)
  if badge and 'johto_3' not in state['adventure']['badges']:state['adventure']['badges'].append('johto_3')
  await self.w.commit(p,state);self.packets(p);return next(o for o in self.c.maps[ROUTE]['objects'] if o['id']==NPC)

 async def start(self,p):
  await self.w.dispatch(p,{'op':'npc','npc':NPC,'map':ROUTE,'action':'squirtbottle'});return self.w.battles[p.battle]

 async def finish(self,p,*,winner=0,caught=False):
  battle=self.w.battles[p.battle];battle.resolve=lambda:None;battle.ended=True;battle.winner=winner;battle.experience_events=[]
  if caught:
   battle.caught=copy.deepcopy(battle.rosters[1][0]);battle.caught['originalTrainer']=p.username
  await self.w.resolve_battle(battle);return battle

 async def test_uncleared_object_is_solid_despite_zero_shared_collision_and_owner_clear_is_private(self):
  obj=await self.place(self.a);await self.place(self.b);m=self.c.maps[ROUTE];j=obj['y']*m['width']+obj['x'];self.assertEqual(m['collision'][j],0)
  self.assertFalse(self.w.walkable(m,obj['x'],obj['y'],state=self.a.state));self.assertFalse(self.w.walkable(m,obj['x'],obj['y'],state=self.b.state))
  state=copy.deepcopy(self.a.state);mark_cleared(state,EVENT);await self.w.commit(self.a,state)
  self.assertTrue(self.w.walkable(m,obj['x'],obj['y'],state=self.a.state));self.assertFalse(self.w.walkable(m,obj['x'],obj['y'],state=self.b.state));self.assertEqual(m['collision'][j],0);self.assertIn(obj,m['objects'])

 async def test_plain_badge_grants_and_persists_squirtbottle_once(self):
  # Fixture Johto gym 3 is npc 240; earlier badges are needed by normal challenge ordering.
  for npc in (238,239,240):await self.win(self.a,npc)
  saved=self.db.load(self.a.id);self.assertIn('johto_3',saved['adventure']['badges']);self.assertEqual(saved['items'][BOTTLE],1);self.assertNotIn(BOTTLE,self.b.state['items'])
  migrated=copy.deepcopy(saved);migrated['items'].pop(BOTTLE,None);self.w.validate_state(migrated);self.assertEqual(migrated['items'][BOTTLE],1)

 async def test_locked_menu_and_malicious_use_are_rejected_before_badge(self):
  obj=await self.place(self.a,badge=False);self.a.state['items'].pop(BOTTLE,None)
  await self.w.dispatch(self.a,{'op':'npc','npc':obj['id'],'map':ROUTE});dialog=next(p for p in self.packets(self.a) if p['type']=='dialog');self.assertIn('squirtbottle',dialog['disabledActions']);self.assertFalse(dialog['storyEvent']['badgeEarned'])
  with self.assertRaisesRegex(RequestError,'Whitney'):await self.w.dispatch(self.a,{'op':'npc','npc':obj['id'],'map':ROUTE,'action':'squirtbottle'})
  self.assertIsNone(self.a.battle);self.assertNotIn(EVENT,self.a.state['adventure']['storyEvents'])

 async def test_squirtbottle_starts_exact_level20_sudowoodo_without_consuming_item(self):
  await self.place(self.a);before=self.a.state['items'][BOTTLE];battle=await self.start(self.a);enemy=battle.rosters[1][0]
  self.assertEqual((enemy['species'],enemy['level'],enemy['variety']),(SUDOWOODO,20,'normal'));self.assertEqual([m['id'] for m in enemy['moves']],[88,102,175,67]);self.assertEqual(battle.kind,'wild');self.assertEqual(getattr(battle,'story_event',None),EVENT);self.assertEqual(self.a.state['items'][BOTTLE],before)

 async def test_defeat_or_capture_clears_only_that_character_and_persists(self):
  await self.place(self.a);await self.place(self.b);await self.start(self.a);await self.finish(self.a,winner=0,caught=False);self.assertIn(EVENT,self.a.state['adventure']['storyEvents']);self.assertNotIn(EVENT,self.b.state['adventure']['storyEvents']);self.assertEqual(self.a.state['items'][BOTTLE],1)
  self.assertIn(EVENT,self.db.load(self.a.id)['adventure']['storyEvents']);uid=self.a.id;await self.w.leave(self.a);again=await self.w.join(uid,'Akuma',None,asyncio.Queue(maxsize=2048));self.assertIn(EVENT,again.state['adventure']['storyEvents']);self.assertTrue(self.w.walkable(self.c.maps[ROUTE],24,11,state=again.state))
  await self.start(self.b);before=len(self.b.state['creatures']);await self.finish(self.b,winner=0,caught=True);self.assertIn(EVENT,self.b.state['adventure']['storyEvents']);self.assertEqual(len(self.b.state['creatures']),before+1);self.assertEqual(self.b.state['creatures'][-1]['species'],SUDOWOODO)

 async def test_run_and_loss_do_not_clear_story_gate(self):
  await self.place(self.a);await self.start(self.a);await self.finish(self.a,winner=None);self.assertNotIn(EVENT,self.a.state['adventure']['storyEvents'])
  await self.place(self.a);await self.start(self.a);await self.finish(self.a,winner=1);self.assertNotIn(EVENT,self.a.state['adventure']['storyEvents']);self.assertNotIn(EVENT,self.db.load(self.a.id)['adventure']['storyEvents'])

 async def test_battle_save_failure_cannot_publish_cleared_path(self):
  await self.place(self.a);await self.start(self.a);before=copy.deepcopy(self.a.state);battle=self.w.battles[self.a.battle];battle.resolve=lambda:None;battle.ended=True;battle.winner=0;battle.experience_events=[]
  with patch.object(self.db,'save_many',side_effect=OSError('disk unavailable')):await self.w.resolve_battle(battle)
  self.assertEqual(self.a.state,before);self.assertNotIn(EVENT,self.a.state['adventure']['storyEvents']);self.assertIsNone(self.a.battle)

 async def test_key_item_cannot_be_bought_or_traded_even_with_forged_packets(self):
  await self.place(self.a);self.s.config.set('world','allow_alpha_atlas','true')
  with self.assertRaisesRegex(RequestError,'not sold'):await self.w.dispatch(self.a,{'op':'buy','item':BOTTLE,'quantity':99})
  with self.assertRaisesRegex(RequestError,'cannot be traded'):self.w.check_offer(self.a,{'pokemon':[],'items':{BOTTLE:1},'money':0})
  self.assertEqual(self.a.state['items'][BOTTLE],1)

 async def test_stale_map_remote_and_post_clear_replays_are_rejected(self):
  await self.place(self.a)
  with self.assertRaisesRegex(RequestError,'another map'):await self.w.dispatch(self.a,{'op':'npc','npc':NPC,'map':'johto_2_22','action':'squirtbottle'})
  self.a.state['x']=20
  with self.assertRaisesRegex(RequestError,'closer'):await self.w.dispatch(self.a,{'op':'npc','npc':NPC,'map':ROUTE,'action':'squirtbottle'})
  self.a.state['x']=23;await self.start(self.a);await self.finish(self.a)
  with self.assertRaisesRegex(RequestError,'already clear'):await self.w.dispatch(self.a,{'op':'npc','npc':NPC,'map':ROUTE,'action':'squirtbottle'})

 async def test_invalid_story_flags_are_cleaned_by_migration(self):
  state=copy.deepcopy(self.a.state);state['adventure']['storyEvents']=[EVENT,'forged',EVENT];state['items'][BOTTLE]=99
  # Without Plain Badge a forged cleared flag cannot survive.
  self.w.validate_state(state);self.assertEqual(state['adventure']['storyEvents'],[]);self.assertEqual(state['items'].get(BOTTLE,0),1 if 'johto_3' in state['adventure']['badges'] else 0)


if __name__=='__main__':unittest.main()
