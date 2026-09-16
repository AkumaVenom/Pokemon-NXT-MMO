#!/usr/bin/env python3
"""Validate bundled Sigma NPC dialogue and attach it to the server world pack."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

CUT_GRAPHICS = {95, 96, 97}
TOKEN_RE = re.compile(r"\{[A-Z0-9_]+\}")
ALLOWED_DYNAMIC = {
    "{PLAYER}", "{KUN}", "{RIVAL}", "{VERSION}", "{EVIL_TEAM}", "{EVIL_LEADER}", "{LEGENDARY}",
    "{EVIL_TEAM2}", "{EVIL_LEADER2}", "{LEGENDARY2}", "{LEAD_SPECIES}", "{PARTY_MON}", "{NUMBER}", "{STRING}",
    "{STR_VAR_1}", "{STR_VAR_2}", "{STR_VAR_3}",
} | {f"{{PARTY_MON_{i}}}" for i in range(1, 7)}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def accepted_hash(root: Path) -> tuple[str, int]:
    manifest = read_json(root / "Tools/extraction_manifest.json")
    row = next((row for row in manifest.get("sources", []) if row.get("source") == "johto"), None)
    if row is None:
        raise ValueError("Missing reviewed Johto ROM provenance")
    return row["sha256"], row["size"]


def assemble(world: dict, root: Path) -> None:
    root = Path(root)
    data = read_json(root / "Server/data/johto_dialogue.json")
    if data.get("format") != 1:
        raise ValueError("Unsupported Johto NPC dialogue format")
    sha, size = accepted_hash(root)
    if data.get("source", {}).get("sha256") != sha or data.get("source", {}).get("size") != size:
        raise ValueError("Johto NPC dialogue provenance does not match the reviewed Sigma ROM")
    if data.get("policy", {}).get("scriptExecution") is not False:
        raise ValueError("Johto NPC dialogue must remain static and non-executing")

    trainers = set(world.get("adventureRom", {}).get("trainers", {}))
    validated: dict[str, dict] = {}
    for key, entry in data.get("entries", {}).items():
        if key != f"{entry.get('map')}:{entry.get('npc')}" or not entry.get("map", "").startswith("johto_"):
            raise ValueError("Invalid Johto dialogue identity: " + str(key))
        map_data = world["maps"].get(entry["map"])
        if map_data is None:
            raise ValueError("Johto dialogue map is unavailable: " + key)
        obj = next((obj for obj in map_data.get("objects", []) if obj.get("id") == entry["npc"]), None)
        if obj is None:
            raise ValueError("Johto dialogue object is unavailable: " + key)
        if key in trainers or obj.get("trainerType", 0):
            raise ValueError("Trainer dialogue must not override trainer/gym preview UI: " + key)
        if obj.get("storyEvent") or obj.get("graphics") in CUT_GRAPHICS:
            raise ValueError("Authored story/field object must keep its dedicated UI: " + key)
        if entry.get("sourceObjectIndex") != obj.get("sourceObjectIndex") or entry.get("sourceLocalId") != obj.get("sourceLocalId"):
            raise ValueError("Johto dialogue source-object provenance mismatch: " + key)
        message = entry.get("message")
        if not isinstance(message, str) or not 1 <= len(message) <= 1800:
            raise ValueError("Invalid Johto dialogue text length: " + key)
        if any(ord(ch) < 32 and ch != "\n" for ch in message):
            raise ValueError("Johto dialogue contains unsafe control characters: " + key)
        tokens = set(TOKEN_RE.findall(message))
        unresolved_std = {token for token in tokens if token.startswith("{STD_STRING_")}
        if unresolved_std or tokens - ALLOWED_DYNAMIC:
            raise ValueError("Johto dialogue contains an unsupported runtime token: " + key)
        declared = set(entry.get("dynamicTokens", []))
        if declared != tokens:
            raise ValueError("Johto dialogue dynamic token audit mismatch: " + key)
        validated[key] = copy.deepcopy(entry)

    expected = data.get("audit", {}).get("dialogueEntries")
    if expected != len(validated):
        raise ValueError("Johto dialogue audit count does not match bundled entries")
    world["npcDialogue"] = {
        "format": 1,
        "source": copy.deepcopy(data["source"]),
        "policy": copy.deepcopy(data["policy"]),
        "entries": validated,
    }


if __name__ == "__main__":
    raise SystemExit("Use Tools/repack_content.py so server/client pack hashes remain synchronized.")
