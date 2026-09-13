"""Per-account environmental progress; shared map/collision assets are immutable.

Cut is a field licence, not a destructive replacement of a partner's battle move.
Badge checks are derived from earned regional badges, never from client input or
an advisory saved unlock string. Clearing is durable and owner-only.
"""
from __future__ import annotations

CUT_GRAPHICS = 95
CUT_REQUIREMENTS = {
 'kanto': {'badge': 'kanto_2', 'badgeName': 'Cascade Badge', 'leader': 'Misty', 'city': 'Cerulean City'},
 'johto': {'badge': 'johto_2', 'badgeName': 'Hive Badge', 'leader': 'Bugsy', 'city': 'Azalea Town'},
}

def region(map_id):
 return str(map_id).split('_', 1)[0].lower()

def is_cut_tree(obj):
 return obj.get('graphics') == CUT_GRAPHICS

def cut_allowed(state, map_id=None):
 rule = CUT_REQUIREMENTS.get(region(map_id or state['map']))
 return bool(rule and rule['badge'] in state.get('adventure', {}).get('badges', []))

def tree_cleared(state, map_id, obj):
 return bool(state and is_cut_tree(obj) and obj['id'] in state.get('adventure', {}).get('cutTrees', {}).get(map_id, []))

def migrate_cuts(state, maps):
 """Additive migration. Invalid flags can never remove rocks or arbitrary walls."""
 raw = state['adventure'].get('cutTrees', {})
 cleaned = {}
 if isinstance(raw, dict):
  for key, ids in raw.items():
   if key not in maps or not isinstance(ids, list):continue
   valid = {o['id'] for o in maps[key]['objects'] if is_cut_tree(o)}
   kept = sorted({n for n in ids if type(n) is int and n in valid})
   if kept:cleaned[key] = kept
 state['adventure']['cutTrees'] = cleaned

def public_field_moves(state):
 return [{'id': 'cut_' + key, 'move': 'Cut', 'region': key,
          **rule, 'unlocked': cut_allowed(state, key)}
         for key, rule in CUT_REQUIREMENTS.items()]
