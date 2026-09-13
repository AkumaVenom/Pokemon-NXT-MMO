#!/usr/bin/env python3
"""Verify the bundled ROM audio without ROMs, FFmpeg or third-party packages."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import struct
import wave

ROOT = Path(__file__).resolve().parents[1]


def _require(condition, message):
    if not condition:
        raise ValueError("Audio validation failed: " + message)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _ogg_duration(path):
    """Read Ogg page framing, Vorbis identification and final PCM position."""
    sample_rate = channels = granule = None
    with path.open('rb') as stream:
        while True:
            header = stream.read(27)
            if not header:
                break
            _require(len(header) == 27 and header[:5] == b'OggS\0', f"invalid Ogg page: {path.name}")
            segments = stream.read(header[26])
            _require(len(segments) == header[26], f"truncated Ogg lacing: {path.name}")
            payload = stream.read(sum(segments))
            _require(len(payload) == sum(segments), f"truncated Ogg payload: {path.name}")
            if sample_rate is None:
                _require(payload[:7] == b'\x01vorbis' and len(payload) >= 30, f"not Vorbis: {path.name}")
                channels = payload[11]
                sample_rate = struct.unpack_from('<I', payload, 12)[0]
            position = struct.unpack_from('<Q', header, 6)[0]
            if position != 0xffffffffffffffff:
                granule = position
    _require(sample_rate == 44100 and channels == 2 and granule and granule > 0,
             f"invalid music/effect format: {path.name}")
    return granule / sample_rate


def verify(root: Path = ROOT, *, world: dict | None = None) -> dict:
    root = Path(root).resolve()
    assets = root / 'Client/app/assets'
    catalog_path = assets / 'audio/catalog.json'
    _require(catalog_path.is_file(), 'audio/catalog.json is missing; extract the entire source ZIP.')
    raw = catalog_path.read_bytes()
    catalog = json.loads(raw)
    _require(catalog.get('format') == 1, 'unsupported catalog format')
    clips = catalog.get('clips')
    _require(isinstance(clips, dict) and clips, 'no audio clips')
    paths = set()
    for key, clip in clips.items():
        relative = PurePosixPath(clip.get('path', ''))
        _require(not relative.is_absolute() and '..' not in relative.parts and relative.parts[:1] == ('audio',)
                 and '\\' not in str(relative), f'unsafe clip path: {key}')
        path = assets.joinpath(*relative.parts)
        _require(path.resolve().is_relative_to((assets / 'audio').resolve()) and path.is_file() and not path.is_symlink(), f'missing/unsafe clip: {key}')
        _require(str(relative) not in paths, f'duplicate clip path: {key}')
        paths.add(str(relative))
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        _require(digest == clip.get('sha256'), f'checksum mismatch: {relative}; restore this file from the source ZIP')
        _require(clip.get('kind') in ('music', 'effect', 'cry'), f'invalid clip kind: {key}')
        _require(_number(clip.get('duration')) and clip['duration'] > 0, f'invalid duration: {key}')
        _require(isinstance(clip.get('loop'), bool), f'missing explicit loop flag: {key}')
        if path.suffix == '.ogg':
            actual_duration = _ogg_duration(path)
        else:
            _require(path.suffix == '.wav' and clip['kind'] == 'cry', f'unsupported audio container: {key}')
            with wave.open(str(path), 'rb') as wav:
                _require(wav.getcomptype() == 'NONE' and wav.getnchannels() == 1 and wav.getsampwidth() == 2
                         and wav.getframerate() == 10512 and wav.getnframes() > 0, f'invalid cry PCM format: {key}')
                actual_duration = wav.getnframes() / wav.getframerate()
                _require(len(wav.readframes(wav.getnframes())) == wav.getnframes() * 2, f'truncated cry: {key}')
        _require(abs(actual_duration - clip['duration']) < .003, f'duration differs from encoded audio: {key}')
        if clip['loop']:
            start, end = clip.get('loopStart'), clip.get('loopEnd')
            _require(_number(start) and _number(end) and 0 <= start < end <= actual_duration + .001,
                     f'invalid loop bounds: {key}')

    def reference(key, where, nullable=False):
        _require((nullable and key is None) or (isinstance(key, str) and key in clips), f'missing clip reference in {where}: {key}')

    if world is None:
        world = json.loads((root / 'Server/data/world.json').read_text(encoding='utf-8'))
    _require(set(catalog.get('mapMusic', {})) == set(world['maps']), 'map music coverage differs from world maps')
    _require(set(catalog.get('mapModes', {})) == set(world['maps']), 'map music modes differ from world maps')
    for key, clip_id in catalog['mapMusic'].items():
        mode = catalog['mapModes'][key]
        _require(mode in ('song', 'inherit', 'silence'), 'invalid map music mode: ' + key)
        reference(clip_id, 'map ' + key, nullable=mode != 'song')
        _require(mode == 'song' or clip_id is None, 'non-song map must use a null clip: ' + key)
    for bank in ('cries', 'reverseCries'):
        _require(set(catalog.get(bank, {})) == set(world['species']), bank + ' coverage differs from species catalog')
        for species, clip_id in catalog[bank].items():
            reference(clip_id, bank + ' ' + species)
            _require(clips[clip_id]['kind'] == 'cry', 'species references a non-cry clip: ' + species)
    required_cues = {'title', 'region_default', 'surf', 'battle_wild', 'battle_trainer', 'victory_wild',
                     'victory_trainer', 'victory_caught', 'defeat', 'ui_select', 'ui_error', 'sendout',
                     'hit', 'faint', 'capture_throw', 'capture_success', 'heal', 'level_up', 'low_hp'}
    for source in ('kanto', 'johto'):
        cues = catalog.get('cues', {}).get(source, {})
        _require(required_cues <= set(cues), 'missing gameplay cues for ' + source)
        for cue, clip_id in cues.items():
            reference(clip_id, source + ' cue ' + cue)
        moves = catalog.get('moveSounds', {}).get(source, {})
        _require(set(moves) == set(world['moves']), 'move sound coverage differs from move catalog for ' + source)
        for move, record in moves.items():
            for event in record.get('events', []):
                reference(event.get('clip'), source + ' move ' + move)
                _require(_number(event.get('delaySeconds')) and 0 <= event['delaySeconds'] <= 120,
                         'invalid move sound timing: ' + move)
                _require(isinstance(event.get('repeat', 1), int) and 1 <= event.get('repeat', 1) <= 255,
                         'invalid move sound repeat: ' + move)
            for clip_id in record.get('reachableClips', []):
                reference(clip_id, source + ' move alternatives ' + move)
    return {'format': 1, 'catalogSha256': hashlib.sha256(raw).hexdigest(), 'clipCount': len(clips),
            'mapCount': len(catalog['mapMusic']), 'speciesCryCount': len(catalog['cries']),
            'sourceHashes': {s: catalog['sources'][s]['sha256'] for s in ('kanto', 'johto')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root), indent=2))
    except (ValueError, OSError, KeyError, wave.Error, struct.error) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
