"""Regional tables, original slot boundaries, and durable owner-only HM Cut.

The gym fixture uses the production victory/save path, not client-supplied badges.
Every real tree/collision cell is also checked against the immutable full pack.
"""
import asyncio
import copy
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'Server'), str(ROOT / 'Tests'), str(ROOT)]
import test_adventure as fixture
from nxt.content import Content
from nxt.encounters import encounter_period, encounter_area, encounter_slots, select_encounter, validate_encounter_map
from nxt.field_moves import cut_allowed, tree_cleared, migrate_cuts, public_field_moves
from nxt.security import RequestError
from Tools.crystal_encounter_catalog import build
from Tools.publish_encounters import assemble


class EncounterContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = Content(ROOT / 'Server/data/world.json')
        cls.bindings = json.loads((ROOT / 'Server/data/encounter_bindings.json').read_text())
        cls.crystal = json.loads((ROOT / 'Server/data/encounters_crystal.json').read_text())

    def test_every_map_explicitly_bound_and_no_fallback(self):
        self.assertEqual(set(self.bindings['maps']), set(self.c.maps))
        self.assertEqual(len(self.c.maps), 959)
        for key, m in self.c.maps.items():
            with self.subTest(map=key):
                self.assertIn(m['encounterSource'], ('none', 'firered', 'crystal'))
                validate_encounter_map(m, self.c.species)
        self.assertEqual(sum(bool(m['encounters'] or any(z['encounters'] for z in m.get('encounterZones', []))) for m in self.c.maps.values()), 248)

    def test_crystal_catalog_rebuild_is_identical(self):
        self.assertEqual(build(self.c.species), self.crystal)

    def test_crystal_clock_all_hours_and_invalid_types(self):
        expected = ['night'] * 4 + ['morning'] * 6 + ['day'] * 8 + ['night'] * 6
        self.assertEqual([encounter_period(h) for h in range(24)], expected)
        for hour in (-1, 24, True, 5.0, '5'):
            with self.assertRaises(ValueError): encounter_period(hour)

    def test_crystal_slot_and_surf_level_probabilities(self):
        for table in self.crystal['tables'].values():
            for method, rows in table['encounters'].items():
                expected = [60, 30, 10] if method == 'water' else [30, 30, 20, 10, 5, 4, 1]
                self.assertEqual([r['weight'] for r in rows], expected)
                for row in rows:
                    if method == 'water':
                        self.assertEqual(row['max'], row['min'] + 4)
                        self.assertEqual(row['levelWeights'], [89, 76, 51, 26, 14])
                        self.assertEqual(sum(row['levelWeights']), 256)
                    else: self.assertEqual(row['min'], row['max'])

    def test_route_29_changes_by_time_and_has_no_foreign_fallback(self):
        m = self.c.maps['johto_3_46']
        x, y = next((i % m['width'], i // m['width']) for i, b in enumerate(m['behavior']) if b == 2 and m['collision'][i] == 0)
        s = {'x': x, 'y': y, 'surf': False}
        self.assertEqual([r['species'] for r in encounter_slots(m, s, hour=8)], ['fr_16', 'fr_161', 'fr_16', 'fr_161', 'fr_19', 'fr_187', 'fr_187'])
        self.assertEqual([r['species'] for r in encounter_slots(m, s, hour=22)], ['fr_163', 'fr_19', 'fr_163', 'fr_19', 'fr_19', 'fr_163', 'fr_163'])

    def test_late_locations_are_not_starter_pools(self):
        road = self.crystal['tables']['VICTORY_ROAD']['encounters']['land_day']
        self.assertEqual([(r['species'], r['min']) for r in road], [('fr_75',34),('fr_111',32),('fr_95',33),('fr_42',34),('fr_28',35),('fr_112',35),('fr_112',35)])
        silver = self.crystal['tables']['SILVER_CAVE_ROOM_3']['encounters']
        self.assertEqual(silver['land_day'][-1]['species'], 'fr_247')
        self.assertEqual(silver['land_day'][-1]['min'], 20)  # Original Crystal rare slot, not a guessed high level.
        self.assertNotIn('fr_161', [r['species'] for r in road])

    def test_firered_sexes_and_original_ordered_route_weights(self):
        route = self.c.maps['kanto_3_21']['encounters']['land']
        self.assertEqual([r['weight'] for r in route], [20,20,10,10,10,10,5,5,4,4,1,1])
        self.assertEqual([route[i]['species'] for i in (4,8,10)], ['fr_32','fr_32','fr_29'])
        route1 = self.c.maps['kanto_3_19']['encounters']['land']
        self.assertEqual({r['species'] for r in route1}, {'fr_16','fr_19'})
        self.assertTrue(all(2 <= r['min'] <= r['max'] <= 5 for r in route1))

    def test_restored_male_identity_and_both_evolutions(self):
        self.assertEqual(self.c.species['fr_32']['sourceId'], 32)
        self.assertEqual(self.c.species['fr_32']['name'], 'Nidoran♂')
        native = self.c.data['adventureRom']
        self.assertEqual(native['evolutions']['fr_29'][0]['target'], 'fr_30')
        self.assertEqual(native['evolutions']['fr_32'][0]['target'], 'fr_33')
        for trainer in native['trainers'].values():
            for mon in trainer['team']:
                if mon.get('sourceSpeciesId') == 32: self.assertEqual(mon['species'], 'fr_32')
        audio = json.loads((ROOT / 'Client/app/assets/audio/catalog.json').read_text())
        self.assertEqual(audio['cries']['fr_32'], 'kanto.cry.31')

    def test_surf_and_land_are_strictly_separate(self):
        m = {'id':'fixture','width':2,'height':1,'collision':[0,0],'behavior':[16,2],'warps':[],
             'encounters':{'land':[{'species':'fr_19','min':3,'max':3,'weight':100}]}}
        self.assertEqual(encounter_slots(m, {'x':0,'y':0,'surf':True}), [])
        self.assertEqual(encounter_slots(m, {'x':0,'y':0,'surf':False}), [])
        self.assertEqual(encounter_slots(m, {'x':1,'y':0,'surf':False})[0]['species'], 'fr_19')
        m['encounters']['water']=[{'species':'fr_72','min':20,'max':24,'weight':100}]
        self.assertEqual(encounter_slots(m, {'x':0,'y':0,'surf':True})[0]['species'], 'fr_72')
        m['collision'][0]=1
        self.assertEqual(encounter_slots(m, {'x':0,'y':0,'surf':True}), [])

    def test_empty_rooms_zones_warps_and_floor_policy(self):
        m = self.c.maps['johto_2_63']
        self.assertEqual(encounter_area(m, 5, 35)['encounters'], {})
        self.assertTrue(encounter_area(m, 5, 10)['encounters'])
        sprout = self.c.maps['johto_2_72']
        self.assertFalse(encounter_area(sprout, 60, 5)['encounters'])
        self.assertTrue(encounter_area(sprout, 10, 5)['encounters'])
        m = {'id':'floor','width':1,'height':1,'collision':[0],'behavior':[0],'warps':[],
             'encounterTerrain':'floor','encounters':{'land':[{'species':'fr_41','min':5,'max':5,'weight':100}]}}
        s = {'x':0,'y':0}
        self.assertTrue(encounter_slots(m,s))
        m['warps']=[{'x':0,'y':0}];self.assertFalse(encounter_slots(m,s))
        m['warps']=[];m['encounterTerrain']='tiles';self.assertFalse(encounter_slots(m,s))

    def test_picker_honors_slot_weights_and_original_level_model(self):
        class Recorder:
            calls=[]
            def choices(self, values, *, weights, k):
                self.calls.append(list(weights));return [list(values)[-1]]
            def randint(self, low, high): return high
        rows=self.crystal['tables']['DRAGONS_DEN_B1F']['encounters']['water']
        rng=Recorder();self.assertEqual(select_encounter(rows,rng),('fr_147',14))
        self.assertEqual(rng.calls,[[60,30,10],[89,76,51,26,14]])
        with self.assertRaises(ValueError):select_encounter([],random.Random(1))

    def test_bad_weights_species_and_overlapping_zones_rejected(self):
        m=copy.deepcopy(self.c.maps['kanto_3_19'])
        m['encounters']['land'][0]['weight']=0
        with self.assertRaises(ValueError):validate_encounter_map(m,self.c.species)
        m=copy.deepcopy(self.c.maps['kanto_3_19']);m['encounters']['land'][0]['species']='missing'
        with self.assertRaises(ValueError):validate_encounter_map(m,self.c.species)
        m['encounters']={};m['encounterZones']=[{'rect':[0,0,3,3]}, {'rect':[1,1,4,4]}]
        with self.assertRaisesRegex(ValueError,'Overlapping'):validate_encounter_map(m,self.c.species)

    def test_binding_fail_closed_and_republish_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'Server/data').mkdir(parents=True)
            for name in ('encounters_firered','encounters_crystal','encounter_bindings'):
                (root/'Server/data'/f'{name}.json').write_bytes((ROOT/'Server/data'/f'{name}.json').read_bytes())
            w=copy.deepcopy(self.c.data);assemble(w,root);before=copy.deepcopy(w);assemble(w,root);self.assertEqual(w,before)
            binding=json.loads((root/'Server/data/encounter_bindings.json').read_text());binding['maps'].pop('kanto_3_19');(root/'Server/data/encounter_bindings.json').write_text(json.dumps(binding))
            with self.assertRaisesRegex(ValueError,'cover every map'):assemble(w,root)


class CutRuntimeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls): cls.base=Content(ROOT/'Server/data/world.json')
    asyncSetUp=fixture.AdventureTests.asyncSetUp
    asyncTearDown=fixture.AdventureTests.asyncTearDown
    add=fixture.AdventureTests.add
    packets=fixture.AdventureTests.packets
    win=fixture.AdventureTests.win

    def plant(self, player=None, key=None, collision=0):
        player=player or self.a;key=key or self.map;m=self.c.maps[key]
        x,y=m['spawn'];obj={'id':219,'x':x+1,'y':y,'graphics':95,'trainerType':0}
        m['objects']=[o for o in m['objects'] if o['id']!=219]+[obj]
        m['collision'][y*m['width']+x+1]=collision;m['behavior'][y*m['width']+x+1]=0;m['elevation'][y*m['width']+x+1]=m['elevation'][y*m['width']+x]
        player.state.update(map=key,x=x,y=y)
        return m,obj

    async def cut(self,p,obj,key=None):
        await self.w.dispatch(p,{'op':'npc','npc':obj['id'],'map':key or p.state['map'],'action':'cut'})

    async def test_automatic_second_gym_unlock_both_start_regions_and_no_move_replacement(self):
        for p,home,npcs,region in [(self.a,'Kanto',(230,231),'kanto'),(self.b,'Johto',(238,239),'johto')]:
            p.state['home']=home;before=copy.deepcopy(p.state['creatures'][0]['moves'])
            await self.win(p,npcs[0]);self.assertFalse(cut_allowed(p.state,region))
            await self.win(p,npcs[1]);self.assertTrue(cut_allowed(p.state,region));self.assertFalse(cut_allowed(p.state,'johto' if region=='kanto' else 'kanto'))
            self.assertIn('cut_'+region,self.db.load(p.id)['adventure']['unlocks'])
            # Neither a fifth move nor HM overwrite is introduced by the licence.
            after=[m['id'] for m in p.state['creatures'][0]['moves']]
            self.assertEqual(after[:len(before)],[m['id'] for m in before])
            self.assertLessEqual(len(after),4);self.assertNotIn(15,after)  # Natural EXP learning is allowed; Cut is not inserted.

    async def test_legacy_badges_unlock_on_migration_not_home_or_badge_count(self):
        s=copy.deepcopy(self.a.state);s['adventure']['badges']=['johto_2'];s['adventure'].pop('cutTrees',None);s['home']='Kanto'
        migrated=self.w.adventure.migrate(s);self.assertTrue(cut_allowed(migrated,'johto'));self.assertFalse(cut_allowed(migrated,'kanto'))
        self.assertIn('cut_johto',migrated['adventure']['unlocks'])
        migrated['adventure']['badges']=['kanto_1','johto_1'];migrated['adventure']['unlocks']=['cut_kanto','cut_johto']
        self.assertFalse(cut_allowed(migrated,'kanto'));self.assertFalse(cut_allowed(migrated,'johto'))

    async def test_locked_menu_cannot_cut_or_mutate_storage(self):
        m,o=self.plant();self.packets(self.a);before=copy.deepcopy(self.a.state)
        await self.w.dispatch(self.a,{'op':'npc','npc':o['id'],'map':m['id']})
        menu=self.packets(self.a)[-1];self.assertEqual(menu['actions'],['cut']);self.assertEqual(menu['disabledActions'],['cut']);self.assertIn('Misty',menu['message'])
        with self.assertRaisesRegex(RequestError,'locked'):await self.cut(self.a,o)
        self.assertEqual(self.a.state,before)

    async def test_cut_is_saved_owner_only_idempotent_and_collision_is_not_global(self):
        m,o=self.plant(collision=1);self.a.state['adventure']['badges']=['kanto_1','kanto_2'];self.packets(self.a);self.packets(self.b)
        grid=copy.deepcopy(m['collision']);objects=copy.deepcopy(m['objects']);before_other=copy.deepcopy(self.b.state)
        self.assertFalse(self.w.walkable(m,o['x'],o['y'],state=self.a.state))
        await self.cut(self.a,o);self.assertTrue(self.w.walkable(m,o['x'],o['y'],state=self.a.state));self.assertFalse(self.w.walkable(m,o['x'],o['y'],state=self.b.state))
        self.assertEqual(m['collision'],grid);self.assertEqual(m['objects'],objects);self.assertEqual(self.b.state,before_other);self.assertFalse(self.packets(self.b))
        self.assertTrue(tree_cleared(self.db.load(self.a.id),m['id'],o))
        packets=self.packets(self.a);self.assertEqual([p['type'] for p in packets],['state','dialog'])
        self.assertEqual(packets[0]['ownerId'],self.a.id);self.assertEqual(packets[0]['adventure']['cutTrees'][m['id']],[o['id']])
        revision=self.a.state['revision'];await self.cut(self.a,o);self.assertEqual(self.a.state['revision'],revision)

    async def test_save_failure_leaves_tree_and_collision_intact_and_retry_works(self):
        m,o=self.plant();self.a.state['adventure']['badges']=['kanto_2'];before=copy.deepcopy(self.a.state);self.packets(self.a)
        with patch.object(self.db,'save_many',side_effect=OSError('injected failure')):
            with self.assertRaisesRegex(RequestError,'Nothing was changed'):await self.cut(self.a,o)
        self.assertEqual(self.a.state,before);self.assertFalse(self.packets(self.a));self.assertFalse(self.w.walkable(m,o['x'],o['y'],state=self.a.state))
        await self.cut(self.a,o);self.assertTrue(tree_cleared(self.a.state,m['id'],o))

    async def test_cut_reloads_for_same_account_and_not_a_different_account(self):
        m,o=self.plant();self.a.state['adventure']['badges']=['kanto_2'];await self.cut(self.a,o)
        uid=self.a.id;self.w.players.pop(uid);p=await self.w.join(uid,'Akuma',None,asyncio.Queue(maxsize=2048))
        self.assertTrue(tree_cleared(p.state,m['id'],o));self.assertFalse(tree_cleared(self.b.state,m['id'],o))
        s=self.w.relocation_state(p,self.c.data['homes']['Johto']);s=self.w.relocation_state(type('P',(),{'state':s})(),m['id'])
        self.assertTrue(tree_cleared(s,m['id'],o))

    async def test_cut_rejects_stale_missing_map_far_away_busy_and_other_objects(self):
        m,o=self.plant();self.a.state['adventure']['badges']=['kanto_2']
        for mapid in ('johto_3_0',None):
            with self.assertRaises(RequestError):await self.cut(self.a,o,key=mapid if mapid else 'missing')
        with self.assertRaises(RequestError):await self.w.dispatch(self.a,{'op':'npc','npc':o['id'],'action':'cut'})
        self.a.state['x']-=5
        with self.assertRaisesRegex(RequestError,'closer'):await self.cut(self.a,o)
        self.a.state['x']+=5;self.a.trade='fixture'
        with self.assertRaisesRegex(RequestError,'Finish'):await self.cut(self.a,o)
        self.a.trade=None
        for graphics in (96,97,19):
            o['graphics']=graphics
            with self.assertRaises(RequestError):await self.cut(self.a,o)
        self.assertFalse(self.a.state['adventure']['cutTrees'])

    async def test_each_actual_hm_tree_has_owner_only_collision_override(self):
        count=0
        for m in self.base.maps.values():
            for obj in m['objects']:
                if obj['graphics']!=95:continue
                count+=1
                with self.subTest(map=m['id'],npc=obj['id']):
                    state={'adventure':{'cutTrees':{m['id']:[obj['id']]}}}
                    self.assertFalse(self.w.walkable(m,obj['x'],obj['y']))
                    self.assertTrue(self.w.walkable(m,obj['x'],obj['y'],state=state))
                    for other in m['objects']:
                        if other['id']!=obj['id'] and other['graphics'] in (95,96,97):self.assertFalse(self.w.walkable(m,other['x'],other['y'],state=state))
        self.assertEqual(count,120)

    async def test_invalid_flags_cannot_remove_a_rock_wall_or_tree_in_another_map(self):
        m,o=self.plant();m['objects'].append({'id':218,'x':o['x']+1,'y':o['y'],'graphics':96})
        s=copy.deepcopy(self.a.state);s['adventure']['cutTrees']={m['id']:[o['id'],o['id'],218,999,True,'219'],'missing':[219]}
        migrate_cuts(s,self.c.maps);self.assertEqual(s['adventure']['cutTrees'],{m['id']:[219]})
        wallx=o['x']-1;wally=o['y']-1;m['collision'][wally*m['width']+wallx]=1
        self.assertFalse(self.w.walkable(m,wallx,wally,state=s));self.assertFalse(self.w.walkable(m,o['x']+1,o['y'],state=s))

    async def test_gym_save_failure_or_loss_cannot_unlock_cut(self):
        await self.win(self.a,230)
        await self.w.dispatch(self.a,{'op':'npc','npc':231,'action':'battle'});b=self.w.battles[self.a.battle];b.resolve=lambda:None;b.ended=True;b.winner=0;b.experience_events=[]
        with patch.object(self.db,'save_many',side_effect=OSError('injected badge failure')):await self.w.resolve_battle(b)
        self.assertFalse(cut_allowed(self.a.state,'kanto'));self.assertFalse(cut_allowed(self.db.load(self.a.id),'kanto'))
        await self.w.dispatch(self.a,{'op':'npc','npc':231,'action':'battle'});b=self.w.battles[self.a.battle];b.resolve=lambda:None;b.ended=True;b.winner=1;b.experience_events=[];await self.w.resolve_battle(b)
        self.assertFalse(cut_allowed(self.a.state,'kanto'))

    async def test_live_wild_battle_uses_current_map_and_level_not_client_species(self):
        m=self.c.maps['johto_2_70'];x,y=next((i%m['width'],i//m['width']) for i in range(len(m['collision'])) if encounter_slots(m,{'x':i%m['width'],'y':i//m['width']},hour=12))
        self.a.state.update(map=m['id'],x=x,y=y,surf=False)
        with patch('nxt.encounters.encounter_period',return_value='day'):
            await self.w.dispatch(self.a,{'op':'encounter','species':'fr_161','level':1})
        battle=self.w.battles[self.a.battle];enemy=battle.rosters[1][0]
        self.assertIn((enemy['species'],enemy['level']),{(r['species'],r['min']) for r in m['encounters']['land_day']})

if __name__=='__main__':unittest.main()
