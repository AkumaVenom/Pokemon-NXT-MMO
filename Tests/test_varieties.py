"""Cosmetic variety contracts: real data, deterministic ticket audit and durable ownership.

No remote assets, ROM, operator database, Pillow or browser is required. Database
failure injection must keep the last committed owner state and never publish a catch.
"""
from __future__ import annotations
import asyncio, collections, copy, hashlib, json, random, shutil, sys, tempfile, unittest
from contextlib import contextmanager
from typing import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'Server'),str(ROOT)]
from nxt.content import Content
from nxt.varieties import VARIETIES, Varieties, validate_policy, variety_key
from nxt.growth import Growth
from nxt.combat import Battle
from nxt.world import World
from nxt.security import RequestError
from Tools.publish_varieties import assemble
import test_adventure as fixture

@contextmanager
def publisher_fixture(manifest: dict) -> Iterator[Path]:
    """Make a disposable, link-free input tree for the real variety publisher.

    The publisher reads the 3,697 variety fronts, not maps/audio/native fronts.
    Copy only that small tree. Real copies need no Windows symlink privilege,
    work across volumes, and let corruption tests modify a sprite without ever
    changing the shipped source (a hard link would not provide that isolation).
    The production publisher and all checksum/path checks remain unmodified.
    """
    with tempfile.TemporaryDirectory(prefix="nxt-variety-publisher-") as tmp:
        root = Path(tmp)
        (root / "Server/data").mkdir(parents=True)
        (root / "Docs").mkdir()
        shutil.copytree(
            ROOT / "Client/app/assets/pokemon/varieties",
            root / "Client/app/assets/pokemon/varieties",
            copy_function=shutil.copyfile,
        )
        (root / "Server/data/varieties.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        yield root


class TicketRng:
 def __init__(self): self.value=0; self.calls=[]
 def randrange(self,denominator): self.calls.append(denominator); return self.value

class VarietyDataTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.c=Content(ROOT/'Server/data/world.json')
  cls.manifest=json.loads((ROOT/'Server/data/varieties.json').read_text())
 def test_all_251_core_identities_have_all_five_fronts_and_normal(self):
  for index in range(1,252):
   key=f'fr_{index}'
   self.assertEqual(set(self.c.species[key]['varieties']),set(VARIETIES))
   for v in VARIETIES[1:]: self.assertIn(v,self.manifest['species'][key])
 def test_every_imported_front_is_checksum_verified_and_bound_to_correct_id(self):
  count=0
  for species,rows in self.manifest['species'].items():
   for variety,row in rows.items():
    self.assertEqual(row['front'],f'pokemon/varieties/{variety}/{species}.png')
    data=(ROOT/'Client/app/assets'/row['front']).read_bytes()
    self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
    self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n');count+=1
  self.assertEqual(count,3697);self.assertEqual(self.manifest['importProblems'],[])
 def test_normal_fronts_and_follower_icons_are_not_replaced_by_variants(self):
  for key,sp in self.c.species.items():
   self.assertEqual(sp['varieties']['normal']['front'],sp['front'])
   self.assertNotIn('/varieties/',sp['icon'])
   for v,row in sp['varieties'].items():
    self.assertNotIn('back',row['front'].lower())
    self.assertTrue((ROOT/'Client/app/assets'/row['front']).is_file())
 def test_server_and_client_share_exact_policy_species_bindings_and_pack(self):
  client=json.loads((ROOT/'Client/app/assets/world/client.json').read_text())
  self.assertEqual(client['varietyPolicy'],self.c.data['varietyPolicy'])
  self.assertEqual(client['pack'],self.c.pack)
  for key in self.c.species:self.assertEqual(client['species'][key]['varieties'],self.c.species[key]['varieties'])
 def test_exact_exhaustive_tickets_no_extra_roll_or_reweight(self):
  rng=TicketRng();v=Varieties(SimpleNamespace(data=self.c.data,species=self.c.species,rng=rng));counts=collections.Counter()
  for i in range(10000):rng.value=i;counts[v.roll('fr_25')]+=1
  self.assertEqual(dict(counts),dict(zip(VARIETIES,(9000,250,250,125,250,125))))
  self.assertEqual(rng.calls,[10000]*10000)
 def test_missing_extra_form_art_tickets_become_normal_without_reroll(self):
  key=next(k for k,s in self.c.species.items() if 'ancient' not in s['varieties'])
  rng=TicketRng();v=Varieties(SimpleNamespace(data=self.c.data,species=self.c.species,rng=rng));rng.value=9100
  self.assertEqual(v.roll(key),'normal');self.assertEqual(rng.calls,[10000])
  rng.value=9510;self.assertEqual(v.roll(key),'shiny')
 def test_catalog_counts_are_audited_not_assumed_for_sigma_extras(self):
  policy=self.c.data['varietyPolicy'];self.assertEqual(policy['coverage']['uploadedFronts'],3697)
  self.assertEqual(policy['coverage']['kantoJohtoSpecies'],251)
  self.assertEqual(policy['coverage']['species'],877)
  self.assertLess(policy['coverage']['fullyCoveredSpecies'],877)
  self.assertEqual(policy['coverage']['availableCounts']['shiny'],877)
 def test_invalid_policy_weights_order_colours_and_denominator_fail_closed(self):
  transforms=[lambda p:p.update(rollDenominator=0),lambda p:p.update(rollDenominator=True),lambda p:p['order'].reverse(),lambda p:p['definitions']['shiny'].update(weight=True),lambda p:p['definitions']['shiny'].update(weight=-1),lambda p:p['definitions']['shiny'].update(weight=100),lambda p:p['definitions']['shadow'].update(color='red;display:none')]
  for change in transforms:
   p=copy.deepcopy(self.c.data['varietyPolicy']);change(p)
   with self.subTest(policy=p),self.assertRaises(ValueError):validate_policy(p)
 def test_publisher_is_idempotent_and_preserves_species_combat_facts(self):
  with publisher_fixture(self.manifest) as root:
   world={'species':copy.deepcopy(self.c.species)};first=assemble(world,root);snapshot=copy.deepcopy(world)
   self.assertEqual(assemble(world,root),first);self.assertEqual(world,snapshot)
   for key in world['species']:
    for field in ('baseStats','catchRate','learnset','growth','icon','front','shiny'):
     self.assertEqual(world['species'][key][field],self.c.species[key][field])
 def test_publisher_rejects_cross_species_path_and_checksum_corruption(self):
  cases=[('front','../steal.png','Unsafe or cross-species'),
         ('front','pokemon/varieties/shiny/fr_25.png','Unsafe or cross-species'),
         ('sha256','0'*64,'checksum mismatch')]
  for field,value,message in cases:
   with self.subTest(field=field,value=value):
    manifest=copy.deepcopy(self.manifest);manifest['species']['fr_1']['ancient'][field]=value
    with publisher_fixture(manifest) as root:
     with self.assertRaisesRegex(ValueError,message):
      assemble({'species':copy.deepcopy(self.c.species)},root)
 def test_publisher_checks_do_not_require_symlink_or_hardlink_privileges(self):
  # Reproduce an ordinary Windows session even when this suite runs on Linux.
  error=PermissionError(1314,'A required privilege is not held by the client')
  error.winerror=1314
  with patch('os.symlink',side_effect=error) as symlink,patch('os.link',side_effect=error) as hardlink:
   self.test_publisher_is_idempotent_and_preserves_species_combat_facts()
   self.test_publisher_rejects_cross_species_path_and_checksum_corruption()
  symlink.assert_not_called();hardlink.assert_not_called()
 def test_publisher_fixture_is_private_complete_and_cleans_after_failure(self):
  record=self.manifest['species']['fr_1']['ancient'];relative=record['front']
  original=ROOT/'Client/app/assets'/relative;before=original.read_bytes()
  with publisher_fixture(self.manifest) as root:
   assets=root/'Client/app/assets'
   expected={row['front'] for rows in self.manifest['species'].values() for row in rows.values()}
   actual={p.relative_to(assets).as_posix() for p in assets.rglob('*') if p.is_file()}
   self.assertEqual(actual,expected);self.assertEqual(len(actual),3697)
   self.assertFalse(any(p.is_symlink() for p in root.rglob('*')))
   duplicate=assets/relative;self.assertFalse(duplicate.samefile(original))
   self.assertEqual(duplicate.read_bytes(),before)
   duplicate.write_bytes(before+b'fixture-only corruption')
   with self.assertRaisesRegex(ValueError,'checksum mismatch'):
    assemble({'species':copy.deepcopy(self.c.species)},root)
   self.assertEqual(original.read_bytes(),before)
   self.assertFalse((root/'Docs/POKEMON_VARIETY_ASSET_AUDIT.json').exists())
  self.assertFalse(root.exists());self.assertEqual(original.read_bytes(),before)
 def test_publisher_rejects_missing_copied_front(self):
  relative=self.manifest['species']['fr_1']['ancient']['front']
  with publisher_fixture(self.manifest) as root:
   (root/'Client/app/assets'/relative).unlink()
   with self.assertRaisesRegex(ValueError,'Missing or unsafe variety image'):
    assemble({'species':copy.deepcopy(self.c.species)},root)
  self.assertTrue((ROOT/'Client/app/assets'/relative).is_file())
 def test_modern_identity_wins_over_conflicting_legacy_boolean(self):
  for v in VARIETIES:
   mon={'variety':v,'shiny':v!='shiny'};self.assertEqual(variety_key(mon),v)
   self.c.varieties.normalize_mon(mon);self.assertEqual(mon['shiny'],v=='shiny')
 def test_legacy_migration_is_additive_idempotent_and_preserves_damage_moves(self):
  mons=[self.c.new_mon('fr_1',16,'Original') for _ in range(2)]
  for mon in mons:mon.pop('variety');mon['hp']=1;mon['moves'][0]['pp']=0
  mons[0]['shiny']=True;state={'creatures':mons,'adventure':{'badges':['kanto_2'],'cutTrees':{'kanto_3_0':[1]}}};old=copy.deepcopy(state)
  changed=self.c.varieties.migrate(state);self.assertEqual(state,old)
  self.assertEqual([m['variety'] for m in changed['creatures']],['shiny','normal'])
  for before,after in zip(old['creatures'],changed['creatures']):
   self.assertEqual({k:after[k] for k in before},before)
  self.assertEqual(self.c.varieties.migrate(changed),changed)
  self.assertEqual(changed['adventure']['badges'],old['adventure']['badges']);self.assertEqual(changed['adventure']['cutTrees'],old['adventure']['cutTrees'])
 def test_unknown_saved_variety_is_not_silently_destroyed(self):
  for value in ('dark','future',[],{},None,True):
   mon=self.c.new_mon('fr_1',5);mon['variety']=value
   with self.assertRaises(RequestError):self.c.varieties.migrate({'creatures':[mon]})
 def test_variety_dex_filters_invalid_rows_and_caught_implies_seen(self):
  mon=self.c.new_mon('fr_1',5);state={'creatures':[mon],'adventure':{'varietyDex':{'seen':{'fr_4':['mystic','bad'], 'missing':['shiny']},'caught':{'fr_25':['shadow','shadow']}}}}
  dex=self.c.varieties.migrate(state)['adventure']['varietyDex']
  self.assertEqual(dex['caught']['fr_25'],['shadow']);self.assertEqual(dex['seen']['fr_25'],['shadow']);self.assertEqual(dex['seen']['fr_4'],['mystic']);self.assertNotIn('missing',dex['seen'])
 def test_cosmetic_variants_leave_identical_stats_moves_and_capture_data(self):
  original=self.c.new_mon('fr_25',37);stats=self.c.stats(original)
  for value in VARIETIES:
   mon=copy.deepcopy(original);mon.update(variety=value,shiny=value=='shiny');public=self.c.public_mon(mon)
   self.assertEqual(self.c.stats(mon),stats);self.assertEqual(public['moves'],original['moves']);self.assertEqual(public['variety'],value)
   self.assertEqual(public['displayName'],'Pikachu' if value=='normal' else value.title()+' Pikachu')
 def test_level_stone_and_trade_evolution_keep_each_cosmetic_identity(self):
  for source,target,level,method in [('fr_1','fr_2',16,'level'),('fr_25','fr_26',20,'stone'),('fr_64','fr_65',25,'trade')]:
   for value in VARIETIES:
    with self.subTest(source=source,variety=value):
     c=copy.copy(self.c);c.data=dict(c.data);c.data['adventureRom']={'evolutions':{source:[{'method':method,'target':target,'level':level,'item':'thunderstone'}]}};c.growth=Growth(c)
     mon=c.new_mon(source,level,'Owner',variety=value);mon['hp']=1
     if method=='trade':c.growth.mark_trade(mon)
     state={'creatures':[mon],'items':{'thunderstone':1}};old=copy.deepcopy(mon);out=c.growth.evolve(state,mon['uid'],target)['creatures'][0]
     self.assertEqual(mon,old)
     for field in ('uid','variety','shiny','ivs','nature','originalTrainer','level','exp'):self.assertEqual(out[field],old[field])
     self.assertTrue(c.varieties.supported(target,value));self.assertEqual(out['species'],target)
 def test_inherited_identity_without_extra_form_art_is_retained_and_flagged(self):
  key=next(k for k,s in self.c.species.items() if 'ancient' not in s['varieties'])
  mon=self.c.new_mon(key,5);mon['variety']='ancient';self.c.varieties.normalize_mon(mon)
  self.assertFalse(self.c.public_mon(mon)['varietyArtAvailable']);self.assertEqual(self.c.public_mon(mon)['variety'],'ancient')
 def test_non_wild_factories_are_normal_even_for_username_wild(self):
  with patch.object(self.c.varieties,'roll',side_effect=AssertionError('must not roll')):
   for name in ('Wild','Trainer','Akuma'):
    self.assertEqual(self.c.new_mon('fr_1',5,name)['variety'],'normal')

class VarietyWorldTests(unittest.IsolatedAsyncioTestCase):
 @classmethod
 def setUpClass(cls):cls.base=Content(ROOT/'Server/data/world.json')
 asyncSetUp=fixture.AdventureTests.asyncSetUp
 asyncTearDown=fixture.AdventureTests.asyncTearDown
 add=fixture.AdventureTests.add
 packets=fixture.AdventureTests.packets
 async def test_real_wild_capture_preserves_all_six_varieties_uid_and_private_dex(self):
  self.packets(self.b)
  for value in VARIETIES:
   with patch.object(self.c.varieties,'roll',return_value=value):await self.w.start_wild(self.a,('fr_19',5))
   battle=self.w.battles[self.a.battle];original=copy.deepcopy(battle.mon(1));self.assertEqual(original['variety'],value)
   with patch.object(self.c.rng,'random',return_value=0.0),patch.object(self.c.rng,'randrange',return_value=0):
    await self.w.battle_action(self.a,{'id':battle.id,'action':'capture','item':'pokeball','variety':'shadow','species':'fr_150'})
   self.assertTrue(battle.caught)
   saved=self.db.load(self.a.id);owned=next(m for m in saved['creatures'] if m['uid']==original['uid'])
   self.assertEqual(owned['species'],'fr_19');self.assertEqual(owned['variety'],value);self.assertEqual(owned['ivs'],original['ivs']);self.assertEqual(owned['originalTrainer'],'Akuma')
   self.assertIn(value,saved['adventure']['varietyDex']['caught']['fr_19'])
  self.assertNotIn('fr_19',self.b.state['adventure']['varietyDex']['caught']);self.assertFalse(any(p['type']=='state' for p in self.packets(self.b)))
 async def test_save_failure_cannot_publish_variant_catch_or_spend_ball(self):
  with patch.object(self.c.varieties,'roll',return_value='shadow'):await self.w.start_wild(self.a,('fr_19',5))
  battle=self.w.battles[self.a.battle];before=copy.deepcopy(self.a.state);self.packets(self.a)
  with patch.object(self.c.rng,'random',return_value=0.0),patch.object(self.c.rng,'randrange',return_value=0),patch.object(self.db,'save_many',side_effect=OSError('fixture disk failure')):
   await self.w.battle_action(self.a,{'id':battle.id,'action':'capture','item':'pokeball'})
  self.assertEqual(self.db.load(self.a.id),before);self.assertEqual(self.a.state,before);self.assertIsNone(battle.caught)
  packets=self.packets(self.a);self.assertFalse(any(e.get('cue')=='capture_success' for p in packets for e in p.get('battle',{}).get('audio',{}).get('events',[])))
 async def test_failed_encounter_save_has_no_battle_no_seen_leak(self):
  before=copy.deepcopy(self.a.state);self.packets(self.a)
  with patch.object(self.db,'save_many',side_effect=OSError('fixture disk failure')):
   with self.assertRaises(RequestError):await self.w.start_wild(self.a,('fr_19',5))
  self.assertIsNone(self.a.battle);self.assertEqual(self.a.state,before);self.assertEqual(self.packets(self.a),[])
 async def test_untrusted_encounter_packet_cannot_choose_species_level_or_variety(self):
  with patch('nxt.world.encounter_slots',return_value=[{'species':'fr_19','minLevel':5,'maxLevel':5,'weight':100}]),patch('nxt.world.select_encounter',return_value=('fr_19',5)),patch.object(self.c.varieties,'roll',return_value='metallic') as roll:
   # The fixture map is a registered Center: explicit wild permission is staged only here.
   with patch.object(self.w.adventure,'wild_allowed',return_value=True):await self.w.dispatch(self.a,{'op':'encounter','species':'fr_150','level':100,'variety':'shadow','shiny':True})
  enemy=self.w.battles[self.a.battle].mon(1);self.assertEqual((enemy['species'],enemy['level'],enemy['variety']),('fr_19',5,'metallic'));roll.assert_called_once_with('fr_19')
 async def test_legacy_shiny_login_is_durably_migrated_without_resetting_cut_badges(self):
  state=copy.deepcopy(self.a.state);mon=state['creatures'][0];mon.pop('variety');mon['shiny']=True;mon['hp']=1;mon['moves'][0]['pp']=0;state['adventure'].pop('varietyDex',None);state['adventure']['badges']=['kanto_1','kanto_2']
  self.db.save_many([(self.a.id,state)]);world=World(self.c,self.db,self.s);p=await world.join(self.a.id,'Akuma',None,asyncio.Queue());saved=self.db.load(p.id)
  self.assertEqual(saved,p.state);self.assertEqual(saved['creatures'][0]['variety'],'shiny');self.assertEqual(saved['creatures'][0]['hp'],1);self.assertEqual(saved['creatures'][0]['moves'],mon['moves']);self.assertIn('cut_kanto',saved['adventure']['unlocks'])
  await world.leave(p);p=await world.join(self.a.id,'Akuma',None,asyncio.Queue());self.assertEqual(p.state['revision'],saved['revision'])
 async def test_failed_variety_login_migration_publishes_no_partial_session(self):
  state=copy.deepcopy(self.a.state);state['creatures'][0].pop('variety');self.db.save_many([(self.a.id,state)]);world=World(self.c,self.db,self.s);q=asyncio.Queue()
  with patch.object(self.db,'save_many',side_effect=OSError('fixture disk failure')):
   with self.assertRaises(RequestError):await world.join(self.a.id,'Akuma',None,q)
  self.assertEqual(self.db.load(self.a.id),state);self.assertTrue(q.empty());self.assertNotIn(self.a.id,world.players)
 async def test_all_varieties_survive_pc_storage_and_world_relogin(self):
  state=copy.deepcopy(self.a.state)
  for value in VARIETIES[1:]:state['creatures'].append(self.c.new_mon('fr_25',5,'Akuma',variety=value))
  await self.w.commit(self.a,state)
  for mon in state['creatures'][1:]:
   await self.w.dispatch(self.a,{'op':'pc','action':'withdraw','uid':mon['uid']});await self.w.dispatch(self.a,{'op':'pc','action':'deposit','uid':mon['uid']})
  expected=copy.deepcopy(self.a.state);world=World(self.c,self.db,self.s);p=await world.join(self.a.id,'Akuma',None,asyncio.Queue());self.assertEqual(p.state,expected)
 async def test_atomic_trade_preserves_variety_uid_and_ownership_history(self):
  sa=copy.deepcopy(self.a.state);sb=copy.deepcopy(self.b.state)
  for value in VARIETIES[1:]:sa['creatures'].append(self.c.new_mon('fr_25',5,'Akuma',variety=value))
  await self.w.commit(self.a,sa);original=copy.deepcopy(sa['creatures'][1:]);ids=[m['uid'] for m in original]
  trade={'id':'variety-atomic','players':[self.a.id,self.b.id],'offers':{self.a.id:{'pokemon':ids,'items':{},'money':0},self.b.id:{'pokemon':[],'items':{},'money':0}}}
  await self.w.commit_trade(trade)
  self.assertFalse(set(ids)&{m['uid'] for m in self.db.load(self.a.id)['creatures']})
  acquired=[m for m in self.db.load(self.b.id)['creatures'] if m['uid'] in ids];self.assertEqual(acquired,original)
  self.assertEqual(self.b.state['adventure']['varietyDex']['caught']['fr_25'],list(VARIETIES[1:]));self.assertEqual(self.a.state['adventure']['varietyDex']['caught']['fr_25'],list(VARIETIES[1:]))
 async def test_trade_failure_leaves_both_variety_collections_unchanged(self):
  sa=copy.deepcopy(self.a.state);mon=self.c.new_mon('fr_25',5,'Akuma',variety='mystic');sa['creatures'].append(mon);await self.w.commit(self.a,sa);before=[copy.deepcopy(p.state) for p in (self.a,self.b)]
  t={'id':'failed-variety-trade','players':[self.a.id,self.b.id],'offers':{self.a.id:{'pokemon':[mon['uid']],'items':{},'money':0},self.b.id:{'pokemon':[],'items':{},'money':0}}}
  with patch.object(self.db,'trade',side_effect=OSError('fixture disk failure')):await self.w.commit_trade(t)
  for p,old in zip((self.a,self.b),before):self.assertEqual(p.state,old);self.assertEqual(self.db.load(p.id),old)
 async def test_public_follower_identity_changes_even_between_same_species(self):
  state=copy.deepcopy(self.a.state);first=state['creatures'][0];other=copy.deepcopy(first);other['uid']='fixture-other-uid';other.update(variety='mystic',shiny=False);state['creatures'].append(other);state['party'].append(other['uid']);await self.w.commit(self.a,state)
  before=self.a.entity();await self.w.dispatch(self.a,{'op':'party','party':[other['uid'],first['uid']]});after=self.a.entity()
  self.assertEqual(before['follower'],after['follower']);self.assertEqual(before['followerVariety'],'normal');self.assertEqual(after['followerVariety'],'mystic');self.assertFalse(after['shiny']);self.assertNotIn('creatures',after);self.assertNotIn('varietyDex',after)
 async def test_event_time_identity_is_correct_for_same_species_switch_and_capture(self):
  a=self.c.new_mon('fr_25',20,variety='ancient');b=self.c.new_mon('fr_25',20,variety='shadow');enemy=self.c.new_mon('fr_25',20,variety='mystic');battle=Battle(self.c,'wild',[self.a.id,None],['Akuma','Wild Mystic Pikachu'],[[a,b],[enemy]],[{'pokeball':2},{}])
  battle.audio('hit',0,species='fr_25',damage=1);old=copy.deepcopy(battle.audio_events[-1]);battle.active[0]=1;battle.sendout_audio(0)
  self.assertEqual((old['uid'],old['variety']),(a['uid'],'ancient'));self.assertEqual((battle.audio_events[-1]['uid'],battle.audio_events[-1]['variety']),(b['uid'],'shadow'))
  battle.audio('capture_throw',0,species='fr_25');event=battle.audio_events[-1];self.assertEqual((event['uid'],event['variety']),(enemy['uid'],'mystic'))
  self.assertEqual(battle.audio_view(1)['events'][-1]['side'],'opponent')

if __name__=='__main__':unittest.main()
