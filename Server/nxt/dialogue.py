"""Runtime renderer for audited static Johto/Sigma NPC talk text."""
from __future__ import annotations

import re

TOKEN_RE = re.compile(r"\{[A-Z0-9_]+\}")
STATIC_REPLACEMENTS = {
    "{KUN}": "",
    "{RIVAL}": "Rival",
    "{VERSION}": "Ultra Shiny Gold Sigma",
    "{EVIL_TEAM}": "Team Rocket",
    "{EVIL_LEADER}": "Giovanni",
    "{LEGENDARY}": "legendary Pokémon",
    "{EVIL_TEAM2}": "Team Rocket",
    "{EVIL_LEADER2}": "Giovanni",
    "{LEGENDARY2}": "legendary Pokémon",
    "{NUMBER}": "number",
    "{STRING}": "…",
    "{STR_VAR_1}": "…",
    "{STR_VAR_2}": "…",
    "{STR_VAR_3}": "…",
}


def _party_name(content, state: dict, index: int) -> str:
    party = state.get("party", [])
    if not 0 <= index < len(party):
        return "Pokémon"
    uid = party[index]
    mon = next((mon for mon in state.get("creatures", []) if mon.get("uid") == uid), None)
    if not mon:
        return "Pokémon"
    species = content.species.get(mon.get("species"), {})
    return species.get("name") or "Pokémon"


def render(content, state: dict, username: str, map_id: str, npc_id: int) -> str | None:
    """Return owner-contextualized ROM text, or None when no audited literal exists."""
    if not map_id.startswith("johto_"):
        return None
    entry = content.data.get("npcDialogue", {}).get("entries", {}).get(f"{map_id}:{npc_id}")
    if not entry:
        return None
    message = entry.get("message")
    if not isinstance(message, str):
        return None

    replacements = dict(STATIC_REPLACEMENTS)
    replacements["{PLAYER}"] = username
    trade_context = "trade" in message.casefold() or "looking for the pokémon" in message.casefold()
    replacements["{STR_VAR_1}"] = "Pokémon" if trade_context else "Trainer"
    replacements["{STR_VAR_2}"] = "Pokémon"
    replacements["{STR_VAR_3}"] = "Pokémon"
    replacements["{LEAD_SPECIES}"] = _party_name(content, state, 0)
    replacements["{PARTY_MON}"] = replacements["{LEAD_SPECIES}"]
    for index in range(6):
        replacements[f"{{PARTY_MON_{index + 1}}}"] = _party_name(content, state, index)
    return TOKEN_RE.sub(lambda match: replacements.get(match.group(0), "…"), message)
