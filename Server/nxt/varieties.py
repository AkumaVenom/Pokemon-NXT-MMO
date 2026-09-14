"""Server-owned cosmetic identities, weighted wild rolls and private collection history.

Species and variety are orthogonal. Never create new species IDs, multiply combat
stats, re-roll a captured creature, or accept a variety from a player command.
"""
from __future__ import annotations
import copy
import re
from .security import require

VARIETIES = ('normal', 'ancient', 'metallic', 'shiny', 'mystic', 'shadow')
DEFAULT_WEIGHTS = (9000, 250, 250, 125, 250, 125)

def variety_key(mon):
    """Read modern identity, or a genuine pre-variety shiny flag, without mutation."""
    if not isinstance(mon, dict): return 'normal'
    value = mon.get('variety')
    if isinstance(value, str) and value in VARIETIES: return value
    return 'shiny' if 'variety' not in mon and mon.get('shiny') is True else 'normal'

def validate_policy(policy):
    if not isinstance(policy, dict) or policy.get('format') != 1:
        raise ValueError('Unsupported variety policy format')
    order = policy.get('order'); definitions = policy.get('definitions')
    if order != list(VARIETIES) or not isinstance(definitions, dict) or set(definitions) != set(VARIETIES):
        raise ValueError('The variety policy must declare the six supported identities exactly once')
    denominator = policy.get('rollDenominator')
    if type(denominator) is not int or not 1 <= denominator <= 1_000_000:
        raise ValueError('Invalid variety roll denominator')
    for key in VARIETIES:
        row = definitions[key]
        if not isinstance(row, dict) or type(row.get('weight')) is not int or row['weight'] < 0:
            raise ValueError('Invalid variety weight: '+key)
        if not isinstance(row.get('label'), str) or not 1 <= len(row['label']) <= 24:
            raise ValueError('Invalid variety label: '+key)
        if not isinstance(row.get('color'), str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', row['color']):
            raise ValueError('Invalid variety effect colour: '+key)
    if definitions['normal']['weight'] <= 0 or sum(definitions[v]['weight'] for v in VARIETIES) != denominator:
        raise ValueError('Variety weights must sum exactly to the roll denominator')

class Varieties:
    def __init__(self, content):
        self.c = content
        self.policy = content.data.get('varietyPolicy')
        if self.policy is not None: validate_policy(self.policy)

    def supported(self, species, value):
        profile = self.c.species.get(species)
        if not profile or value not in VARIETIES: return False
        if value == 'normal': return bool(profile.get('front'))
        if value == 'shiny': return bool(profile.get('varieties', {}).get(value) or profile.get('shiny'))
        return bool(profile.get('varieties', {}).get(value))

    def roll(self, species):
        """One cryptographic server roll. Missing art returns Normal; never retry.

        Reserved missing-art tickets do not redistribute into other rarities.
        This keeps each supported variety's advertised probability unchanged.
        """
        if species not in self.c.species: raise ValueError('Unknown encounter species')
        if self.policy is None: return 'normal'  # Unpublished legacy/test content.
        ticket = self.c.rng.randrange(self.policy['rollDenominator'])
        for key in VARIETIES:
            ticket -= self.policy['definitions'][key]['weight']
            if ticket < 0: return key if self.supported(species, key) else 'normal'
        raise RuntimeError('Validated variety weights did not select an identity')

    def normalize_mon(self, mon):
        if 'variety' in mon:
            require(isinstance(mon['variety'], str) and mon['variety'] in VARIETIES,
                    'This Pokemon has an unsupported variety; use its matching server/content version.')
        value = variety_key(mon)
        mon['variety'] = value
        mon['shiny'] = value == 'shiny'  # Compatibility output, not a second identity.
        return mon

    def display_name(self, mon):
        value = variety_key(mon); name = self.c.species[mon['species']]['name']
        return name if value == 'normal' else value.title()+' '+name

    def migrate(self, state):
        candidate = copy.deepcopy(state)
        for mon in candidate['creatures']: self.normalize_mon(mon)
        adventure = candidate.setdefault('adventure', {})
        old = adventure.get('varietyDex', {})
        clean = {'seen': {}, 'caught': {}}
        for kind in clean:
            rows = old.get(kind, {}) if isinstance(old, dict) else {}
            if not isinstance(rows, dict): continue
            for species, values in rows.items():
                if species not in self.c.species or not isinstance(values, list): continue
                valid = [v for v in VARIETIES if v in values]
                if valid: clean[kind][species] = valid
        for species, values in clean['caught'].items():
            clean['seen'][species] = [v for v in VARIETIES if v in values or v in clean['seen'].get(species, [])]
        adventure['varietyDex'] = clean
        self.observe(candidate, candidate['creatures'], caught=True)
        return candidate

    def observe(self, state, mons, *, caught=False):
        """Detached state only; caller commits before any owner-facing success."""
        dex = state.setdefault('adventure', {}).setdefault('varietyDex', {'seen': {}, 'caught': {}})
        for mon in mons:
            species = mon.get('species')
            if species not in self.c.species: continue
            value = variety_key(mon)
            for kind in ('seen', 'caught') if caught else ('seen',):
                rows = dex.setdefault(kind, {}); values = rows.setdefault(species, [])
                if value not in values:
                    values.append(value); values.sort(key=VARIETIES.index)
