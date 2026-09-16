#!/usr/bin/env python3
"""Extract validated regular Kanto NPC talk text from the reviewed FireRed ROM.

The extractor is deliberately static: it follows only the bounded FireRed event
opcodes implemented by ``extract_sigma_dialogue`` and never executes ROM code,
native specials, arbitrary flags, or choice handlers.  Trainer/Gym objects keep
NXT's existing team-preview UI.  Non-regular object graphics (item balls,
Pokemon/field props, rocks/trees, and other object-event actors) are excluded so
this sidecar contains ordinary person NPC dialogue only.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import struct
from pathlib import Path

try:
    from .extract_adventure_data import Rom, normalize_objects
    from .extract_sigma_dialogue import DYNAMIC_TOKEN_RE, decode_text, read_item_names, script_candidates
except ImportError:
    from extract_adventure_data import Rom, normalize_objects
    from extract_sigma_dialogue import DYNAMIC_TOKEN_RE, decode_text, read_item_names, script_candidates

ROOT = Path(__file__).resolve().parents[1]
KANTO_PREFIX = "kanto_"
# In the reviewed FireRed object-event graphics table, 0..91 are the ordinary
# person-scale NPC actor set.  92+ starts the item/field/Pokemon/object actor
# range.  Keeping this explicit prevents item pickup/result strings from being
# presented as ordinary NPC speech.
REGULAR_NPC_GRAPHICS_MAX = 91


def accepted_firered_source(root: Path) -> dict:
    manifest = json.loads((root / "Tools/extraction_manifest.json").read_text(encoding="utf-8"))
    rows = [row for row in manifest.get("sources", []) if row.get("source") == "kanto"]
    if len(rows) != 1:
        raise ValueError("Extraction manifest does not contain exactly one reviewed Kanto/FireRed source")
    return rows[0]


def extract(root: Path, rom_path: Path) -> dict:
    root = Path(root).resolve()
    accepted = accepted_firered_source(root)
    rom_bytes = Path(rom_path).read_bytes()
    digest = hashlib.sha256(rom_bytes).hexdigest()
    if digest != accepted["sha256"] or len(rom_bytes) != accepted["size"]:
        raise ValueError("The supplied ROM is not the reviewed Pokemon FireRed Rev 1 revision used by this project")

    rom = Rom(rom_path)
    world = json.loads((root / "Server/data/world.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "Tools/extraction_manifest.json").read_text(encoding="utf-8"))
    species_names = {int(key): row["name"] for key, row in manifest["catalogs"]["kanto"].items()}
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
        if not map_id.startswith(KANTO_PREFIX):
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

        normalized = {
            obj["sourceObjectIndex"]: obj
            for obj in normalize_objects(rom, map_data)
            if "sourceObjectIndex" in obj
        }
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
            graphics = obj.get("graphics")
            if not isinstance(graphics, int) or graphics > REGULAR_NPC_GRAPHICS_MAX:
                audit["excludedNonRegularObjects"] += 1
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
                "graphics": graphics,
                "candidateCount": valid_count,
                "branchCost": candidate.branch_cost,
                "messageKind": candidate.kind,
            }
            if tokens:
                entry["dynamicTokens"] = tokens
            entries[key] = entry
            audit["dialogueEntries"] += 1

    return {
        "format": 1,
        "source": {
            "label": "Pokemon FireRed Version (USA, Europe) Rev 1",
            "sha256": digest,
            "size": len(rom_bytes),
            "revision": accepted.get("revision", 1),
        },
        "policy": {
            "regionPrefix": KANTO_PREFIX,
            "selection": "reachable validated literal with lowest unknown-conditional branch cost, then shortest static path",
            "regularNpcGraphicsMax": REGULAR_NPC_GRAPHICS_MAX,
            "trainerPolicy": "trainer bindings and trainer-type objects excluded; existing trainer/gym preview UI remains authoritative",
            "objectPolicy": "only ordinary person NPC object graphics are published; item/Pokemon/field objects remain on existing NXT behavior",
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="Reviewed Pokemon FireRed Rev 1 .gba")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output or root / "Server/data/kanto_dialogue.json"
    data = extract(root, args.rom.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    a = data["audit"]
    print(f"Extracted {a.get('dialogueEntries', 0)} validated Kanto/FireRed regular NPC dialogues from {a.get('eligibleObjects', 0)} eligible visible NPC objects.")
    print(f"Trainer bindings excluded: {a.get('excludedTrainerBindings', 0)}; trainer-type objects excluded: {a.get('excludedTrainerTypeObjects', 0)}; non-regular objects excluded: {a.get('excludedNonRegularObjects', 0)}.")
    print(f"Output: {output}")


if __name__ == "__main__":
    main()
