"""Normalized, reviewable Crystal encounter facts (not Sigma/Gold/Silver tables).

The compact rows preserve source slot ORDER, including duplicate species/levels.
Do not deduplicate: slot probabilities differ. Rebuild with this module's main.
Primary sources and upstream verifier are documented in Docs/REGIONAL_ENCOUNTERS.md.
"""
from __future__ import annotations
import copy,json,re
from pathlib import Path

SOURCES = [f'https://raw.githubusercontent.com/pret/pokecrystal/master/{p}' for p in (
 'data/wild/johto_grass.asm','data/wild/johto_water.asm',
 'data/wild/kanto_grass.asm','data/wild/kanto_water.asm',
 'data/wild/probabilities.asm','engine/overworld/wildmons.asm','macros/data.asm')]

def build(species):
 names={re.sub('[^a-z0-9]','',v['name'].lower()):k for k,v in species.items() if k.startswith('fr_') and int(k[3:])<=251}
 names.update(nidoranm='fr_32',nidoranf='fr_29',farfetchd='fr_83')
 tables={}
 def slots(row,weights,water=False):
  bits=row.split();assert len(bits)==len(weights),(row,len(bits))
  out=[]
  for bit,weight in zip(bits,weights):
   name,lv=bit.split(':');level=int(lv);key=names[re.sub('[^a-z0-9]','',name.lower())]
   e={'species':key,'min':level,'max':level+(4 if water else 0),'weight':weight}
   # Crystal compares an unsigned random byte against (35/65/85/95)*255//100.
   if water:e['levelWeights']=[89,76,51,26,14]
   out.append(e)
  return out
 def grass(key,rate,m,d=None,n=None):
  t=tables.setdefault(key,{'encounters':{},'rates':{}})
  for period,row in zip(('morning','day','night'),(m,d or m,n or d or m)):
   method='land_'+period;t['encounters'][method]=slots(row,[30,30,20,10,5,4,1]);t['rates'][method]=rate
 def water(keys,rate,row):
  for key in keys.split():
   t=tables.setdefault(key,{'encounters':{},'rates':{}});t['encounters']['water']=slots(row,[60,30,10],True);t['rates']['water']=rate
 def clone(src,*dest):
  for key in dest:tables[key]=copy.deepcopy(tables[src])
 grass('SPROUT_TOWER_2F',2,'Rattata:3 Rattata:4 Rattata:5 Rattata:3 Rattata:6 Rattata:5 Rattata:5',n='Gastly:3 Gastly:4 Gastly:5 Rattata:3 Gastly:6 Rattata:5 Rattata:5')
 clone('SPROUT_TOWER_2F','SPROUT_TOWER_3F')
 grass('TIN_TOWER_2F',2,'Rattata:20 Rattata:21 Rattata:22 Rattata:22 Rattata:23 Rattata:24 Rattata:24',n='Gastly:20 Gastly:21 Gastly:22 Rattata:22 Rattata:23 Rattata:24 Rattata:24')
 clone('TIN_TOWER_2F',*[f'TIN_TOWER_{i}F' for i in range(3,10)])
 grass('BURNED_TOWER_1F',4,'Rattata:13 Koffing:14 Rattata:15 Zubat:14 Rattata:15 Raticate:15 Raticate:15')
 grass('BURNED_TOWER_B1F',6,'Rattata:14 Koffing:14 Koffing:16 Zubat:15 Koffing:12 Koffing:16 Weezing:16')
 grass('NATIONAL_PARK',10,'NidoranM:12 NidoranF:12 Ledyba:14 Pidgey:13 Caterpie:10 Weedle:10 Weedle:10',d='NidoranF:12 NidoranM:12 Sunkern:14 Pidgey:13 Caterpie:10 Weedle:10 Weedle:10',n='Psyduck:12 Hoothoot:13 Spinarak:14 Hoothoot:15 Venonat:10 Venonat:12 Venonat:12')
 grass('RUINS_OF_ALPH_OUTSIDE',4,'Natu:20 Natu:22 Natu:18 Natu:24 Smeargle:20 Smeargle:22 Smeargle:22',n='Natu:20 Natu:22 Natu:18 Natu:24 Wooper:22 Quagsire:22 Quagsire:22')
 grass('RUINS_OF_ALPH_INNER_CHAMBER',6,' '.join(['Unown:5']*7))
 grass('UNION_CAVE_1F',6,'Geodude:6 Sandshrew:6 Zubat:5 Rattata:4 Zubat:7 Onix:6 Onix:6',n='Geodude:6 Rattata:6 Wooper:5 Rattata:4 Zubat:7 Onix:6 Onix:6')
 grass('UNION_CAVE_B1F',6,'Geodude:8 Zubat:6 Zubat:8 Onix:8 Rattata:6 Rattata:8 Rattata:8',n='Geodude:8 Zubat:6 Wooper:8 Onix:8 Rattata:6 Rattata:8 Rattata:8')
 grass('UNION_CAVE_B2F',4,'Zubat:22 Golbat:22 Zubat:22 Raticate:21 Geodude:20 Onix:23 Onix:23',n='Zubat:22 Golbat:22 Quagsire:22 Raticate:21 Geodude:20 Onix:23 Onix:23')
 grass('SLOWPOKE_WELL_B1F',2,'Zubat:5 Zubat:6 Zubat:7 Slowpoke:6 Zubat:8 Slowpoke:8 Slowpoke:8')
 grass('SLOWPOKE_WELL_B2F',2,'Zubat:21 Zubat:23 Zubat:19 Slowpoke:21 Golbat:23 Slowpoke:23 Slowpoke:23')
 grass('ILEX_FOREST',4,'Caterpie:5 Weedle:5 Metapod:7 Kakuna:7 Pidgey:7 Paras:6 Paras:6',n='Oddish:5 Venonat:5 Oddish:7 Psyduck:7 Hoothoot:7 Paras:6 Paras:6')
 grass('MOUNT_MORTAR_1F_OUTSIDE',6,'Rattata:14 Zubat:13 Machop:14 Golbat:13 Geodude:14 Raticate:16 Raticate:16',n='Rattata:14 Zubat:13 Marill:14 Golbat:13 Geodude:14 Raticate:16 Raticate:16')
 grass('MOUNT_MORTAR_1F_INSIDE',6,'Geodude:13 Rattata:14 Machop:15 Raticate:14 Zubat:15 Golbat:15 Golbat:15',n='Geodude:13 Rattata:14 Raticate:15 Zubat:14 Marill:15 Golbat:15 Golbat:15')
 grass('MOUNT_MORTAR_2F_INSIDE',6,'Graveler:31 Machoke:32 Geodude:31 Raticate:30 Machop:28 Golbat:30 Golbat:30',n='Graveler:31 Geodude:31 Raticate:30 Golbat:30 Marill:28 Golbat:32 Golbat:32')
 grass('MOUNT_MORTAR_B1F',6,'Zubat:15 Zubat:17 Golbat:17 Machop:16 Geodude:16 Raticate:18 Raticate:18',n='Zubat:15 Zubat:17 Golbat:17 Marill:16 Geodude:16 Raticate:18 Raticate:18')
 for key,row in {
  'ICE_PATH_1F':'Swinub:21 Zubat:22 Golbat:22 Swinub:23 Golbat:24 Golbat:22 Golbat:22',
  'ICE_PATH_B1F':'Swinub:22 Zubat:23 Golbat:23 Swinub:24 Golbat:25 Golbat:23 Jynx:22',
  'ICE_PATH_B2F_MAHOGANY_SIDE':'Swinub:23 Zubat:24 Golbat:24 Swinub:25 Golbat:26 Jynx:22 Jynx:24',
  'ICE_PATH_B3F':'Swinub:24 Zubat:25 Golbat:25 Swinub:26 Jynx:22 Jynx:24 Jynx:26'}.items():
  grass(key,2,row,n=row.replace('Swinub','Delibird').replace('Jynx','Sneasel'))
 clone('ICE_PATH_B2F_MAHOGANY_SIDE','ICE_PATH_B2F_BLACKTHORN_SIDE')
 for floor,inc in [('NW',0),('B1F',1),('B2F',2),('LUGIA_CHAMBER',3)]:
  def raised(row):return ' '.join(f'{name}:{int(lv)+inc}' for name,lv in (a.split(':') for a in row.split()))
  grass('WHIRL_ISLAND_'+floor,6,raised('Krabby:22 Zubat:23 Seel:22 Krabby:24 Golbat:25 Seel:24 Seel:24'),n=raised('Krabby:22 Zubat:23 Krabby:22 Krabby:24 Golbat:25 Golbat:24 Golbat:24'))
 clone('WHIRL_ISLAND_NW',*[f'WHIRL_ISLAND_{s}' for s in ('NE','SW','CAVE','SE')])
 grass('SILVER_CAVE_ROOM_1',6,'Graveler:43 Ursaring:44 Onix:42 Magmar:45 Golbat:45 Larvitar:20 Larvitar:15',n='Graveler:43 Golbat:44 Onix:42 Golbat:42 Golduck:45 Golbat:46 Golbat:46')
 grass('SILVER_CAVE_ROOM_2',6,'Golbat:48 Machoke:48 Ursaring:47 Parasect:46 Parasect:48 Larvitar:15 Larvitar:20',n='Golbat:48 Golduck:48 Golbat:46 Parasect:46 Parasect:48 Misdreavus:45 Misdreavus:45')
 grass('SILVER_CAVE_ROOM_3',6,'Golbat:51 Onix:48 Graveler:48 Ursaring:50 Larvitar:20 Larvitar:15 Pupitar:20',n='Golbat:51 Onix:48 Graveler:48 Golbat:49 Golduck:45 Golbat:53 Golbat:53')
 grass('SILVER_CAVE_ITEM_ROOMS',6,'Golbat:48 Golbat:46 Golbat:50 Parasect:46 Parasect:48 Parasect:50 Parasect:52',n='Misdreavus:45 Golbat:48 Golbat:50 Parasect:46 Parasect:48 Parasect:50 Parasect:52')
 grass('DARK_CAVE_VIOLET_ENTRANCE',4,'Geodude:3 Zubat:2 Geodude:2 Geodude:4 Teddiursa:2 Zubat:4 Dunsparce:4',d='Geodude:3 Zubat:2 Geodude:2 Geodude:4 Zubat:2 Zubat:4 Dunsparce:4')
 grass('DARK_CAVE_BLACKTHORN_ENTRANCE',4,'Geodude:23 Zubat:23 Graveler:25 Ursaring:25 Teddiursa:20 Golbat:23 Golbat:23',d='Geodude:23 Zubat:23 Graveler:25 Ursaring:25 Ursaring:30 Golbat:23 Golbat:23',n='Geodude:23 Zubat:23 Graveler:25 Wobbuffet:20 Wobbuffet:25 Golbat:23 Golbat:23')
 grass('ROUTE_29',10,'Pidgey:2 Sentret:2 Pidgey:3 Sentret:3 Rattata:2 Hoppip:3 Hoppip:3',n='Hoothoot:2 Rattata:2 Hoothoot:3 Rattata:3 Rattata:2 Hoothoot:3 Hoothoot:3')
 grass('ROUTE_30',10,'Ledyba:3 Caterpie:3 Caterpie:4 Pidgey:4 Weedle:3 Hoppip:4 Hoppip:4',d='Pidgey:3 Caterpie:3 Caterpie:4 Pidgey:4 Weedle:3 Hoppip:4 Hoppip:4',n='Spinarak:3 Hoothoot:3 Poliwag:4 Hoothoot:4 Zubat:3 Hoothoot:4 Hoothoot:4')
 grass('ROUTE_31',10,'Ledyba:4 Caterpie:4 Bellsprout:5 Pidgey:5 Weedle:4 Hoppip:5 Hoppip:5',d='Pidgey:4 Caterpie:4 Bellsprout:5 Pidgey:5 Weedle:4 Hoppip:5 Hoppip:5',n='Spinarak:4 Poliwag:4 Bellsprout:5 Hoothoot:5 Zubat:4 Gastly:5 Gastly:5')
 grass('ROUTE_32',10,'Ekans:4 Rattata:5 Bellsprout:7 Hoppip:6 Pidgey:7 Hoppip:7 Hoppip:7',n='Wooper:4 Rattata:5 Bellsprout:7 Zubat:6 Hoothoot:7 Gastly:7 Gastly:7')
 grass('ROUTE_33',10,'Rattata:6 Spearow:6 Geodude:6 Hoppip:6 Ekans:7 Hoppip:7 Hoppip:7',n='Rattata:6 Zubat:6 Geodude:6 Zubat:6 Rattata:7 Rattata:7 Rattata:7')
 grass('ROUTE_34',10,'Snubbull:10 Rattata:11 Pidgey:12 Abra:10 Jigglypuff:12 Ditto:10 Ditto:10',n='Drowzee:12 Rattata:11 Hoothoot:12 Abra:10 Jigglypuff:12 Ditto:10 Ditto:10')
 grass('ROUTE_35',10,'Snubbull:12 Pidgey:14 Growlithe:13 Abra:10 Jigglypuff:12 Ditto:10 Yanma:12',n='Drowzee:12 Hoothoot:14 Psyduck:13 Abra:10 Jigglypuff:12 Ditto:10 Yanma:12')
 grass('ROUTE_36',10,'Ledyba:4 Pidgey:4 Bellsprout:5 Growlithe:5 Pidgey:5 Pidgey:6 Pidgey:6',d='Pidgey:4 Pidgey:4 Bellsprout:5 Growlithe:5 Pidgey:5 Pidgey:6 Pidgey:6',n='Spinarak:4 Hoothoot:4 Bellsprout:5 Hoothoot:5 Hoothoot:5 Gastly:5 Gastly:5')
 grass('ROUTE_37',10,'Ledyba:13 Growlithe:14 Pidgey:15 Growlithe:16 Pidgeotto:15 Ledian:15 Ledian:15',d='Pidgey:13 Growlithe:14 Pidgey:15 Growlithe:16 Pidgeotto:15 Pidgey:15 Pidgey:15',n='Spinarak:13 Stantler:14 Hoothoot:15 Stantler:16 Noctowl:15 Ariados:15 Ariados:15')
 grass('ROUTE_38',10,'Rattata:16 Raticate:16 Magnemite:16 Pidgeotto:16 Tauros:13 Miltank:13 Miltank:13',n='Meowth:16 Raticate:16 Magnemite:16 Noctowl:16 Meowth:16 Meowth:16 Meowth:16')
 grass('ROUTE_39',2,'Rattata:16 Raticate:16 Magnemite:16 Pidgeotto:16 Miltank:15 Tauros:15 Tauros:15',n='Meowth:16 Raticate:16 Magnemite:16 Noctowl:16 Meowth:18 Meowth:18 Meowth:18')
 grass('ROUTE_42',10,'Ekans:13 Spearow:14 Rattata:15 Raticate:16 Arbok:15 Fearow:16 Fearow:16',n='Rattata:13 Zubat:14 Raticate:15 Golbat:16 Marill:15 Golbat:16 Golbat:16')
 grass('ROUTE_43',10,'Sentret:15 Pidgeotto:16 Farfetchd:16 Furret:15 Raticate:17 Furret:17 Furret:17',n='Venonat:15 Noctowl:16 Raticate:16 Venonat:17 Raticate:17 Venomoth:17 Venomoth:17')
 grass('ROUTE_44',10,'Tangela:23 Lickitung:22 Bellsprout:22 Weepinbell:24 Lickitung:24 Lickitung:26 Lickitung:26',n='Tangela:23 Poliwag:22 Bellsprout:22 Weepinbell:24 Poliwhirl:24 Poliwhirl:26 Poliwhirl:26')
 grass('ROUTE_45',10,'Geodude:23 Graveler:23 Gligar:24 Donphan:25 Phanpy:20 Skarmory:27 Skarmory:27',d='Geodude:23 Graveler:23 Gligar:24 Donphan:25 Donphan:30 Skarmory:27 Skarmory:27',n='Geodude:23 Graveler:23 Gligar:24 Graveler:25 Graveler:27 Graveler:27 Graveler:27')
 grass('ROUTE_46',10,'Geodude:2 Spearow:2 Geodude:3 Rattata:3 Phanpy:2 Rattata:2 Rattata:2',d='Geodude:2 Spearow:2 Geodude:3 Rattata:3 Rattata:2 Rattata:2 Rattata:2',n='Geodude:2 Rattata:2 Geodude:3 Rattata:3 Rattata:2 Rattata:2 Rattata:2')
 grass('SILVER_CAVE_OUTSIDE',10,'Tangela:41 Ponyta:42 Arbok:42 Rapidash:44 Doduo:41 Dodrio:43 Dodrio:43',n='Tangela:41 Poliwhirl:42 Golbat:42 Poliwhirl:44 Golbat:40 Golbat:44 Golbat:44')
 grass('VICTORY_ROAD',6,'Graveler:34 Rhyhorn:32 Onix:33 Golbat:34 Sandslash:35 Rhydon:35 Rhydon:35',n='Golbat:34 Graveler:34 Onix:32 Graveler:36 Graveler:38 Graveler:40 Graveler:40')
 grass('TOHJO_FALLS',6,'Zubat:22 Raticate:22 Golbat:24 Slowpoke:21 Rattata:20 Slowpoke:23 Slowpoke:23')
 grass('ROUTE_26',10,'Doduo:28 Sandslash:28 Ponyta:32 Raticate:30 Doduo:30 Arbok:30 Arbok:30',n='Noctowl:28 Raticate:28 Noctowl:32 Raticate:30 Quagsire:30 Quagsire:30 Quagsire:30')
 grass('ROUTE_27',10,'Doduo:28 Arbok:28 Raticate:30 Doduo:30 Ponyta:32 Dodrio:30 Dodrio:30',n='Quagsire:28 Noctowl:28 Raticate:30 Quagsire:30 Noctowl:32 Noctowl:32 Noctowl:32')
 grass('ROUTE_28',10,'Tangela:39 Ponyta:40 Rapidash:40 Arbok:42 Doduo:41 Dodrio:43 Dodrio:43',n='Tangela:39 Poliwhirl:40 Golbat:40 Poliwhirl:40 Golbat:42 Golbat:42 Golbat:42')
 water('RUINS_OF_ALPH_OUTSIDE UNION_CAVE_1F UNION_CAVE_B1F',2,'Wooper:15 Quagsire:20 Quagsire:15')
 water('UNION_CAVE_B2F',4,'Tentacool:15 Quagsire:20 Tentacruel:20')
 water('SLOWPOKE_WELL_B1F',2,'Slowpoke:15 Slowpoke:20 Slowpoke:10')
 water('SLOWPOKE_WELL_B2F',2,'Slowpoke:15 Slowpoke:20 Slowbro:20')
 water('ILEX_FOREST',2,'Psyduck:15 Psyduck:10 Golduck:15')
 water('MOUNT_MORTAR_1F_OUTSIDE',4,'Goldeen:15 Marill:20 Seaking:20')
 water('MOUNT_MORTAR_2F_INSIDE',2,'Goldeen:20 Marill:25 Seaking:25')
 water('MOUNT_MORTAR_B1F',2,'Goldeen:15 Marill:20 Seaking:20')
 water('WHIRL_ISLAND_SW',4,'Tentacool:20 Horsea:15 Tentacruel:20')
 water('WHIRL_ISLAND_B2F',4,'Horsea:15 Horsea:20 Tentacruel:20')
 water('WHIRL_ISLAND_LUGIA_CHAMBER',4,'Horsea:20 Tentacruel:20 Seadra:20')
 water('SILVER_CAVE_ROOM_2',2,'Seaking:35 Golduck:35 Goldeen:35')
 water('DARK_CAVE_VIOLET_ENTRANCE DARK_CAVE_BLACKTHORN_ENTRANCE',2,'Magikarp:15 Magikarp:10 Magikarp:5')
 water('DRAGONS_DEN_B1F',4,'Magikarp:15 Magikarp:10 Dratini:10')
 water('OLIVINE_PORT',2,'Tentacool:20 Tentacool:15 Tentacruel:20')
 water('ROUTE_30 ROUTE_31 VIOLET_CITY ECRUTEAK_CITY',2,'Poliwag:20 Poliwag:15 Poliwhirl:20')
 water('ROUTE_32',6,'Tentacool:15 Quagsire:20 Tentacruel:20')
 water('ROUTE_34 ROUTE_40 NEW_BARK_TOWN CHERRYGROVE_CITY CIANWOOD_CITY OLIVINE_CITY',6,'Tentacool:20 Tentacool:15 Tentacruel:20')
 water('ROUTE_35',4,'Psyduck:20 Psyduck:15 Golduck:20')
 water('ROUTE_41',6,'Tentacool:20 Tentacruel:20 Mantine:20')
 water('ROUTE_42',4,'Goldeen:20 Goldeen:15 Seaking:20')
 water('ROUTE_43',2,'Magikarp:20 Magikarp:15 Magikarp:10')
 water('ROUTE_44',2,'Poliwag:25 Poliwag:20 Poliwhirl:25')
 water('ROUTE_45',2,'Magikarp:20 Magikarp:15 Magikarp:5')
 water('LAKE_OF_RAGE',6,'Magikarp:15 Magikarp:10 Gyarados:15')
 water('BLACKTHORN_CITY',4,'Magikarp:15 Magikarp:10 Magikarp:5')
 water('SILVER_CAVE_OUTSIDE',2,'Poliwhirl:35 Poliwhirl:40 Poliwag:35')
 water('TOHJO_FALLS',4,'Goldeen:20 Slowpoke:20 Seaking:20')
 water('ROUTE_26',6,'Tentacool:30 Tentacool:25 Tentacruel:30')
 water('ROUTE_27',6,'Tentacool:20 Tentacool:15 Tentacruel:20')
 water('ROUTE_28',2,'Poliwag:40 Poliwag:35 Poliwhirl:40')
 return {'format':1,'game':'Pokemon Crystal','sourceRetrieved':'2026-09-13','sources':SOURCES,'tables':tables}

if __name__=='__main__':
 root=Path(__file__).resolve().parents[1]
 world=json.loads((root/'Server/data/world.json').read_text(encoding='utf-8'))
 result=build(world['species'])
 (root/'Server/data/encounters_crystal.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f'Wrote {len(result["tables"])} Crystal tables.')
