#!/usr/bin/env python3
"""Import supplied FRONT images once; normal builds use the shipped PNGs and manifest.

Usage: python Tools/import_variety_assets.py --fronts /path/to/extracted/pokemon
Requires Pillow only for this authoring operation. No downloads, colour invention,
back sprites, species creation or fuzzy runtime name matching are performed.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORDER = ('normal', 'ancient', 'metallic', 'shiny', 'mystic', 'shadow')
DEFINITIONS = {
    'normal': {'label': 'Normal', 'weight': 9000, 'color': '#BDCAD8'},
    'ancient': {'label': 'Ancient', 'weight': 250, 'color': '#FFAA55'},
    'metallic': {'label': 'Metallic', 'weight': 250, 'color': '#91DCEC'},
    'shiny': {'label': 'Shiny', 'weight': 125, 'color': '#FFF07A'},
    'mystic': {'label': 'Mystic', 'weight': 250, 'color': '#C49AFF'},
    'shadow': {'label': 'Shadow', 'weight': 125, 'color': '#F879B3'},
}
# Explicit identities, never guesses from a substring or a National Dex number
# treated as a Sigma internal ID. The original saved species IDs remain intact.
ALIASES = {
    'fr_29': ['Nidoran (F)'], 'fr_32': ['Nidoran (M)'],
    'fr_180': ['Flaaffy', 'Flaffy'], 'fr_201': ['Unown (A)', 'Unown'],
    'sg_255': ['Kangaskhan (Mega)'], 'sg_256': ['Charizard (Mega X)'],
    'sg_265': ['Salamence (Mega)'], 'sg_266': ['Charizard (Mega Y)'],
    'sg_276': ['Aerodactyl (Mega)'], 'sg_889': ['Manectric (Mega)'],
    'sg_885': ['Mewtwo (Mega X)'], 'sg_886': ['Mewtwo (Mega Y)'],
    'sg_469': ['Vespiquen'], 'sg_475': ['Shellos (East)'],
    'sg_476': ['Gastrodon (East)'], 'sg_547': ['Victini'],
    'sg_599': ['Cottonee'], 'sg_701': ['Meloetta (Aria)'],
    'sg_715': ['Fletchinder'], 'sg_731': ['Meowstic (Male)', 'Meowstic (M)'],
    'sg_769': ['Xerneas (Active)'], 'sg_773': ['Hoopa (Unbound)'],
}
# Older Ancient filenames use explicit default forms where the newer set has
# both an unqualified name and a qualified copy.
ANCIENT_DEFAULTS = {
    'sg_465': ['Burmy (Plant)'], 'sg_466': ['Wormadam (Plant)'],
    'sg_474': ['Cherrim (Overcast)'], 'sg_603': ['Basculin (Red Stripe)'],
    'sg_638': ['Deerling (Spring)'], 'sg_639': ['Sawsbuck (Spring)'],
}

def normalize(value: str) -> str:
    value = value.replace('♀', '(F)').replace('♂', '(M)')
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value).casefold())

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    from PIL import Image
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fronts', required=True, type=Path)
    parser.add_argument('--root', default=ROOT, type=Path)
    parser.add_argument('--archive-sha256', default='')
    args = parser.parse_args(); root = args.root.resolve()
    world = json.loads((root/'Server/data/world.json').read_text(encoding='utf-8'))
    index = collections.defaultdict(list)
    for path in sorted(args.fronts.glob('*.gif')):
        index[normalize(path.stem)].append(path)
    entries = {}; problems = []; counts = collections.Counter(); frames_total = 0
    for key, sp in world['species'].items():
        entries[key] = {}
        for variety in ORDER[1:]:
            names = ALIASES.get(key, [sp['name']])
            if variety == 'ancient' and key in ANCIENT_DEFAULTS:
                names = [*names, *ANCIENT_DEFAULTS[key]]
            source = None
            for name in names:
                candidates = index.get(normalize(variety+' '+name), [])
                if len(candidates)>1:
                    exact = [p for p in candidates if p.stem.casefold()==(variety+' '+name).casefold()]
                    candidates = exact or candidates
                if len(candidates)>1: raise ValueError('Ambiguous asset: '+key+' / '+variety)
                if candidates: source=candidates[0];break
            if source is None: continue
            relative = f'pokemon/varieties/{variety}/{key}.png'
            target = root/'Client/app/assets'/relative; target.parent.mkdir(parents=True,exist_ok=True)
            try:
                with Image.open(source) as image:
                    if image.format not in ('GIF', 'PNG') or not all(1<=n<=512 for n in image.size) or image.n_frames>120:
                        raise ValueError('Unexpected image format, dimensions or frame count')
                    frames=[]; durations=[]; source_size=image.size
                    for i in range(image.n_frames):
                        image.seek(i); frame=image.convert('RGBA')
                        if not frame.getchannel('A').getbbox(): raise ValueError('Empty sprite frame')
                        frames.append(frame.copy()); durations.append(max(40,int(image.info.get('duration',100))))
                    boxes=[f.getchannel('A').getbbox() for f in frames]
                    box=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
                    with Image.open(root/'Client/app/assets'/sp['front']) as native:
                        edge=max(*native.size,box[2]-box[0]+4,box[3]-box[1]+4)
                    offset=((edge-(box[2]-box[0]))//2,(edge-(box[3]-box[1]))//2)
                    normalized=[]
                    for frame in frames:
                        canvas=Image.new('RGBA',(edge,edge),(0,0,0,0));canvas.paste(frame.crop(box),offset);normalized.append(canvas)
                    frames=normalized
                    if len(frames)==1: frames[0].save(target,format='PNG',optimize=True)
                    else: frames[0].save(target,format='PNG',save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=0,blend=0)
                    entries[key][variety]={'front':relative,'sourceFile':'pokemon/'+source.name,
                        'sourceSha256':digest(source),'sha256':digest(target),
                        'width':frames[0].width,'height':frames[0].height,'frames':len(frames),'sourceWidth':source_size[0],'sourceHeight':source_size[1],'sourceCropBox':list(box),'pixelOffset':list(offset),'canvasNormalization':'Transparent padding only; no resampling or recolouring'}
                    counts[variety]+=1;frames_total+=len(frames)
            except Exception as error:
                target.unlink(missing_ok=True);problems.append({'species':key,'variety':variety,'file':source.name,'error':str(error)})
    # Every Gen I/II identity is an explicit acceptance gate, not an assumed count.
    missing_core = [(f'fr_{i}',v) for i in range(1,252) for v in ORDER[1:] if v not in entries.get(f'fr_{i}',{})]
    if missing_core: raise ValueError('Incomplete Kanto/Johto front coverage: '+repr(missing_core))
    manifest={'format':1,'rollDenominator':10000,'order':list(ORDER),'definitions':DEFINITIONS,
        'sourceArchiveSha256':args.archive_sha256,'species':entries,
        'coverage':{'catalogSpecies':len(entries),'kantoJohtoSpecies':251,'kantoJohtoUploadedFronts':1255,
                    'uploadedFronts':sum(counts.values()),'uploadedCounts':dict(counts),'totalFrames':frames_total},
        'importProblems':problems}
    (root/'Server/data/varieties.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest['coverage'],indent=2));print('Rejected source images:',len(problems))

if __name__=='__main__':main()
