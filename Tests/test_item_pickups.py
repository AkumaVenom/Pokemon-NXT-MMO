"""Server-authoritative Johto / Sigma field-item pickup regression tests."""
import asyncio,copy,dataclasses,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'))
from nxt.content import Content
from nxt.config import Settings
from nxt.security import RequestError
from nxt.store import Store
from nxt.world import World

class FieldItemPickupTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):
  cls.content_path=ROOT/'Server/data/world.json'

 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();config=Path(self.temp.name)/'config.ini';config.write_text((ROOT/'Build/config_templates/Server/config.ini').read_text())
  settings=Settings.load(config);settings.config.set('database','backend','sqlite');self.s=dataclasses.replace(settings,encounter_chance=0)
  self.c=Content(self.content_path);self.db=Store(self.s);self.db.acquire_lease();self.w=World(self.c,self.db,self.s)
  self.pickup=next(p for p in self.c.data['adventureRom']['itemPickups'].values() if p['quantity']==16)
  self.a=await self.add('Akuma','fr_152');self.b=await self.add('Spider','fr_4')

 async def asyncTearDown(self):
  self.w.players.clear();self.db.close();self.temp.cleanup()

 async def add(self,name,starter):
  state=self.w.initial(name,'Kanto',starter,0);uid=self.db.create(name,'unused',state);return await self.w.join(uid,name,state,asyncio.Queue(maxsize=2048))

 async def place(self,p):
  state=copy.deepcopy(p.state);state['map']=self.pickup['map'];state['x']=self.pickup['x'];state['y']=self.pickup['y'];await self.w.commit(p,state)

 async def test_pickup_awards_exact_rom_quantity_once_and_persists_privately(self):
  await self.place(self.a);before=self.a.state['items'].get(self.pickup['item'],0);other_before=copy.deepcopy(self.b.state)
  await self.w.dispatch(self.a,{'op':'npc','npc':self.pickup['npc'],'map':self.pickup['map']})
  saved=self.db.load(self.a.id);self.assertEqual(saved['items'][self.pickup['item']],before+16);self.assertIn(self.pickup['id'],saved['adventure']['itemPickups'])
  self.assertIn(self.pickup['id'],self.w.adventure.public(self.a.state)['itemPickups']);self.assertNotIn(self.pickup['id'],self.w.adventure.public(self.b.state)['itemPickups']);self.assertEqual(self.b.state,other_before)
  with self.assertRaisesRegex(RequestError,'already collected'):
   await self.w.dispatch(self.a,{'op':'npc','npc':self.pickup['npc'],'map':self.pickup['map']})
  self.assertEqual(self.db.load(self.a.id),saved)

 async def test_pickup_requires_correct_map_and_proximity(self):
  with self.assertRaisesRegex(RequestError,'not available|another map'):
   await self.w.dispatch(self.a,{'op':'npc','npc':self.pickup['npc'],'map':self.pickup['map']})
  await self.place(self.a);self.a.state['x']=min(self.c.maps[self.pickup['map']]['width']-1,self.pickup['x']+5)
  if abs(self.a.state['x']-self.pickup['x'])<=2:self.a.state['y']=min(self.c.maps[self.pickup['map']]['height']-1,self.pickup['y']+5)
  with self.assertRaisesRegex(RequestError,'closer'):
   await self.w.dispatch(self.a,{'op':'npc','npc':self.pickup['npc'],'map':self.pickup['map']})

 async def test_pickup_save_failure_is_atomic_and_does_not_mark_collected(self):
  await self.place(self.a);before=copy.deepcopy(self.a.state);saved=copy.deepcopy(self.db.load(self.a.id))
  with patch.object(self.db,'save_many',side_effect=OSError('storage unavailable')):
   with self.assertLogs('nxt.world',level='ERROR'):
    with self.assertRaisesRegex(RequestError,'database'):
     await self.w.dispatch(self.a,{'op':'npc','npc':self.pickup['npc'],'map':self.pickup['map']})
  self.assertEqual(self.a.state,before);self.assertEqual(self.db.load(self.a.id),saved);self.assertNotIn(self.pickup['id'],self.a.state['adventure']['itemPickups'])

 async def test_full_stack_leaves_ball_uncollected(self):
  await self.place(self.a);state=copy.deepcopy(self.a.state);state['items'][self.pickup['item']]=999;await self.w.commit(self.a,state);before=copy.deepcopy(self.a.state)
  with self.assertRaisesRegex(RequestError,'Make room'):
   await self.w.dispatch(self.a,{'op':'npc','npc':self.pickup['npc'],'map':self.pickup['map']})
  self.assertEqual(self.a.state,before);self.assertNotIn(self.pickup['id'],self.a.state['adventure']['itemPickups'])

if __name__=='__main__':unittest.main()
