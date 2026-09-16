#!/usr/bin/env python3
"""Extract validated Johto/Sigma NPC talk text from the reviewed GBA ROM.

This is a static extractor, not a ROM script emulator. It follows only known
FireRed-family event opcodes, keeps a bounded call stack, and prefers the
fall-through/default path when script flags or variables cannot be known. It
never executes native ROM code. Trainer/gym objects and authored MMO field/story
objects are excluded so their existing gameplay UI remains authoritative.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import heapq
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

try:
    from .extract_adventure_data import LENGTHS as BASE_LENGTHS, Rom, normalize_objects
except ImportError:
    from extract_adventure_data import LENGTHS as BASE_LENGTHS, Rom, normalize_objects

ROOT = Path(__file__).resolve().parents[1]
JOHTO_PREFIX = "johto_"
CUT_GRAPHICS = {95, 96, 97}
MAX_TEXT_BYTES = 2048
MAX_MESSAGE_CHARS = 1800
MAX_SCRIPT_STATES = 2048
MAX_CALL_DEPTH = 12

# FireRed event command widths used only to step over instructions whose
# operands are irrelevant to static dialogue discovery. Control-flow and text
# commands are handled explicitly below. Unknown opcodes terminate that path.
LENGTHS = dict(BASE_LENGTHS)
LENGTHS.update({
    0x0A: 3, 0x0B: 3, 0x0E: 2, 0x17: 5, 0x18: 5, 0x19: 5, 0x23: 5, 0x24: 5,
    0x39: 8, 0x3A: 8, 0x3B: 8, 0x3C: 4, 0x3D: 8, 0x3E: 8, 0x3F: 8, 0x40: 8, 0x41: 8,
    0x63: 7, 0x64: 3, 0x65: 4,
    0x72: 5, 0x73: 5, 0x74: 1, 0x75: 5, 0x76: 1, 0x77: 2, 0x78: 5,
    0x79: 15, 0x7A: 3, 0x7B: 5, 0x7C: 3, 0x7D: 4, 0x7E: 2, 0x7F: 4,
    0x80: 4, 0x81: 4, 0x82: 4, 0x83: 4, 0x84: 4, 0x85: 6, 0x86: 5, 0x87: 5, 0x88: 5, 0x89: 3,
    0x8D: 1, 0x8E: 1, 0x8F: 3, 0x90: 6, 0x91: 6, 0x92: 6, 0x93: 4, 0x94: 3, 0x95: 4, 0x96: 3, 0x97: 2, 0x98: 3, 0x99: 3,
    0x9A: 2, 0x9B: 5, 0x9C: 3, 0x9D: 4, 0x9E: 3, 0x9F: 3,
    0xA0: 1, 0xA1: 5, 0xA2: 9, 0xA3: 1, 0xA4: 3, 0xA5: 1,
    0xAB: 3, 0xAC: 5, 0xAD: 5, 0xAE: 1, 0xAF: 5, 0xB0: 5, 0xB1: 8, 0xB2: 1,
    0xB3: 3, 0xB4: 3, 0xB5: 3, 0xB6: 6, 0xB7: 1, 0xB8: 5, 0xB9: 5, 0xBA: 5, 0xBB: 6, 0xBC: 6, 0xBD: 5, 0xBE: 5, 0xBF: 6,
    0xC0: 3, 0xC1: 3, 0xC2: 3, 0xC3: 2, 0xC4: 8, 0xC5: 1, 0xC6: 4, 0xC7: 2, 0xC8: 5, 0xC9: 1, 0xCA: 1, 0xCB: 1,
    0xCC: 6, 0xCD: 3, 0xCE: 3, 0xCF: 1, 0xD0: 3,
})

# English Gen III character map. Text control bytes are decoded separately.
CHARS = {
    0x00: " ", 0x01: "À", 0x02: "Á", 0x03: "Â", 0x04: "Ç", 0x05: "È", 0x06: "É", 0x07: "Ê", 0x08: "Ë",
    0x09: "Ì", 0x0B: "Î", 0x0C: "Ï", 0x0D: "Ò", 0x0E: "Ó", 0x0F: "Ô", 0x10: "Œ", 0x11: "Ù", 0x12: "Ú",
    0x13: "Û", 0x14: "Ñ", 0x15: "ß", 0x16: "à", 0x17: "á", 0x19: "ç", 0x1A: "è", 0x1B: "é", 0x1C: "ê",
    0x1D: "ë", 0x1E: "ì", 0x20: "î", 0x21: "ï", 0x22: "ò", 0x23: "ó", 0x24: "ô", 0x25: "œ", 0x26: "ù",
    0x27: "ú", 0x28: "û", 0x29: "ñ", 0x2A: "º", 0x2B: "ª", 0x2D: "&", 0x2E: "+", 0x34: "Lv", 0x35: "=",
    0x36: ";", 0x51: "¿", 0x52: "¡", 0x53: "PK", 0x54: "MN", 0x55: "PO", 0x56: "Ké", 0x57: "BL", 0x58: "OC",
    0x59: "K", 0x5A: "Í", 0x5B: "%", 0x5C: "(", 0x5D: ")", 0x68: "â", 0x6F: "í", 0x79: "↑", 0x7A: "↓",
    0x7B: "←", 0x7C: "→", 0x84: "ᵉ", 0x85: "<", 0x86: ">", 0xA0: "ʳᵉ", 0xAB: "!", 0xAC: "?", 0xAD: ".",
    0xAE: "-", 0xAF: "·", 0xB0: "…", 0xB1: "“", 0xB2: "”", 0xB3: "‘", 0xB4: "’", 0xB5: "♂", 0xB6: "♀",
    0xB7: "¥", 0xB8: ",", 0xB9: "×", 0xBA: "/", 0xEF: "▶", 0xF0: ":", 0xF1: "Ä", 0xF2: "Ö", 0xF3: "Ü",
    0xF4: "ä", 0xF5: "ö", 0xF6: "ü",
}
CHARS.update({0xA1 + i: str(i) for i in range(10)})
CHARS.update({0xBB + i: chr(65 + i) for i in range(26)})
CHARS.update({0xD5 + i: chr(97 + i) for i in range(26)})

# 0xFC extended control code operand counts. Formatting/audio controls are
# intentionally stripped; text/new-page structure remains in the web dialog.
CONTROL_ARGS = {
    0x00: 0, 0x01: 1, 0x02: 1, 0x03: 1, 0x04: 3, 0x05: 1, 0x06: 1, 0x07: 0, 0x08: 1,
    0x09: 0, 0x0A: 0, 0x0B: 2, 0x0C: 1, 0x0D: 1, 0x0E: 1, 0x0F: 0, 0x10: 2,
    0x11: 0, 0x12: 1, 0x13: 1, 0x14: 1, 0x15: 0, 0x16: 0, 0x17: 0, 0x18: 0,
}
PLACEHOLDERS = {
    0x01: "{PLAYER}", 0x02: "{STR_VAR_1}", 0x03: "{STR_VAR_2}", 0x04: "{STR_VAR_3}",
    0x05: "{KUN}", 0x06: "{RIVAL}", 0x07: "{VERSION}", 0x08: "{EVIL_TEAM}",
    0x09: "{EVIL_LEADER}", 0x0A: "{LEGENDARY}", 0x0B: "{EVIL_TEAM2}",
    0x0C: "{EVIL_LEADER2}", 0x0D: "{LEGENDARY2}",
}
DYNAMIC_TOKEN_RE = re.compile(r"\{[A-Z0-9_]+\}")
STANDARD_STRINGS = {15: "Boulder Badge", 16: "Cascade Badge", 17: "Thunder Badge", 18: "Rainbow Badge", 19: "Soul Badge", 20: "Marsh Badge", 21: "Volcano Badge", 22: "Earth Badge"}


@dataclass(frozen=True)
class Candidate:
    branch_cost: int
    steps: int
    text_pointer: int
    buffers: tuple[str, str, str]
    kind: str
    command_offset: int


def accepted_sigma_source(root: Path) -> dict:
    manifest = json.loads((root / "Tools/extraction_manifest.json").read_text(encoding="utf-8"))
    rows = [row for row in manifest.get("sources", []) if row.get("source") == "johto"]
    if len(rows) != 1:
        raise ValueError("Extraction manifest does not contain exactly one reviewed Johto source")
    return rows[0]


def pointer_value(rom: Rom, offset: int) -> int | None:
    value = rom.u32(offset) - 0x08000000
    return value if 0 <= value < len(rom.b) else None


def decode_text(rom: Rom, pointer: int, buffers: tuple[str, str, str] = ("", "", "")) -> tuple[str | None, dict]:
    output: list[str] = []
    controls: list[int] = []
    placeholders: list[int] = []
    i = pointer
    for _ in range(MAX_TEXT_BYTES):
        if not 0 <= i < len(rom.b):
            return None, {"reason": "range"}
        byte = rom.b[i]
        i += 1
        if byte == 0xFF:
            break
        if byte in (0xFA, 0xFE):
            output.append("\n")
            continue
        if byte == 0xFB:
            output.append("\n\n")
            continue
        if byte == 0xFC:
            if i >= len(rom.b):
                return None, {"reason": "control-range"}
            code = rom.b[i]
            i += 1
            controls.append(code)
            operands = CONTROL_ARGS.get(code)
            if operands is None:
                return None, {"reason": f"control-{code:02x}"}
            i += operands
            if i > len(rom.b):
                return None, {"reason": "control-range"}
            continue
        if byte == 0xFD:
            if i >= len(rom.b):
                return None, {"reason": "placeholder-range"}
            code = rom.b[i]
            i += 1
            placeholders.append(code)
            if code in (0x02, 0x03, 0x04):
                output.append(buffers[code - 2] or PLACEHOLDERS[code])
            elif code in PLACEHOLDERS:
                output.append(PLACEHOLDERS[code])
            else:
                return None, {"reason": f"placeholder-{code:02x}"}
            continue
        glyph = CHARS.get(byte)
        if glyph is None:
            return None, {"reason": f"char-{byte:02x}"}
        output.append(glyph)
    else:
        return None, {"reason": "unterminated"}

    message = "".join(output).replace("PKMN", "Pokémon").replace("POKéBLOCK", "Pokéblock")
    message = "\n".join(line.rstrip() for line in message.splitlines()).strip()
    message = re.sub(r"\n{3,}", "\n\n", message)
    letters = sum(ch.isalpha() for ch in message)
    if not message or len(message) > MAX_MESSAGE_CHARS or letters < 2:
        return None, {"reason": "implausible"}
    if any(ord(ch) < 32 and ch != "\n" for ch in message):
        return None, {"reason": "control-character"}
    return message, {"controls": controls, "placeholders": placeholders}


def read_item_names(rom: Rom) -> dict[int, str]:
    """Decode only item records whose embedded source ID validates the stride."""
    names: dict[int, str] = {}
    try:
        base = rom.ptr(0x1C8)
    except (ValueError, struct.error):
        return names
    for item_id in range(1024):
        q = base + item_id * 44
        if q + 44 > len(rom.b):
            break
        if rom.u16(q + 14) != item_id:
            continue
        chars: list[str] = []
        valid = True
        for byte in rom.raw(q, 14):
            if byte == 0xFF:
                break
            glyph = CHARS.get(byte)
            if glyph is None:
                valid = False
                break
            chars.append(glyph)
        value = "".join(chars).strip()
        if valid and value:
            names[item_id] = value
    return names


def script_candidates(rom: Rom, start: int, species_names: dict[int, str], item_names: dict[int, str], move_names: dict[int, str]) -> tuple[list[Candidate], collections.Counter]:
    """Find reachable literal message pointers without deciding game flags."""
    queue: list[tuple[int, int, int, int, tuple[int, ...], int | None, tuple[str, str, str]]] = []
    sequence = 0
    heapq.heappush(queue, (0, 0, sequence, start, (), None, ("", "", "")))
    seen: set[tuple] = set()
    found: list[Candidate] = []
    stops: collections.Counter = collections.Counter()

    while queue and len(seen) < MAX_SCRIPT_STATES:
        branch_cost, steps, _, pc, stack, word0, buffers = heapq.heappop(queue)
        key = (pc, stack, word0, buffers)
        if key in seen:
            continue
        seen.add(key)
        if not 0 <= pc < len(rom.b):
            stops["range"] += 1
            continue
        op = rom.b[pc]

        def push(next_pc: int, *, next_stack=stack, next_word=word0, next_buffers=buffers, extra_cost=0):
            nonlocal sequence
            sequence += 1
            heapq.heappush(queue, (branch_cost + extra_cost, steps + 1, sequence, next_pc, next_stack, next_word, next_buffers))

        try:
            if op in (0x02, 0x0D):  # end / endram
                stops["end"] += 1
                continue
            if op in (0x03, 0x0C):  # return / returnram
                if stack:
                    push(stack[-1], next_stack=stack[:-1])
                else:
                    stops["return"] += 1
                continue
            if op in (0x04, 0x05):  # call / goto
                target = rom.ptr(pc + 1)
                if op == 0x04:
                    if len(stack) >= MAX_CALL_DEPTH:
                        stops["call-depth"] += 1
                    else:
                        push(target, next_stack=stack + (pc + 5,))
                else:
                    push(target)
                continue
            if op in (0x06, 0x07):  # goto_if / call_if
                if rom.b[pc + 1] > 5:
                    raise ValueError("invalid comparison")
                target = rom.ptr(pc + 2)
                push(pc + 6)  # unknown condition: prefer ordinary fall-through
                if op == 0x07:
                    if len(stack) >= MAX_CALL_DEPTH:
                        stops["call-depth"] += 1
                    else:
                        push(target, next_stack=stack + (pc + 6,), extra_cost=1)
                else:
                    push(target, extra_cost=1)
                continue
            if op == 0x0F:  # loadword index, immediate pointer
                index = rom.b[pc + 1]
                value = pointer_value(rom, pc + 2)
                push(pc + 6, next_word=value if index == 0 else word0)
                continue
            if op in (0x08, 0x09):  # gotostd / callstd
                std = rom.b[pc + 1]
                if std in (2, 3, 4, 5, 6) and word0 is not None:
                    found.append(Candidate(branch_cost, steps, word0, buffers, f"std-{std}", pc))
                if op == 0x08:
                    stops["gotostd"] += 1
                else:
                    push(pc + 2)
                continue
            if op in (0x0A, 0x0B):  # gotostd_if / callstd_if
                std = rom.b[pc + 2]
                # The standard call happens only on the unknown true branch.
                if std in (2, 3, 4, 5, 6) and word0 is not None:
                    found.append(Candidate(branch_cost + 1, steps, word0, buffers, f"std-if-{std}", pc))
                push(pc + 3)
                continue
            if op in (0x67, 0x9B):  # message / messageautoscroll
                pointer = rom.ptr(pc + 1)
                found.append(Candidate(branch_cost, steps, pointer, buffers, "message" if op == 0x67 else "autoscroll", pc))
                push(pc + 5)
                continue

            # String-var builders used by the text placeholders.
            if op == 0x7D:  # bufferspeciesname
                slot, source_id = rom.b[pc + 1], rom.u16(pc + 2)
                values = list(buffers)
                if slot < 3:
                    values[slot] = species_names.get(source_id, f"Pokémon #{source_id}")
                push(pc + 4, next_buffers=tuple(values))
                continue
            if op == 0x7E:  # bufferleadmonspeciesname
                slot = rom.b[pc + 1]
                values = list(buffers)
                if slot < 3:
                    values[slot] = "{LEAD_SPECIES}"
                push(pc + 2, next_buffers=tuple(values))
                continue
            if op == 0x7F:  # bufferpartymonnick
                slot, party_slot = rom.b[pc + 1], rom.u16(pc + 2)
                values = list(buffers)
                if slot < 3:
                    values[slot] = f"{{PARTY_MON_{party_slot + 1}}}" if 0 <= party_slot < 6 else "{PARTY_MON}"
                push(pc + 4, next_buffers=tuple(values))
                continue
            if op == 0x80:  # bufferitemname
                slot, item_id = rom.b[pc + 1], rom.u16(pc + 2)
                values = list(buffers)
                if slot < 3:
                    values[slot] = item_names.get(item_id, f"Item #{item_id}")
                push(pc + 4, next_buffers=tuple(values))
                continue
            if op == 0x81:  # bufferdecorationname
                slot, decoration_id = rom.b[pc + 1], rom.u16(pc + 2)
                values = list(buffers)
                if slot < 3:
                    values[slot] = f"Decoration #{decoration_id}"
                push(pc + 4, next_buffers=tuple(values))
                continue
            if op == 0x82:  # buffermovename
                slot, move_id = rom.b[pc + 1], rom.u16(pc + 2)
                values = list(buffers)
                if slot < 3:
                    values[slot] = move_names.get(move_id, f"Move #{move_id}")
                push(pc + 4, next_buffers=tuple(values))
                continue
            if op == 0x83:  # buffernumberstring
                slot, number = rom.b[pc + 1], rom.u16(pc + 2)
                values = list(buffers)
                if slot < 3:
                    values[slot] = str(number) if number < 0x4000 else "{NUMBER}"
                push(pc + 4, next_buffers=tuple(values))
                continue
            if op == 0x84:  # bufferstdstring
                slot, string_id = rom.b[pc + 1], rom.u16(pc + 2)
                values = list(buffers)
                if slot < 3:
                    values[slot] = STANDARD_STRINGS.get(string_id, f"{{STD_STRING_{string_id}}}")
                push(pc + 4, next_buffers=tuple(values))
                continue
            if op == 0x85:  # bufferstring
                slot, pointer = rom.b[pc + 1], rom.ptr(pc + 2)
                values = list(buffers)
                if slot < 3:
                    value, _ = decode_text(rom, pointer, tuple(values))
                    values[slot] = value or "{STRING}"
                push(pc + 6, next_buffers=tuple(values))
                continue
            if op == 0x5C:  # trainerbattle; trainer UI is intentionally separate
                stops["trainerbattle"] += 1
                continue
            if op in LENGTHS:
                size = LENGTHS[op]
                rom.raw(pc, size)
                push(pc + size)
                continue
            stops[f"opcode-{op:02x}"] += 1
        except (IndexError, ValueError, struct.error):
            stops["invalid-instruction"] += 1

    if queue:
        stops["instruction-limit"] += 1
    found.sort(key=lambda candidate: (candidate.branch_cost, candidate.steps, candidate.text_pointer, candidate.command_offset))
    return found, stops


def extract(root: Path, rom_path: Path) -> dict:
    root = Path(root).resolve()
    accepted = accepted_sigma_source(root)
    rom_bytes = Path(rom_path).read_bytes()
    digest = hashlib.sha256(rom_bytes).hexdigest()
    if digest != accepted["sha256"] or len(rom_bytes) != accepted["size"]:
        raise ValueError("The supplied ROM is not the reviewed Ultra Shiny Gold Sigma revision used by this project")
    rom = Rom(rom_path)
    world = json.loads((root / "Server/data/world.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "Tools/extraction_manifest.json").read_text(encoding="utf-8"))
    species_names = {int(key): row["name"] for key, row in manifest["catalogs"]["johto"].items()}
    item_names = read_item_names(rom)
    move_names = {int(key): row["name"] for key, row in world["moves"].items()}
    trainer_keys = set(world.get("adventureRom", {}).get("trainers", {}))

    entries: dict[str, dict] = {}
    audit = collections.Counter()
    stop_reasons = collections.Counter()
    decode_reasons = collections.Counter()
    controls = collections.Counter()
    placeholders = collections.Counter()

    for map_id, map_data in sorted(world["maps"].items()):
        if not map_id.startswith(JOHTO_PREFIX):
            continue
        audit["maps"] += 1
        try:
            header = int(map_data["sourceHeader"], 16)
            events = rom.ptr(header + 4)
            count = rom.b[events]
            table = rom.ptr(events + 4) if count else None
        except (KeyError, ValueError, IndexError, struct.error):
            audit["mapsWithoutReadableEvents"] += 1
            continue
        normalized = {obj["sourceObjectIndex"]: obj for obj in normalize_objects(rom, map_data) if "sourceObjectIndex" in obj}
        published_by_id = {obj["id"]: obj for obj in map_data.get("objects", [])}
        for source_index, obj in normalized.items():
            audit["visibleObjects"] += 1
            key = f"{map_id}:{obj['id']}"
            if key in trainer_keys:
                audit["excludedTrainerBindings"] += 1
                continue
            if obj.get("trainerType", 0):
                audit["excludedTrainerTypeObjects"] += 1
                continue
            published = published_by_id.get(obj["id"], obj)
            if published.get("storyEvent"):
                audit["excludedStoryObjects"] += 1
                continue
            if obj.get("graphics") in CUT_GRAPHICS:
                audit["excludedFieldMoveObjects"] += 1
                continue
            audit["eligibleObjects"] += 1
            try:
                object_offset = table + source_index * 24
                script = rom.ptr(object_offset + 16)
            except (TypeError, ValueError, IndexError, struct.error):
                audit["withoutScriptPointer"] += 1
                continue

            candidates, stops = script_candidates(rom, script, species_names, item_names, move_names)
            stop_reasons.update(stops)
            chosen = None
            valid_count = 0
            for candidate in candidates:
                message, metadata = decode_text(rom, candidate.text_pointer, candidate.buffers)
                if message is None:
                    decode_reasons[metadata.get("reason", "unknown")] += 1
                    continue
                valid_count += 1
                if chosen is None:
                    chosen = (candidate, message, metadata)
            if chosen is None:
                audit["withoutValidatedLiteral"] += 1
                continue

            candidate, message, metadata = chosen
            controls.update(metadata.get("controls", []))
            placeholders.update(metadata.get("placeholders", []))
            tokens = sorted(set(DYNAMIC_TOKEN_RE.findall(message)))
            entry = {
                "map": map_id,
                "npc": obj["id"],
                "message": message,
                "sourceScript": hex(script),
                "sourceText": hex(candidate.text_pointer),
                "sourceCommand": hex(candidate.command_offset),
                "sourceObjectOffset": hex(object_offset),
                "sourceObjectIndex": source_index,
                "sourceLocalId": obj.get("sourceLocalId", obj["id"]),
                "graphics": obj.get("graphics"),
                "candidateCount": valid_count,
                "branchCost": candidate.branch_cost,
                "messageKind": candidate.kind,
            }
            if tokens:
                entry["dynamicTokens"] = tokens
            entries[key] = entry
            audit["dialogueEntries"] += 1

    result = {
        "format": 1,
        "source": {
            "label": "Pokemon Ultra Shiny Gold Sigma Completo 1.5.0",
            "sha256": digest,
            "size": len(rom_bytes),
            "revision": accepted.get("revision", 0),
        },
        "policy": {
            "regionPrefix": JOHTO_PREFIX,
            "selection": "reachable validated literal with lowest unknown-conditional branch cost, then shortest static path",
            "trainerPolicy": "trainer bindings and trainer-type objects excluded; existing trainer/gym preview UI remains authoritative",
            "storyPolicy": "authored MMO story objects and Cut objects excluded",
            "scriptExecution": False,
        },
        "entries": entries,
        "audit": {
            **dict(sorted(audit.items())),
            "scriptStopReasons": dict(sorted(stop_reasons.items())),
            "decodeRejectReasons": dict(sorted(decode_reasons.items())),
            "textControlsStripped": {f"0x{key:02x}": value for key, value in sorted(controls.items())},
            "placeholderUses": {f"0x{key:02x}": value for key, value in sorted(placeholders.items())},
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="Reviewed Ultra Shiny Gold Sigma .gba")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output or root / "Server/data/johto_dialogue.json"
    data = extract(root, args.rom.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    a = data["audit"]
    print(f"Extracted {a.get('dialogueEntries', 0)} validated Johto/Sigma NPC dialogues from {a.get('eligibleObjects', 0)} eligible visible objects.")
    print(f"Trainer bindings excluded: {a.get('excludedTrainerBindings', 0)}; trainer-type objects excluded: {a.get('excludedTrainerTypeObjects', 0)}.")
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
