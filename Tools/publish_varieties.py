"""Validate local variety fronts and bind stable identities before pack hashing.

Normal builds require no Pillow, original archive, ROM or network download.
"""
from __future__ import annotations
import copy, hashlib, json, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The publisher uses exactly the same policy validation as the live server.
if str(ROOT/'Server') not in sys.path: sys.path.insert(0,str(ROOT/'Server'))
from nxt.varieties import VARIETIES, validate_policy

def assemble(world, root=ROOT):
    root = Path(root); assets = (root/'Client/app/assets').resolve()
    source = root/'Server/data/varieties.json'
    manifest = json.loads(source.read_text(encoding='utf-8'))
    policy = {key:copy.deepcopy(manifest[key]) for key in ('format','order','definitions','rollDenominator')}
    validate_policy(policy)
    if set(manifest.get('species', {})) != set(world['species']):
        raise ValueError('Every catalog identity must have an explicit variety asset decision')
    counts = {v:0 for v in VARIETIES}; audit = {}; uploaded = 0
    for key, profile in world['species'].items():
        rows = manifest['species'][key]
        if not isinstance(rows, dict) or set(rows)-set(VARIETIES[1:]):
            raise ValueError('Invalid variety asset row: '+key)
        bindings = {'normal':{'front':profile['front'],'source':'native'},
                    'shiny':{'front':profile['shiny'],'source':'native'}}
        for variety, record in rows.items():
            expected = f'pokemon/varieties/{variety}/{key}.png'
            if not isinstance(record,dict) or record.get('front') != expected:
                raise ValueError('Unsafe or cross-species variety asset: '+key+'/'+variety)
            path = assets/expected
            if path.is_symlink() or not path.resolve().is_relative_to(assets) or not path.is_file():
                raise ValueError('Missing or unsafe variety image: '+expected)
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=record.get('sha256'):
                raise ValueError('Variety image checksum mismatch: '+expected)
            if len(raw)<24 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR':
                raise ValueError('Invalid PNG header: '+expected)
            width,height=struct.unpack('>II',raw[16:24])
            if width!=record.get('width') or height!=record.get('height') or not all(1<=n<=512 for n in (width,height)):
                raise ValueError('Invalid variety dimensions: '+expected)
            bindings[variety]={'front':expected,'source':'uploaded'};uploaded+=1
        profile['varieties']=bindings
        for variety in bindings:counts[variety]+=1
        audit[key]={'name':profile['name'],'available':list(v for v in VARIETIES if v in bindings),
                    'missingSuppliedArt':[v for v in VARIETIES[1:] if v not in rows],
                    'nativeShinyFallback':'shiny' not in rows,
                    'uploaded':copy.deepcopy(rows)}
    core=[f'fr_{i}' for i in range(1,252)]
    for key in core:
        if key not in world['species'] or set(world['species'][key]['varieties'])!=set(VARIETIES):
            raise ValueError('Incomplete Kanto/Johto variety coverage: '+key)
    policy['assetManifestSha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    policy['coverage']={'species':len(world['species']),'fullyCoveredSpecies':sum(set(p['varieties'])==set(VARIETIES) for p in world['species'].values()),
        'kantoJohtoSpecies':251,'uploadedFronts':uploaded,'availableCounts':counts}
    world['varietyPolicy']=policy;world['version']='0.6.5-alpha'
    report={'format':1,'policy':policy,'sourceArchiveSha256':manifest.get('sourceArchiveSha256'),
        'sourceImportProblems':manifest.get('importProblems',[]),'species':audit,
        'presentation':'Every player-side battle sprite uses a horizontally flipped FRONT; followers retain normal native icons.',
        'missingArtPolicy':'Do not roll unavailable art. Preserve inherited/saved identities; use normal art with an explicit summary notice if no variety front exists.',
        'rarityReference':'NXT-specific 90% Normal, 2.5% Ancient/Metallic/Mystic each and 1.25% Shiny/Shadow each; Vortex-inspired tiers, not claimed exact Vortex odds.'}
    (root/'Docs/POKEMON_VARIETY_ASSET_AUDIT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return policy
