#!/usr/bin/env python3
"""Assemble verified native exports into the bundled client audio catalog.

Optional authoring step after extract_rom_audio_metadata.py,
extract_rom_move_audio.py and native_audio/extract_music.py. Normal builds use the
already assembled assets and run verify_audio.py; they never need ROM inputs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
# Semantic MMO cues select original ROM song IDs. Area music and move effects
# are imported independently from the actual map headers/animation scripts.
CUES = {
    'title': 278, 'surf': 305, 'battle_wild': 298, 'battle_trainer': 297,
    'victory_wild': 311, 'victory_trainer': 310, 'victory': 310,
    'victory_caught': 322, 'defeat': 271,
    'ui_select': 5, 'ui_open': 6, 'ui_cancel': 5, 'ui_error': 252,
    'ui_chat': 66, 'ui_invite': 66, 'ui_dialog': 6, 'ui_warp': 39,
    'select': 5, 'open': 6, 'cancel': 5, 'error': 252, 'chat': 66,
    'invite': 66, 'dialog': 6, 'warp': 39, 'bump': 7, 'ledge': 10,
    'sendout': 15, 'shiny': 95, 'miss': 26, 'no_effect': 12,
    'protected': 12, 'hit': 13, 'hit_super': 14, 'hit_weak': 12,
    'hit_immune': 12, 'critical': 14, 'recover': 1, 'damage': 13,
    'stat_up': 232, 'stat_down': 238, 'status': 72, 'status_clear': 1,
    'faint': 16, 'capture_throw': 54, 'capture_success': 247,
    'capture_fail': 15, 'escape': 17, 'experience': 27, 'level_up': 257,
    'abort': 252, 'purchase': 248, 'party_changed': 29, 'heal': 256,
    'item': 1, 'save': 48, 'trade_complete': 25, 'low_hp': 83,
}
FANFARES = {256, 257, 258, 259, 260, 261, 262, 271, 318}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def song_key(source, song):
    return f'{source}.song.{song}'


def assemble(root, metadata_dir, render_dir):
    metadata = json.loads((metadata_dir / 'audio_metadata.json').read_text())
    moves = json.loads((metadata_dir / 'move_audio.json').read_text())
    rendered = json.loads((render_dir / 'render_manifest.json').read_text())
    world = json.loads((root / 'Server/data/world.json').read_text())
    assets = root / 'Client/app/assets'
    catalog = {'format': 1, 'version': '1.2.0', 'sources': metadata['sources'], 'clips': {},
               'mapMusic': {}, 'mapModes': {}, 'cries': metadata['cries'],
               'reverseCries': metadata['reverseCries'], 'cues': {}, 'moveSounds': {}}
    for key, entry in sorted(rendered['songs'].items()):
        if not entry.get('ok') or entry.get('capped'):
            raise ValueError('Unfinished native audio render: ' + key)
        source, song = key.split(':'); song = int(song)
        relative = f'audio/songs/{source}/{song:04d}.ogg'
        src, target = render_dir / entry['file'], assets / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        clip = {'path': relative, 'source': source, 'songId': song,
                'kind': 'music' if song >= 256 else 'effect',
                'duration': entry['duration'], 'sha256': entry['sha256'], 'loop': entry['loop']}
        if entry['loop']:
            clip.update(loopStart=entry['loop_start'], loopEnd=entry['loop_end'])
        if song in FANFARES:
            clip['fanfare'] = True
        catalog['clips'][song_key(source, song)] = clip
    expected = sum(s['song_table_slots'] - len(s.get('null_ids', [])) - len(s.get('silence_ids', []))
                   for s in rendered['sources'].values())
    if len(rendered['songs']) != expected:
        raise ValueError(f'Expected {expected} native sequences, got {len(rendered["songs"])}')
    for key, entry in metadata['crySamples'].items():
        relative = 'audio/' + entry['path']
        target = assets / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(metadata_dir / entry['path'], target)
        catalog['clips'][key] = {'path': relative, 'source': entry['source'], 'cryId': entry['cryId'],
                                 'kind': 'cry', 'duration': entry['duration'], 'loop': False,
                                 'reverse': entry['reverse'], 'sha256': entry['wavSha256']}
    for key, entry in metadata['maps'].items():
        catalog['mapModes'][key] = entry['mode']
        catalog['mapMusic'][key] = song_key(entry['source'], entry['songId']) if entry['mode'] == 'song' else None
    for source in ('kanto', 'johto'):
        catalog['cues'][source] = {cue: song_key(source, song) for cue, song in CUES.items()}
        home = world['homes']['Kanto' if source == 'kanto' else 'Johto']
        catalog['cues'][source]['region_default'] = catalog['mapMusic'][home]
        catalog['moveSounds'][source] = {}
        for move, entry in moves['moves'][source].items():
            events = []
            for event in entry['events']:
                row = {'clip': song_key(source, event['songId']), 'delaySeconds': event['delayFrames'] / 60,
                       'pan': event.get('pan', 0), 'repeat': max(1, event.get('repeat', 1)),
                       'intervalSeconds': event.get('intervalFrames', 0) / 60}
                events.append(row)
            # The metadata importer decodes native cry callbacks into bounded
            # playback parameters. Keep raw tasks in the provenance report.
            cries = entry.get('cryPlayback', [])
            if entry['cries'] and not cries:
                raise ValueError('Missing decoded cry callback parameters: ' + source + ':' + move)
            catalog['moveSounds'][source][move] = {'events': events, 'cries': cries,
                'reachableClips': [song_key(source, n) for n in entry['reachableSongIds']],
                'timing': entry['timing']}
    write_json(assets / 'audio/catalog.json', catalog)
    report = {'format': 1, 'nativeRenderer': 'agbplay MP2K core', 'sequenceCount': len(rendered['songs']),
              'crySampleCount': len(metadata['crySamples']), 'mapCount': len(metadata['maps']),
              'speciesCryBindings': len(metadata['cries']), 'moveBindings': sum(len(v) for v in catalog['moveSounds'].values()),
              'sourceAliases': metadata['sourceAliases'], 'unavailableUnusedCrySamples': metadata['unavailableSamples'],
              'sampleRecoveries': rendered.get('sample_recoveries', []),
              'sequenceRecoveries': rendered.get('sequence_recoveries', []),
              'sources': metadata['sources'],
              'timingLimit': 'Move script delays are preserved; visual callback completion is not emulated by the MMO.'}
    write_json(root / 'Docs/AUDIO_ASSET_REPORT.json', report)
    # These reports permit tracing every clip to ROM pointers and decoded bytes
    # without distributing either source ROM or temporary repair copies.
    provenance = root / 'Tools/audio_provenance'
    write_json(provenance / 'audio_metadata.json', metadata)
    write_json(provenance / 'move_audio.json', moves)
    write_json(provenance / 'render_manifest.json', rendered)
    from verify_audio import verify
    print(json.dumps(verify(root), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--metadata-dir', required=True, type=Path)
    parser.add_argument('--render-dir', required=True, type=Path)
    args = parser.parse_args()
    assemble(args.root.resolve(), args.metadata_dir.resolve(), args.render_dir.resolve())


if __name__ == '__main__':
    main()
