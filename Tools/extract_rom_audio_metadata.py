#!/usr/bin/env python3
"""Extract exact map music and native cry samples from the two supported ROMs.

This optional content-authoring tool uses only Python's standard library. Neither
the client nor BUILD_ALL.bat needs a ROM. Offsets are bound to whole-ROM SHA-256
values, then cross-checked against active pointers and sample header structures.
No replacement cries are synthesized: source aliases and invalid samples are
reported explicitly. Output WAV files preserve decoded signed 8-bit PCM values
in a signed 16-bit container at the source sample rate.

Format references (implementation below is independent):
https://github.com/pret/pokefirered/blob/master/include/global.fieldmap.h
https://github.com/pret/pokefirered/blob/master/src/m4a_1.s
https://github.com/pret/pokefirered/blob/master/src/pokemon.c
https://github.com/pret/pokefirered/blob/master/asm/macros/music_voice.inc
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import struct
import sys
import wave
from pathlib import Path

PROFILES = {
    'kanto': {
        'sha256': '729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059',
        'mapTableRef': 0x55260,
        'cryTable': 0x48C974,
        'cryTableRef': 0x72128,
        'cryIndexTable': 0x253A44,
        'cryIndexTableRef': 0x4333C,
        'cryIndexFunction': 0x43318,
        'deltaTable': 0x489A58,
    },
    'johto': {
        'sha256': '62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64',
        'mapTableRef': 0x5524C,
        'cryTable': 0x48C914,
        'cryTableRef': 0x72114,
        'cryIndexTable': 0xAA3D74,
        'cryIndexTableRef': 0x43328,
        'cryIndexFunction': 0x43304,
        'deltaTable': 0x4899F8,
    },
}
CRY_COUNT = 388
DELTA_VALUES = (0, 1, 4, 9, 16, 25, 36, 49, -64, -49, -36, -25, -16, -9, -4, -1)


class AudioSourceError(ValueError):
    """The supplied bytes do not satisfy the verified extraction contract."""


class AudioROM:
    def __init__(self, path: Path, source: str):
        self.data = Path(path).read_bytes()
        self.source = source
        self.profile = PROFILES[source]
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        if self.sha256 != self.profile['sha256']:
            raise AudioSourceError(f'{source}: ROM hash differs from the supported source; refusing guessed offsets')
        for pointer, target in [('cryTableRef', 'cryTable'), ('cryIndexTableRef', 'cryIndexTable')]:
            if self.pointer(self.profile[pointer]) != self.profile[target]:
                raise AudioSourceError(f'{source}: active {pointer} has changed')
        expected_delta = bytes(value & 255 for value in DELTA_VALUES)
        if self.read(self.profile['deltaTable'], 16) != expected_delta:
            raise AudioSourceError(f'{source}: delta decoder table differs')

    def read(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise AudioSourceError(f'{self.source}: range {offset:#x}+{size} exceeds ROM')
        return self.data[offset:offset + size]

    def u16(self, offset: int) -> int:
        return struct.unpack('<H', self.read(offset, 2))[0]

    def u32(self, offset: int) -> int:
        return struct.unpack('<I', self.read(offset, 4))[0]

    def pointer(self, offset: int) -> int:
        value = self.u32(offset) - 0x08000000
        self.read(value, 1)
        return value

    def cry_index(self, species: int) -> int:
        """Mirror the active ROM's SpeciesToCryId, including Sigma's aliases."""
        if not 1 <= species <= (411 if self.source == 'kanto' else 971):
            raise AudioSourceError(f'{self.source}: unsupported species ID {species}')
        if species <= 251:
            return species - 1
        if species <= 276:
            return 200  # The original engine's old-Unown slots.
        return self.u16(self.profile['cryIndexTable'] + (species - 277) * 2)

    def map_music(self, key: str, record: dict) -> dict:
        bank_table = self.pointer(self.profile['mapTableRef'])
        bank = self.pointer(bank_table + record['bank'] * 4)
        header = self.pointer(bank + record['map'] * 4)
        if header != int(record['sourceHeader'], 16):
            raise AudioSourceError(f'{key}: active ROM map header differs from existing content')
        song = self.u16(header + 16)
        return {'source': self.source, 'songId': song, 'header': hex(header),
                'name': record['name'],
                'mode': 'inherit' if song == 65535 else 'silence' if song == 0 else 'song'}

    def cry_sample(self, cry_id: int, reverse: bool = False) -> tuple[dict, bytes]:
        if not 0 <= cry_id < CRY_COUNT:
            raise AudioSourceError(f'{self.source}: cry ID {cry_id} exceeds validated normal table')
        tone = self.profile['cryTable'] + (cry_id + (CRY_COUNT if reverse else 0)) * 12
        descriptor = self.read(tone, 12)
        expected_prefix = bytes((0x30 if reverse else 0x20, 60, 0, 0))
        if descriptor[:4] != expected_prefix or descriptor[8:] != b'\xff\x00\xff\x00':
            raise AudioSourceError(f'{self.source}: unsupported cry tone at {tone:#x}')
        sample = self.pointer(tone + 4)
        kind, status, frequency, loop_start, count = struct.unpack('<HHIII', self.read(sample, 16))
        if kind not in (0, 1) or status != 0 or loop_start != 0:
            raise AudioSourceError(f'{self.source}: invalid or looping cry sample at {sample:#x}')
        rate = frequency / 1024
        if not 4000 <= rate <= 48000 or rate != int(rate) or not 32 <= count <= rate * 8:
            raise AudioSourceError(f'{self.source}: invalid cry sample size/frequency at {sample:#x}')
        if kind == 0:
            packed_count = count
            decoded = self.read(sample + 16, count)
        else:
            blocks, remainder = divmod(count, 64)
            packed_count = blocks * 33 + (1 + math.ceil(remainder / 2) if remainder else 0)
            packed = self.read(sample + 16, packed_count)
            decoded = decode_dpcm(packed, count)
        if reverse:
            decoded = decoded[::-1]
        metadata = {
            'source': self.source, 'cryId': cry_id, 'toneOffset': hex(tone),
            'reverse': reverse,
            'sampleOffset': hex(sample), 'sampleType': kind, 'sampleRate': int(rate),
            'samples': count, 'duration': count / rate,
            'romSampleSha256': hashlib.sha256(self.read(sample, 16 + packed_count)).hexdigest(),
            'decodedPcmSha256': hashlib.sha256(decoded).hexdigest(),
            'normalPitch': 60, 'normalAdsr': [255, 0, 255, 0],
        }
        return metadata, decoded


def decode_dpcm(packed: bytes, count: int) -> bytes:
    """Decode MP2K's 64-sample/33-byte delta blocks with signed 8-bit wrap.

    Each block begins with its absolute sample. The next byte's high nibble is
    unused. Consume its low nibble, then subsequent bytes high nibble first.
    A short final block needs only the bytes for its actual sample count.
    """
    if count < 0:
        raise AudioSourceError('Negative PCM sample count')
    result = bytearray()
    offset = 0
    while len(result) < count:
        amount = min(64, count - len(result))
        needed = 1 + math.ceil(amount / 2)
        block = packed[offset:offset + needed]
        if len(block) < needed:
            raise AudioSourceError('Truncated delta PCM block')
        value = block[0]
        result.append(value)
        for position in range(1, amount):
            byte = block[position // 2 + 1]
            nibble = byte & 15 if position & 1 else byte >> 4
            value = (value + DELTA_VALUES[nibble]) & 255
            result.append(value)
        offset += needed
    return bytes(result)


def write_wav(path: Path, decoded: bytes, rate: int) -> None:
    samples = array.array('h', ((value if value < 128 else value - 256) * 256 for value in decoded))
    if sys.byteorder != 'little':
        samples.byteswap()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(samples.tobytes())


def extract(firered: Path, sigma: Path, world_file: Path, out: Path) -> dict:
    roms = {'kanto': AudioROM(firered, 'kanto'), 'johto': AudioROM(sigma, 'johto')}
    world = json.loads(world_file.read_text(encoding='utf-8'))
    report = {'format': 1, 'sources': {}, 'maps': {}, 'crySamples': {}, 'cries': {}, 'reverseCries': {},
              'sourceAliases': [], 'unavailableSamples': []}
    out.mkdir(parents=True, exist_ok=True)
    for source, rom in roms.items():
        report['sources'][source] = {'sha256': rom.sha256, 'bytes': len(rom.data),
                                     'offsets': {key: hex(value) for key, value in rom.profile.items() if key != 'sha256'}}
        for reverse in (False, True):
            bank = 'cry_reverse' if reverse else 'cry'
            for cry_id in range(CRY_COUNT):
                try:
                    metadata, decoded = rom.cry_sample(cry_id, reverse)
                except AudioSourceError as error:
                    report['unavailableSamples'].append({'source': source, 'cryId': cry_id,
                                                         'reverse': reverse, 'reason': str(error)})
                    continue
                relative = Path('cries') / source / f'{bank}_{cry_id:03d}.wav'
                write_wav(out / relative, decoded, metadata['sampleRate'])
                metadata['path'] = relative.as_posix()
                metadata['wavSha256'] = hashlib.sha256((out / relative).read_bytes()).hexdigest()
                report['crySamples'][f'{source}.{bank}.{cry_id}'] = metadata
    for key, record in world['maps'].items():
        source = key.split('_', 1)[0]
        report['maps'][key] = roms[source].map_music(key, record)
    for key, species in world['species'].items():
        source, species_id = species['source'], species['sourceId']
        cry_id = roms[source].cry_index(species_id)
        clip = f'{source}.cry.{cry_id}'
        if clip not in report['crySamples']:
            raise AudioSourceError(f'{key}: current catalog refers to an unavailable cry ({clip})')
        report['cries'][key] = clip
        reverse_clip = f'{source}.cry_reverse.{cry_id}'
        if reverse_clip not in report['crySamples']:
            raise AudioSourceError(f'{key}: current catalog refers to an unavailable reverse cry ({reverse_clip})')
        report['reverseCries'][key] = reverse_clip
        if source == 'johto' and (252 <= species_id <= 276 or species_id > 411):
            report['sourceAliases'].append({'species': key, 'name': species['name'], 'cryId': cry_id,
                                           'reason': 'Native ROM SpeciesToCryId mapping; not an extraction fallback'})
    report['counts'] = {'maps': len(report['maps']), 'species': len(report['cries']),
                        'crySamples': len(report['crySamples']),
                        'normalCrySamples': sum(not value['reverse'] for value in report['crySamples'].values()),
                        'reverseCrySamples': sum(value['reverse'] for value in report['crySamples'].values()),
                        'sourceAliases': len(report['sourceAliases']),
                        'unavailableUnusedSamples': len(report['unavailableSamples'])}
    (out / 'audio_metadata.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firered', type=Path, required=True)
    parser.add_argument('--sigma', type=Path, required=True)
    parser.add_argument('--world', type=Path, default=Path(__file__).resolve().parents[1] / 'Server/data/world.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = extract(args.firered, args.sigma, args.world, args.out)
    print(json.dumps(report['counts'], indent=2))


if __name__ == '__main__':
    main()
