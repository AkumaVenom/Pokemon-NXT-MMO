"""Focused static regression checks for autonomous competitive + overworld life."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Server'))
from nxt.ai_trainers import BACKGROUND_FIELD_VERSION,PARTY_IDENTITY_VERSION,REGIONAL_TRAVEL_VERSION,WORLD_LIFE_VERSION,elo,tier_for
assert WORLD_LIFE_VERSION >= 3
assert PARTY_IDENTITY_VERSION >= 1
assert REGIONAL_TRAVEL_VERSION >= 2
assert BACKGROUND_FIELD_VERSION >= 1
assert tier_for(1000)=='Bronze'
assert tier_for(1100)=='Silver'
assert tier_for(2100)=='Champion'
assert elo(1000,1000,1)>1000 and elo(1000,1000,0)<1000
world=(ROOT/'Server/nxt/world.py').read_text(encoding='utf-8')
ai=(ROOT/'Server/nxt/ai_trainers.py').read_text(encoding='utf-8')
store=(ROOT/'Server/nxt/store.py').read_text(encoding='utf-8')
client=(ROOT/'Client/app/app.js').read_text(encoding='utf-8')
renderer=(ROOT/'Client/app/renderer.js').read_text(encoding='utf-8')
config=(ROOT/'Build/config_templates/Server/config.ini').read_text(encoding='utf-8')
assert "ai.dashboard" in world and "ai.challenge" in world and 'field_tick' in world and 'background_field_tick' in world
assert '_simulate_wild_battle' in ai and '_travel_reason' in ai and '_select_travel_map' in ai and 'field_step_ms' in config
assert 'nextBackgroundFieldAt' in ai and 'background_field_interval_seconds' in config and 'background_field_batch' in config
assert 'travel_min_seconds' in config and 'travel_safe_level_margin' in config and "'kind': 'travel'" in ai
assert 'map_resident_floor' in config and 'active_map_departure_seconds' in config and 'materialized_spacing_tiles' in config
assert '_materialized_bots' in ai and '_ensure_materialized_spacing' in ai and '_resident_floor' in ai
assert '_party_members' in ai and 'partyIdentityVersion' in ai and 'legacySyntheticPokemonRemoved' in ai
assert 'SCHEMA=3' in store and 'AIStoreMixin' in store
assert 'requestAIDashboard' in client and 'Battle autonomous trainer' in client
assert "fieldAction==='wild_battle'" in renderer
print('autonomous trainer overworld regression checks passed')
