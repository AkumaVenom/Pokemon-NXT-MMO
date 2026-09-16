#!/usr/bin/env python3
"""Validate bundled ROM-derived NPC dialogue and attach it to the world pack.

Both regional sidecars are static extraction products.  Publishing validates
ROM provenance, source-object identity, trainer/story isolation, safe runtime
tokens and the per-region object policy before merging entries.  No ROM is
required by a normal source build.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

CUT_GRAPHICS = {95, 96, 97}
KANTO_REGULAR_NPC_GRAPHICS_MAX = 91
TOKEN_RE = re.compile(r"\{[A-Z0-9_]+\}")
ALLOWED_DYNAMIC = {
    "{PLAYER}", "{KUN}", "{RIVAL}", "{VERSION}", "{EVIL_TEAM}", "{EVIL_LEADER}", "{LEGENDARY}",
    "{EVIL_TEAM2}", "{EVIL_LEADER2}", "{LEGENDARY2}", "{LEAD_SPECIES}", "{PARTY_MON}", "{NUMBER}", "{STRING}",
    "{STR_VAR_1}", "{STR_VAR_2}", "{STR_VAR_3}",
} | {f"{{PARTY_MON_{i}}}" for i in range(1, 7)}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def accepted_source(root: Path, source: str) -> tuple[str, int]:
    manifest = read_json(root / "Tools/extraction_manifest.json")
    rows = [row for row in manifest.get("sources", []) if row.get("source") == source]
    if len(rows) != 1:
        raise ValueError(f"Missing or ambiguous reviewed {source} ROM provenance")
    return rows[0]["sha256"], rows[0]["size"]


def _validate_sidecar(world: dict, root: Path, *, source: str, filename: str, prefix: str) -> tuple[dict, dict, dict]:
    data = read_json(root / "Server/data" / filename)
    label = "Kanto/FireRed" if source == "kanto" else "Johto/Sigma"
    if data.get("format") != 1:
        raise ValueError(f"Unsupported {label} NPC dialogue format")
    sha, size = accepted_source(root, source)
    if data.get("source", {}).get("sha256") != sha or data.get("source", {}).get("size") != size:
        raise ValueError(f"{label} NPC dialogue provenance does not match the reviewed ROM")
    policy = data.get("policy", {})
    if policy.get("scriptExecution") is not False:
        raise ValueError(f"{label} NPC dialogue must remain static and non-executing")
    if policy.get("regionPrefix") != prefix:
        raise ValueError(f"{label} NPC dialogue region policy mismatch")
    if source == "kanto" and policy.get("regularNpcGraphicsMax") != KANTO_REGULAR_NPC_GRAPHICS_MAX:
        raise ValueError("Kanto NPC dialogue regular-object graphics policy mismatch")

    trainers = set(world.get("adventureRom", {}).get("trainers", {}))
    validated: dict[str, dict] = {}
    for key, entry in data.get("entries", {}).items():
        if key != f"{entry.get('map')}:{entry.get('npc')}" or not entry.get("map", "").startswith(prefix):
            raise ValueError(f"Invalid {label} dialogue identity: {key}")
        map_data = world["maps"].get(entry["map"])
        if map_data is None:
            raise ValueError(f"{label} dialogue map is unavailable: {key}")
        obj = next((obj for obj in map_data.get("objects", []) if obj.get("id") == entry["npc"]), None)
        if obj is None:
            raise ValueError(f"{label} dialogue object is unavailable: {key}")
        if key in trainers or obj.get("trainerType", 0):
            raise ValueError("Trainer dialogue must not override trainer/gym preview UI: " + key)
        if obj.get("storyEvent"):
            raise ValueError("Authored story object must keep its dedicated UI: " + key)
        if source == "johto" and obj.get("graphics") in CUT_GRAPHICS:
            raise ValueError("Johto field object must keep its dedicated UI: " + key)
        if source == "kanto" and (not isinstance(obj.get("graphics"), int) or obj["graphics"] > KANTO_REGULAR_NPC_GRAPHICS_MAX):
            raise ValueError("Kanto non-regular object must not receive regular NPC dialogue: " + key)
        if entry.get("sourceObjectIndex") != obj.get("sourceObjectIndex") or entry.get("sourceLocalId") != obj.get("sourceLocalId"):
            raise ValueError(f"{label} dialogue source-object provenance mismatch: {key}")
        message = entry.get("message")
        if not isinstance(message, str) or not 1 <= len(message) <= 1800:
            raise ValueError(f"Invalid {label} dialogue text length: {key}")
        if any(ord(ch) < 32 and ch != "\n" for ch in message):
            raise ValueError(f"{label} dialogue contains unsafe control characters: {key}")
        tokens = set(TOKEN_RE.findall(message))
        unresolved_std = {token for token in tokens if token.startswith("{STD_STRING_")}
        if unresolved_std or tokens - ALLOWED_DYNAMIC:
            raise ValueError(f"{label} dialogue contains an unsupported runtime token: {key}")
        declared = set(entry.get("dynamicTokens", []))
        if declared != tokens:
            raise ValueError(f"{label} dialogue dynamic token audit mismatch: {key}")
        published = copy.deepcopy(entry)
        published["sourceRegion"] = source
        validated[key] = published

    expected = data.get("audit", {}).get("dialogueEntries")
    if expected != len(validated):
        raise ValueError(f"{label} dialogue audit count does not match bundled entries")
    return validated, copy.deepcopy(data["source"]), copy.deepcopy(policy)


def assemble(world: dict, root: Path) -> None:
    root = Path(root)
    kanto_entries, kanto_source, kanto_policy = _validate_sidecar(
        world, root, source="kanto", filename="kanto_dialogue.json", prefix="kanto_"
    )
    johto_entries, johto_source, johto_policy = _validate_sidecar(
        world, root, source="johto", filename="johto_dialogue.json", prefix="johto_"
    )
    overlap = set(kanto_entries) & set(johto_entries)
    if overlap:
        raise ValueError("Regional NPC dialogue identity collision: " + sorted(overlap)[0])
    world["npcDialogue"] = {
        "format": 2,
        "sources": {"kanto": kanto_source, "johto": johto_source},
        "policies": {"kanto": kanto_policy, "johto": johto_policy},
        "entries": {**kanto_entries, **johto_entries},
    }


if __name__ == "__main__":
    raise SystemExit("Use Tools/repack_content.py so server/client pack hashes remain synchronized.")
