#!/usr/bin/env python3
"""Read the supported ROMs' Gen III move-animation sound references.

Pointers and SFX arguments come from each exact supplied ROM, including calls and
conditional branches. A deterministic single-turn presentation path is exported
separately from reachable alternatives. Explicit script delays are preserved;
asynchronous visual-task completion time is intentionally reported as unknown.
The MMO does not emulate the original battle-animation renderer.

Opcode/task format references:
https://github.com/pret/pokefirered/blob/master/asm/macros/battle_anim_script.inc
https://github.com/pret/pokefirered/blob/master/data/battle_anim_scripts.s
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from extract_rom_audio_metadata import AudioROM, AudioSourceError

TABLES = {'kanto': 0x1C6964, 'johto': 0x1C68F4}
# These native function pointers were matched against each command in the
# reference script assembly, then checked at the corresponding ROM command.
TASKS_FR = {
    0x080DCE25: 'FireBlast',
    0x080DD459: 'AdjustPanningVar',
    0x080DD425: 'PlaySE2WithPanning',
    0x080DD3F1: 'PlaySE1WithPanning',
    0x080DD081: 'PlayCryHighPitch',
    0x080DD15D: 'PlayDoubleCry',
    0x080DD309: 'WaitForCry',
    0x080DCF4D: 'LoopSEAdjustPanning',
    0x080DD349: 'PlayCryWithEcho',
}
LENGTHS = (3, 3, None, None, 2, 1, 1, 1, 1, 3, 2, 2, 3, 1, 5, 1,
           4, 9, 6, 5, 2, 1, 1, 1, 2, 4, 2, 7, 6, 5, 3, None,
           1, 8, 2, 2, 5, 4, 7, 7, 2, 1, 2, 2, 2, 2, 2, 1)
SOUND_COMMANDS = {9, 25, 27, 28, 29, 38, 39}
# Sprite callbacks which produce all audio for these three moves. Each SFX
# immediate and following Thumb BL are verified in both supported source ROMs.
SPRITE_SOUNDS_FR = {
    0x083E36CC: {'name': 'SharpenSphere', 'songId': 187, 'callOffset': 0xA5C2C,
                 'callbackDelayFrames': 10, 'timing': 'First flash sound; later flashes follow sprite state'},
    0x083E3588: {'name': 'LockOnTarget', 'songId': 203, 'callOffset': 0xA5078,
                 'callbackDelayFrames': 20, 'timing': 'Target animation controls subsequent sound timing'},
    0x083E3E04: {'name': 'BulletSeed', 'songId': 159, 'callOffset': 0xA7C40,
                 'callbackDelayFrames': 20, 'timing': 'Native seed translation duration before impact'},
}
CRY_MODES = {
    3: {'pitch': 15800, 'lengthFrames': 50, 'release': 200, 'reverse': False, 'chorus': 20, 'volume': 90},
    4: {'pitch': 15600, 'lengthFrames': 25, 'release': 100, 'reverse': True, 'chorus': 192, 'volume': 90},
    6: {'pitch': 15555, 'lengthFrames': 140, 'release': 220, 'reverse': False, 'chorus': 192, 'volume': 90},
    7: {'pitch': 14848, 'lengthFrames': 10, 'release': 100, 'reverse': False, 'chorus': 0, 'volume': 120},
    8: {'pitch': 15616, 'lengthFrames': 60, 'release': 225, 'reverse': False, 'chorus': 0, 'volume': 120},
    9: {'pitch': 15200, 'lengthFrames': 15, 'release': 125, 'reverse': True, 'chorus': 0, 'volume': 120},
    10: {'pitch': 15200, 'lengthFrames': 100, 'release': 225, 'reverse': False, 'chorus': 0, 'volume': 120},
}


def normalize_cry_task(row: dict) -> list[dict]:
    """Expose native pitch/envelope parameters to the browser presentation layer.

    The two-part tasks wait for the first cry to finish, rather than starting a
    guessed fixed-time repeat. Consumers should resolve afterPreviousCry using
    the played clip's duration, note-off point and release envelope.
    """
    name, args = row['task'], row.get('args', [])
    if name == 'PlayDoubleCry':
        modes = (9, 10) if len(args) > 1 and args[1] == 255 else (7, 8)
    elif name == 'PlayCryHighPitch':
        modes = (3,)
    elif name == 'PlayCryWithEcho':
        modes = (4, 6)
    else:
        raise AudioSourceError('Unknown cry task for normalization')
    result = []
    for index, mode in enumerate(modes):
        values = CRY_MODES[mode]
        result.append({'delaySeconds': row['delayFrames'] / 60 if index == 0 else 0,
                       'side': 'defender' if args and args[0] in (1, 3) else 'attacker',
                       'reverse': values['reverse'],
                       'playbackRate': 2 ** ((values['pitch'] - 15360) / (256 * 12)),
                       'noteOffSeconds': values['lengthFrames'] / 60,
                       'releaseCoefficient': values['release'] / 256,
                       'gain': values['volume'] / 120,
                       'afterPreviousCry': index > 0,
                       'minimumStartDelaySeconds': 2 / 60 if index > 0 else 0,
                       'sourceMode': mode, 'sourceParameters': values.copy()})
    return result


def signed(value: int) -> int:
    return value - 256 if value > 127 else value


class MoveReader:
    def __init__(self, rom: AudioROM):
        self.rom = rom
        self.table = TABLES[rom.source]
        self.tasks = {address - (20 if rom.source == 'johto' else 0): name
                      for address, name in TASKS_FR.items()}
        self.sprite_sounds = {}
        for template, row in SPRITE_SOUNDS_FR.items():
            code_delta, data_delta = (20, 112) if rom.source == 'johto' else (0, 0)
            call = row['callOffset'] - code_delta
            if rom.read(call, 2) != bytes((row['songId'], 0x20)):
                raise AudioSourceError('Sprite callback SFX immediate differs')
            first, second = rom.u16(call + 2), rom.u16(call + 4)
            if first & 0xF800 != 0xF000 or second & 0xF800 != 0xF800:
                raise AudioSourceError('Sprite callback no longer calls native sound player')
            displacement = ((first & 2047) << 12) | ((second & 2047) << 1)
            if displacement & (1 << 22):
                displacement -= 1 << 23
            if call + 6 + displacement != 0x72308 - code_delta:
                raise AudioSourceError('Sprite callback sound call target differs')
            self.sprite_sounds[template - data_delta] = dict(row, callOffset=hex(call))
        if rom.read(self.table - 8, 8) != bytes.fromhex('2f00c3004001ffff'):
            raise AudioSourceError('Move animation table signature differs')

    def command(self, offset: int) -> tuple[int, bytes]:
        op = self.rom.read(offset, 1)[0]
        if op >= len(LENGTHS):
            raise AudioSourceError(f'Unsupported animation opcode {op} at {offset:#x}')
        size = LENGTHS[op]
        if op in (2, 3):
            size = 7 + 2 * self.rom.read(offset + 6, 1)[0]
        elif op == 31:
            size = 6 + 2 * self.rom.read(offset + 5, 1)[0]
        return op, self.rom.read(offset, size)

    def sound(self, pos: int, op: int, data: bytes, delay: int) -> tuple[list, list]:
        events, cries = [], []
        if op in SOUND_COMMANDS:
            row = {'songId': self.rom.u16(pos + 1), 'delayFrames': delay,
                   'sourceOffset': hex(pos), 'pan': signed(data[3]) if len(data) > 3 else 0}
            if op == 28:
                row.update(repeat=data[5], intervalFrames=data[4])
            elif op == 29:
                row['delayFrames'] += data[4]
            elif op in (27, 38, 39):
                row.update(targetPan=signed(data[4]), panIncrement=signed(data[5]), panDelayFrames=data[6])
            events.append(row)
        elif op == 2:
            callback = self.sprite_sounds.get(self.rom.u32(pos + 1))
            if callback:
                events.append({'songId': callback['songId'],
                               'delayFrames': delay + callback['callbackDelayFrames'],
                               'sourceOffset': hex(pos), 'callback': callback['name'],
                               'soundCallOffset': callback['callOffset'],
                               'callbackTiming': callback['timing'],
                               'pan': -64 if callback['name'] == 'SharpenSphere' else 63})
        elif op in (3, 31):
            pointer = self.rom.u32(pos + 1)
            name = self.tasks.get(pointer)
            first = 7 if op == 3 else 6
            args = [int.from_bytes(data[index:index + 2], 'little') for index in range(first, len(data), 2)]
            if name in ('PlaySE1WithPanning', 'PlaySE2WithPanning', 'LoopSEAdjustPanning', 'FireBlast'):
                sound_ids = args[:2] if name == 'FireBlast' else args[:1]
                for sound_id in sound_ids:
                    row = {'songId': sound_id, 'delayFrames': delay, 'sourceOffset': hex(pos),
                           'task': name, 'taskArgs': args}
                    if name != 'FireBlast' and len(args) > 1:
                        row['pan'] = args[1] - 65536 if args[1] >= 32768 else args[1]
                    if name == 'LoopSEAdjustPanning':
                        row['taskTiming'] = 'Native asynchronous sound task; args preserved'
                    events.append(row)
            elif name in ('PlayCryHighPitch', 'PlayDoubleCry', 'PlayCryWithEcho'):
                row = {'task': name, 'args': args, 'delayFrames': delay, 'sourceOffset': hex(pos)}
                row['playbacks'] = normalize_cry_task(row)
                cries.append(row)
        for event in events:
            if not 1 <= event['songId'] <= 255:
                raise AudioSourceError(f'Unexpected move SFX ID at {pos:#x}')
        return events, cries

    def reachable(self, root: int) -> tuple[list, list]:
        pending, seen, ids, cries = [root], set(), [], []
        while pending:
            pos = pending.pop()
            if pos in seen:
                continue
            seen.add(pos)
            if len(seen) > 20000:
                raise AudioSourceError('Move graph exceeds safety bound')
            op, data = self.command(pos)
            events, cry = self.sound(pos, op, data, 0)
            for row in events:
                if row['songId'] not in ids:
                    ids.append(row['songId'])
            for row in cry:
                if row['task'] not in cries:
                    cries.append(row['task'])
            if op in (8, 15):
                continue
            if op == 19:
                pending.append(self.rom.pointer(pos + 1))
                continue
            if op == 17:
                pending.extend((self.rom.pointer(pos + 1), self.rom.pointer(pos + 5)))
                continue
            pending.append(pos + len(data))
            if op in (14, 36):
                pending.append(self.rom.pointer(pos + 1))
            elif op == 18:
                pending.append(self.rom.pointer(pos + 2))
            elif op == 33:
                pending.append(self.rom.pointer(pos + 4))
        return ids, cries

    def move(self, move_id: int) -> dict:
        root = self.rom.pointer(self.table + move_id * 4)
        ids, cry_types = self.reachable(root)
        pos, elapsed, stack, args = root, 0, [], {}
        events, cries, branches, barriers = [], [], [], []
        visits = {}
        for _ in range(20000):
            visits[pos] = visits.get(pos, 0) + 1
            if visits[pos] > 128:
                raise AudioSourceError(f'Move {move_id}: animation loop exceeds bound')
            op, data = self.command(pos)
            evt, cry = self.sound(pos, op, data, elapsed)
            events.extend(evt)
            cries.extend(cry)
            nxt = pos + len(data)
            if op == 8:
                break
            if op == 4:
                elapsed += data[1]
            elif op in (5, 22, 23, 32):
                barriers.append({'sourceOffset': hex(pos), 'opcode': op, 'afterFrames': elapsed})
            elif op == 14:
                stack.append(nxt)
                nxt = self.rom.pointer(pos + 1)
            elif op == 15:
                if not stack:
                    break
                nxt = stack.pop()
            elif op == 16:
                args[data[1]] = self.rom.u16(pos + 2)
            elif op == 17:
                nxt = self.rom.pointer(pos + 5)
                branches.append({'sourceOffset': hex(pos), 'selection': 'Single-turn MMO uses attack/release branch'})
            elif op == 18:
                if data[1] == 0:
                    nxt = self.rom.pointer(pos + 2)
                branches.append({'sourceOffset': hex(pos), 'selection': 'Move turn 0'})
            elif op == 19:
                nxt = self.rom.pointer(pos + 1)
            elif op == 33:
                value = self.rom.u16(pos + 2)
                if args.get(data[1], 0) == value:
                    nxt = self.rom.pointer(pos + 4)
                if data[1] not in args:
                    branches.append({'sourceOffset': hex(pos), 'selection': 'Visual-task result defaults to 0 for presentation'})
            elif op == 36:
                branches.append({'sourceOffset': hex(pos), 'selection': 'Battle, not contest'})
            pos = nxt
        else:
            raise AudioSourceError('Move execution exceeds safety bound')
        return {'sourceScript': hex(root), 'events': events, 'cries': cries,
                'cryPlayback': [playback for cry in cries for playback in cry['playbacks']],
                'reachableSongIds': ids, 'reachableCryTasks': cry_types,
                'branchSelections': branches, 'asynchronousBarriers': barriers,
                'timing': 'Explicit ROM script delays; visual completion time is not emulated'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firered', required=True, type=Path)
    parser.add_argument('--sigma', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    options = parser.parse_args()
    result = {'format': 1, 'sources': {}, 'moves': {}}
    for source, path in [('kanto', options.firered), ('johto', options.sigma)]:
        rom = AudioROM(path, source)
        reader = MoveReader(rom)
        result['sources'][source] = {'sha256': rom.sha256, 'moveTable': hex(reader.table)}
        result['moves'][source] = {str(move): reader.move(move) for move in range(1, 355)}
    options.out.parent.mkdir(parents=True, exist_ok=True)
    options.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"Extracted {sum(map(len, result['moves'].values()))} source-specific move sound graphs.")


if __name__ == '__main__':
    main()
