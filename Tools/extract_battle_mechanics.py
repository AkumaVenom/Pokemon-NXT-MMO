#!/usr/bin/env python3
"""Extract battle metadata needed by Pokemon NXT's Gen-III move engine.

This is a static, hash-pinned extractor. It reads move table bytes and species
battle fields from the reviewed FireRed Rev 1 and Sigma 1.5.0 ROMs. It never
executes ROM code. The generated JSON is sufficient for builds; ROM files are
not shipped or needed at runtime.
"""
from __future__ import annotations
import argparse, hashlib, json, struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROFILES={
 'kanto':{'sha256':'729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059','bytes':16777216,'label':'FireRed USA/Europe Rev 1'},
 'johto':{'sha256':'62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64','bytes':17632785,'label':'Ultra Shiny Gold Sigma Completo 1.5.0'},
}
SIGMA_ALIASES={183,210,237,294,295,297,346}
EFFECT_NAMES=[
'HIT','SLEEP','POISON_HIT','ABSORB','BURN_HIT','FREEZE_HIT','PARALYZE_HIT','EXPLOSION','DREAM_EATER','MIRROR_MOVE',
'ATTACK_UP','DEFENSE_UP','SPEED_UP','SPECIAL_ATTACK_UP','SPECIAL_DEFENSE_UP','ACCURACY_UP','EVASION_UP','ALWAYS_HIT','ATTACK_DOWN','DEFENSE_DOWN',
'SPEED_DOWN','SPECIAL_ATTACK_DOWN','SPECIAL_DEFENSE_DOWN','ACCURACY_DOWN','EVASION_DOWN','HAZE','BIDE','RAMPAGE','ROAR','MULTI_HIT','CONVERSION',
'FLINCH_HIT','RESTORE_HP','TOXIC','PAY_DAY','LIGHT_SCREEN','TRI_ATTACK','REST','OHKO','RAZOR_WIND','SUPER_FANG','DRAGON_RAGE','TRAP','HIGH_CRITICAL','DOUBLE_HIT','RECOIL_IF_MISS','MIST','FOCUS_ENERGY','RECOIL','CONFUSE',
'ATTACK_UP_2','DEFENSE_UP_2','SPEED_UP_2','SPECIAL_ATTACK_UP_2','SPECIAL_DEFENSE_UP_2','ACCURACY_UP_2','EVASION_UP_2','TRANSFORM','ATTACK_DOWN_2','DEFENSE_DOWN_2','SPEED_DOWN_2','SPECIAL_ATTACK_DOWN_2','SPECIAL_DEFENSE_DOWN_2','ACCURACY_DOWN_2','EVASION_DOWN_2','REFLECT','POISON','PARALYZE','ATTACK_DOWN_HIT','DEFENSE_DOWN_HIT','SPEED_DOWN_HIT','SPECIAL_ATTACK_DOWN_HIT','SPECIAL_DEFENSE_DOWN_HIT','ACCURACY_DOWN_HIT','EVASION_DOWN_HIT','SKY_ATTACK','CONFUSE_HIT','TWINEEDLE','VITAL_THROW','SUBSTITUTE','RECHARGE','RAGE','MIMIC','METRONOME','LEECH_SEED','SPLASH','DISABLE','LEVEL_DAMAGE','PSYWAVE','COUNTER','ENCORE','PAIN_SPLIT','SNORE','CONVERSION_2','LOCK_ON','SKETCH','UNUSED_60','SLEEP_TALK','DESTINY_BOND','FLAIL','SPITE','FALSE_SWIPE','HEAL_BELL','QUICK_ATTACK','TRIPLE_KICK','THIEF','MEAN_LOOK','NIGHTMARE','MINIMIZE','CURSE','UNUSED_6E','PROTECT','SPIKES','FORESIGHT','PERISH_SONG','SANDSTORM','ENDURE','ROLLOUT','SWAGGER','FURY_CUTTER','ATTRACT','RETURN','PRESENT','FRUSTRATION','SAFEGUARD','THAW_HIT','MAGNITUDE','BATON_PASS','PURSUIT','RAPID_SPIN','SONICBOOM','UNUSED_83','MORNING_SUN','SYNTHESIS','MOONLIGHT','HIDDEN_POWER','RAIN_DANCE','SUNNY_DAY','DEFENSE_UP_HIT','ATTACK_UP_HIT','ALL_STATS_UP_HIT','UNUSED_8D','BELLY_DRUM','PSYCH_UP','MIRROR_COAT','SKULL_BASH','TWISTER','EARTHQUAKE','FUTURE_SIGHT','GUST','FLINCH_MINIMIZE_HIT','SOLAR_BEAM','THUNDER','TELEPORT','BEAT_UP','SEMI_INVULNERABLE','DEFENSE_CURL','SOFTBOILED','FAKE_OUT','UPROAR','STOCKPILE','SPIT_UP','SWALLOW','UNUSED_A3','HAIL','TORMENT','FLATTER','WILL_O_WISP','MEMENTO','FACADE','FOCUS_PUNCH','SMELLINGSALT','FOLLOW_ME','NATURE_POWER','CHARGE','TAUNT','HELPING_HAND','TRICK','ROLE_PLAY','WISH','ASSIST','INGRAIN','SUPERPOWER','MAGIC_COAT','RECYCLE','REVENGE','BRICK_BREAK','YAWN','KNOCK_OFF','ENDEAVOR','ERUPTION','SKILL_SWAP','IMPRISON','REFRESH','GRUDGE','SNATCH','LOW_KICK','SECRET_POWER','DOUBLE_EDGE','TEETER_DANCE','BLAZE_KICK','MUD_SPORT','POISON_FANG','WEATHER_BALL','OVERHEAT','TICKLE','COSMIC_POWER','SKY_UPPERCUT','BULK_UP','POISON_TAIL','WATER_SPORT','CALM_MIND','DRAGON_DANCE','CAMOUFLAGE']

class Rom:
 def __init__(self,path,tag):
  self.path=Path(path);self.b=self.path.read_bytes();self.tag=tag
  p=PROFILES[tag];digest=hashlib.sha256(self.b).hexdigest()
  if len(self.b)!=p['bytes'] or digest!=p['sha256']:
   raise ValueError(f'{tag} ROM does not match reviewed source: {len(self.b)} bytes {digest}')
  self.sha256=digest
 def u16(self,o):return struct.unpack_from('<H',self.b,o)[0]
 def u32(self,o):return struct.unpack_from('<I',self.b,o)[0]
 def ptr(self,o):
  v=self.u32(o)
  if not 0x08000000<=v<0x0A000000:raise ValueError(f'bad GBA pointer {v:08x} at {o:x}')
  q=v-0x08000000
  if q>=len(self.b):raise ValueError(f'pointer outside ROM at {o:x}')
  return q

def move_records(r):
 table=r.ptr(0x1cc);out={}
 for mid in range(1,355):
  o=table+mid*12;raw=r.b[o:o+12]
  if len(raw)!=12:raise ValueError('truncated move table')
  effect=raw[0]
  if effect>=len(EFFECT_NAMES):raise ValueError(f'unknown move effect {effect}')
  out[mid]={'effect':effect,'effectName':EFFECT_NAMES[effect],'power':raw[1],'type':raw[2],'accuracy':raw[3],'pp':raw[4],'chance':raw[5],'target':raw[6],'priority':struct.unpack('b',raw[7:8])[0],'flags':raw[8],'categoryByte':raw[10],'offset':hex(o),'rawHex':raw.hex()}
 return out,table

def fr_dex_number(source_id):
 if 1<=source_id<=251:return source_id
 if 277<=source_id<=411:return source_id-25
 return None

def pokedex_weight_fire_red(r,dex):
 # Reviewed Rev-1 table identified from the ROM itself; entry stride is 36.
 base=0x44e8e0
 if not 1<=dex<=386:return None
 o=base+(dex-1)*36
 h,w=struct.unpack_from('<HH',r.b,o)
 return {'heightDecimeters':h,'weightHectograms':w,'pokedexOffset':hex(o)}

def species_record(r,sid):
 base=r.ptr(0x1bc);o=base+sid*28
 raw=r.b[o:o+28]
 if len(raw)!=28:raise ValueError(f'{r.tag} species {sid} outside base-stat table')
 return {'genderRatio':raw[16],'eggCycles':raw[17],'baseFriendship':raw[18],
         'growthRate':raw[19],'eggGroups':[raw[20],raw[21]],'abilities':[raw[22],raw[23]],
         'heldItems':[struct.unpack_from('<H',raw,12)[0],struct.unpack_from('<H',raw,14)[0]],
         'baseStatsOffset':hex(o),'baseStatsRawHex':raw.hex()}

def extract(fr_path,sigma_path,root=ROOT):
 root=Path(root);world_path=root/'Server/data/world.json';world=json.loads(world_path.read_text(encoding='utf-8'))
 roms={'kanto':Rom(fr_path,'kanto'),'johto':Rom(sigma_path,'johto')};moves={};tables={}
 native={}
 for tag,r in roms.items():native[tag],tables[tag]=move_records(r)
 for mid in range(1,355):
  rec=dict(native['kanto'][mid]);rec.update(source='kanto',sourceMoveId=mid,sourceSha256=roms['kanto'].sha256)
  moves[str(mid)]=rec
 for raw_id in sorted(SIGMA_ALIASES):
  rec=dict(native['johto'][raw_id]);rec.update(source='johto',sourceMoveId=raw_id,sourceSha256=roms['johto'].sha256)
  moves[str(1024+raw_id)]=rec
 # Exact FireRed weight lookup by normalized species name lets Sigma copies of
 # original Gen-I/II/III species reuse a ROM-proven value without guessing its
 # hack-specific internal species index.
 fr_weights={}
 for key,s in world['species'].items():
  if s.get('source')!='kanto':continue
  dex=fr_dex_number(int(s['sourceId']))
  if dex:
   w=pokedex_weight_fire_red(roms['kanto'],dex)
   if w:fr_weights[s['name'].casefold().replace('-','').replace(' ','')]=w['weightHectograms']
 species={};unknown_weights=[]
 for key,s in world['species'].items():
  tag=s['source'];sid=int(s['sourceId']);rec=species_record(roms[tag],sid)
  weight=None;weight_source=None
  if tag=='kanto':
   dex=fr_dex_number(sid)
   if dex:
    w=pokedex_weight_fire_red(roms['kanto'],dex);weight=w['weightHectograms'];weight_source='firered-pokedex'
  if weight is None:
   weight=fr_weights.get(s['name'].casefold().replace('-','').replace(' ',''))
   if weight is not None:weight_source='firered-name-match'
  if weight is None:
   # Sigma expands species far beyond FireRed's Pokedex table. Keep the lack of
   # source evidence explicit instead of inventing a modern weight.
   weight=1000;weight_source='unknown-fallback';unknown_weights.append(key)
  rec.update(source=tag,sourceSpeciesId=sid,sourceSha256=roms[tag].sha256,weightHectograms=weight,weightSource=weight_source)
  species[key]=rec
 audit={'format':1,'engine':'Gen III singles move-effect runtime','sources':{tag:{**PROFILES[tag],'moveTable':hex(tables[tag]),'speciesTable':hex(roms[tag].ptr(0x1bc))} for tag in roms},
        'effectNames':{str(i):n for i,n in enumerate(EFFECT_NAMES)},'moves':moves,'species':species,
        'audit':{'moveRecords':len(moves),'effectIds':len({v['effect'] for v in moves.values()}),'speciesRecords':len(species),'unknownSigmaWeights':len(unknown_weights),'unknownSigmaWeightSpecies':unknown_weights},
        'policy':{'moves':'Canonical IDs 1-354 use FireRed Rev-1 move table mechanics. Seven separately published Sigma aliases use their native Sigma table records.',
                  'species':'Gender ratio, base friendship, abilities and held-item fields are read directly from the species base-stat record selected by each published sourceSpeciesId.',
                  'weights':'FireRed species weights come from the reviewed ROM Pokedex table. Sigma species with a name-matched FireRed identity reuse that exact value. Hack-expanded identities without an extractable reviewed Pokedex mapping are explicitly marked unknown-fallback.'}}
 (root/'Server/data/battle_mechanics.json').write_text(json.dumps(audit,separators=(',',':')),encoding='utf-8')
 # Publish exact move flags/category/provenance into the runtime content. Keep
 # existing stable IDs/names and existing Sigma aliases unchanged otherwise.
 for key,move in world['moves'].items():
  rec=moves.get(key)
  if not rec:continue
  move['flags']=rec['flags'];move['category']=rec['categoryByte'] if rec['source']=='johto' else (0 if rec['type']<=8 else 1)
  move['battleEffectName']=rec['effectName']
  move['battleProvenance']={'source':rec['source'],'sha256':rec['sourceSha256'],'sourceMoveId':rec['sourceMoveId'],'offset':rec['offset'],'rawHex':rec['rawHex']}
 for key,s in world['species'].items():
  rec=species[key]
  for field in ('genderRatio','baseFriendship','abilities','heldItems','weightHectograms','weightSource'):s[field]=rec[field]
 world_path.write_text(json.dumps(world,separators=(',',':')),encoding='utf-8')
 return audit

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--firered',required=True);ap.add_argument('--sigma',required=True);ap.add_argument('--root',default=str(ROOT));a=ap.parse_args()
 out=extract(a.firered,a.sigma,a.root);print(f"Published {out['audit']['moveRecords']} move records / {out['audit']['speciesRecords']} species battle records; {out['audit']['unknownSigmaWeights']} hack-expanded weights explicitly unresolved.")
if __name__=='__main__':main()
