"""Owner-only scripted environmental story gates.

Story objects live in immutable shared map content.  Per-character completion is
stored only in ``adventure.storyEvents`` so clearing an obstacle never mutates
another trainer's map or collision state.  Required key items are normal saved
inventory entries marked non-buyable/non-tradable in authored content.
"""
from __future__ import annotations
import copy


def definitions(content):
 return content.data.get('adventure', {}).get('storyEvents', [])


def by_id(content, event_id):
 return next((event for event in definitions(content) if event.get('id') == event_id), None)


def for_object(content, map_id, obj):
 event_id = obj.get('storyEvent') if isinstance(obj, dict) else None
 event = by_id(content, event_id)
 return event if event and event.get('map') == map_id and event.get('npc') == obj.get('id') else None


def cleared(state, event_id):
 return bool(state and event_id in state.get('adventure', {}).get('storyEvents', []))


def mark_cleared(state, event_id):
 events = state['adventure'].setdefault('storyEvents', [])
 if event_id not in events:
  events.append(event_id);events.sort()
 return state


def refresh_rewards(state, content):
 """Grant badge-earned story key items once; return newly granted item ids."""
 a = state.setdefault('adventure', {})
 badges = set(a.get('badges', []));items = state.setdefault('items', {});granted = []
 key_items = content.data.get('adventure', {}).get('keyItems', {})
 for key, spec in key_items.items():
  # Key items are unique ownership flags even though the general bag is counted.
  count = items.get(key, 0)
  if type(count) is not int or count < 0:items[key] = 0
  elif count > 1:items[key] = 1
 for event in definitions(content):
  if not event.get('awardItemOnBadge'):continue
  badge,item = event.get('requiredBadge'),event.get('requiredItem')
  if item not in key_items:continue
  # This authored item is earned only from its badge gate.  An old/forged save
  # cannot smuggle the Key Item in before progression; legitimate upgraded
  # characters with the badge are repaired additively on login.
  if badge and badge not in badges:
   items.pop(item,None);continue
  if items.get(item, 0) < 1:items[item] = 1;granted.append(item)
 return granted


def migrate(state, content):
 """Additive save migration and validation for story completion/key items."""
 a = state.setdefault('adventure', {});raw = a.get('storyEvents', []);valid = {}
 for event in definitions(content):valid[event['id']] = event
 cleaned = []
 if isinstance(raw, list):
  badges = set(a.get('badges', []))
  for event_id in raw:
   if not isinstance(event_id, str) or event_id not in valid:continue
   required = valid[event_id].get('requiredBadge')
   if required and required not in badges:continue
   if event_id not in cleaned:cleaned.append(event_id)
 a['storyEvents'] = sorted(cleaned)
 refresh_rewards(state, content)
 return state


def public(state, content):
 a = state.get('adventure', {});badges = set(a.get('badges', []));items = state.get('items', {})
 rows = []
 for event in definitions(content):
  done = cleared(state, event['id']);badge = event.get('requiredBadge');item = event.get('requiredItem')
  badge_earned = not badge or badge in badges;item_owned = not item or items.get(item, 0) > 0
  rows.append({
   'id': event['id'], 'title': event.get('title', event['id']), 'map': event.get('map'),
   'description': event.get('description', ''), 'cleared': done, 'ready': not done and badge_earned and item_owned,
   'badgeEarned': badge_earned, 'itemOwned': item_owned, 'requiredBadge': badge,
   'requiredBadgeName': event.get('requiredBadgeName'), 'leader': event.get('leader'), 'city': event.get('city'),
   'requiredItem': item, 'itemName': event.get('itemName', item),
  })
 return rows
