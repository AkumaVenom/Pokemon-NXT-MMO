"""Audited Johto/Sigma NPC dialogue extraction, publishing and runtime behavior."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Server"))

from nxt.config import Settings
from nxt.content import Content
from nxt.dialogue import render
from nxt.store import Store
from nxt.world import World

SIGMA_SHA = "62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64"
ROUTE36_KEY = "johto_2_23:1"
ROUTE36_MESSAGE_SHA = "affb1b340b763159965b4944cff81f27df975fb52d736ea169286824f62d3c7b"
CUT_GRAPHICS = {95, 96, 97}
TOKEN_RE = re.compile(r"\{[A-Z0-9_]+\}")
ALLOWED_TOKENS = {
    "{PLAYER}", "{KUN}", "{RIVAL}", "{VERSION}", "{EVIL_TEAM}", "{EVIL_LEADER}", "{LEGENDARY}",
    "{EVIL_TEAM2}", "{EVIL_LEADER2}", "{LEGENDARY2}", "{LEAD_SPECIES}", "{PARTY_MON}", "{NUMBER}", "{STRING}",
    "{STR_VAR_1}", "{STR_VAR_2}", "{STR_VAR_3}",
} | {f"{{PARTY_MON_{i}}}" for i in range(1, 7)}


class PublishedDialogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / "Server/data/world.json")
        cls.world = cls.content.data
        cls.sidecar = json.loads((ROOT / "Server/data/johto_dialogue.json").read_text(encoding="utf-8"))
        cls.entries = {key: entry for key, entry in cls.world["npcDialogue"]["entries"].items() if key.startswith("johto_")}

    def test_reviewed_sigma_provenance_and_release_version_are_published(self):
        self.assertEqual(self.world["version"], "0.6.10-alpha")
        self.assertEqual(self.sidecar["source"]["sha256"], SIGMA_SHA)
        self.assertEqual(self.world["npcDialogue"]["format"], 2)
        self.assertEqual(self.world["npcDialogue"]["sources"]["johto"]["sha256"], SIGMA_SHA)
        self.assertEqual(self.sidecar["source"]["size"], 17632785)
        self.assertFalse(self.world["npcDialogue"]["policies"]["johto"]["scriptExecution"])

    def test_every_published_entry_targets_a_real_nontrainer_nonstory_johto_object(self):
        trainer_keys = set(self.world["adventureRom"]["trainers"])
        for key, entry in self.entries.items():
            self.assertEqual(key, f"{entry['map']}:{entry['npc']}")
            self.assertTrue(entry["map"].startswith("johto_"))
            self.assertNotIn(key, trainer_keys)
            obj = next(o for o in self.world["maps"][entry["map"]]["objects"] if o["id"] == entry["npc"])
            self.assertFalse(obj.get("trainerType", 0), key)
            self.assertNotIn("storyEvent", obj, key)
            self.assertNotIn(obj["graphics"], CUT_GRAPHICS, key)
            self.assertEqual(entry["sourceObjectIndex"], obj["sourceObjectIndex"], key)
            self.assertEqual(entry["sourceLocalId"], obj["sourceLocalId"], key)

    def test_audit_accounts_for_every_visible_object_without_claiming_script_execution(self):
        audit = self.sidecar["audit"]
        self.assertEqual(audit["visibleObjects"], 4429)
        self.assertEqual(audit["dialogueEntries"], 2158)
        self.assertEqual(audit["dialogueEntries"], len(self.sidecar["entries"]))
        self.assertEqual(audit["dialogueEntries"], len(self.entries))
        self.assertEqual(audit["withoutScriptPointer"], 166)
        self.assertEqual(audit["withoutValidatedLiteral"], 800)
        self.assertEqual(audit["eligibleObjects"], audit["dialogueEntries"] + audit["withoutScriptPointer"] + audit["withoutValidatedLiteral"])
        self.assertEqual(audit["visibleObjects"], audit["eligibleObjects"] + audit["excludedTrainerBindings"] + audit["excludedTrainerTypeObjects"] + audit["excludedFieldMoveObjects"] + audit["excludedStoryObjects"])
        self.assertEqual(audit["excludedTrainerBindings"], 881)
        self.assertEqual(audit["excludedTrainerTypeObjects"], 139)

    def test_route36_literal_has_exact_reviewed_rom_provenance(self):
        entry = self.entries[ROUTE36_KEY]
        self.assertEqual(entry["sourceScript"], "0x746460")
        self.assertEqual(entry["sourceText"], "0x7464c0")
        self.assertEqual(hashlib.sha256(entry["message"].encode()).hexdigest(), ROUTE36_MESSAGE_SHA)
        self.assertEqual(entry["branchCost"], 0)

    def test_multiline_text_and_dynamic_tokens_are_safe_and_audited(self):
        multiline = 0
        player_tokens = 0
        for key, entry in self.entries.items():
            message = entry["message"]
            self.assertTrue(message.strip(), key)
            self.assertLessEqual(len(message), 1800, key)
            self.assertFalse(any(ord(ch) < 32 and ch != "\n" for ch in message), key)
            tokens = set(TOKEN_RE.findall(message))
            self.assertEqual(tokens, set(entry.get("dynamicTokens", [])), key)
            self.assertFalse(tokens - ALLOWED_TOKENS, key)
            rendered = render(self.content, {"party": [], "creatures": []}, "DialogueAudit", entry["map"], entry["npc"])
            self.assertIsNotNone(rendered, key)
            self.assertFalse(TOKEN_RE.search(rendered), key)
            multiline += "\n" in message
            player_tokens += "{PLAYER}" in message
        self.assertGreater(multiline, 1000)
        self.assertGreater(player_tokens, 100)

    def test_center_and_mart_services_keep_actions_while_using_rom_greetings_when_available(self):
        nurse_total = nurse_dialogue = 0
        for map_id, center in self.world.get("centers", {}).items():
            if not map_id.startswith("johto_"):
                continue
            for npc in center.get("nurseNpcIds", []):
                nurse_total += 1
                nurse_dialogue += f"{map_id}:{npc}" in self.entries
        mart_dialogue = 0
        for key, entry in self.entries.items():
            obj = next(o for o in self.world["maps"][entry["map"]]["objects"] if o["id"] == entry["npc"])
            mart_dialogue += obj["graphics"] == 68
        self.assertEqual((nurse_total, nurse_dialogue), (33, 31))
        self.assertEqual(mart_dialogue, 47)

    def test_renderer_substitutes_owner_context_and_keeps_johto_source_identity(self):
        key, entry = next((key, entry) for key, entry in self.entries.items() if "{PLAYER}" in entry["message"])
        map_id, npc = key.rsplit(":", 1)
        state = {"party": [], "creatures": []}
        rendered = render(self.content, state, "AkumaVenom", map_id, int(npc))
        self.assertIn("AkumaVenom", rendered)
        self.assertNotIn("{PLAYER}", rendered)
        self.assertEqual(entry.get("sourceRegion"), "johto")
        self.assertIsNotNone(render(self.content, state, "AkumaVenom", "kanto_4_0", 1))


class RuntimeDialogueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        config = Path(self.temp.name) / "config.ini"
        config.write_text((ROOT / "Build/config_templates/Server/config.ini").read_text(encoding="utf-8"), encoding="utf-8")
        settings = Settings.load(config)
        settings.config.set("database", "backend", "sqlite")
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.content = Content(ROOT / "Server/data/world.json")
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.content, self.db, self.settings)
        state = self.world.initial("AkumaVenom", "Johto", "fr_152", 0)
        uid = self.db.create("AkumaVenom", "unused", state)
        self.player = await self.world.join(uid, "AkumaVenom", state, asyncio.Queue(maxsize=2048))
        self.drain()

    async def asyncTearDown(self):
        self.world.players.clear()
        self.db.close()
        self.temp.cleanup()

    def drain(self):
        packets = []
        while not self.player.queue.empty():
            packets.append(self.player.queue.get_nowait())
        return packets

    async def place(self, map_id, npc):
        obj = next(o for o in self.content.maps[map_id]["objects"] if o["id"] == npc)
        state = copy.deepcopy(self.player.state)
        state.update(map=map_id, x=obj["x"], y=obj["y"], surf=False)
        await self.world.commit(self.player, state)
        self.drain()
        return obj

    async def test_clicking_ordinary_route36_npc_returns_rom_text(self):
        await self.place("johto_2_23", 1)
        await self.world.dispatch(self.player, {"op": "npc", "map": "johto_2_23", "npc": 1})
        dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
        expected = render(self.content, self.player.state, self.player.username, "johto_2_23", 1)
        self.assertEqual(dialog["message"], expected)
        self.assertEqual(dialog["actions"], [])

    async def test_real_johto_trainer_preview_remains_species_and_levels_not_rom_dialogue(self):
        trainer = next(t for t in self.content.data["adventureRom"]["trainers"].values() if t["map"].startswith("johto_") and t["team"])
        await self.place(trainer["map"], trainer["npc"])
        await self.world.dispatch(self.player, {"op": "npc", "map": trainer["map"], "npc": trainer["npc"]})
        dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
        self.assertEqual(dialog["title"], trainer["name"])
        self.assertIn("battle", dialog["actions"])
        for member in trainer["team"]:
            expected = f"{self.content.species[member['species']]['name']} Lv. {member['level']}"
            self.assertIn(expected, dialog["message"])
        self.assertNotIn(f"{trainer['map']}:{trainer['npc']}", self.content.data["npcDialogue"]["entries"])


    async def test_real_johto_gym_leader_preview_remains_existing_team_ui(self):
        trainer = next(t for t in self.content.data["adventureRom"]["trainers"].values() if t["map"].startswith("johto_") and t["team"] and self.world.adventure.gym(t))
        await self.place(trainer["map"], trainer["npc"])
        await self.world.dispatch(self.player, {"op": "npc", "map": trainer["map"], "npc": trainer["npc"]})
        dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
        self.assertEqual(dialog["title"], trainer["name"])
        self.assertIn("Gym challenge.", dialog["message"])
        self.assertIn("battle", dialog["actions"])
        for member in trainer["team"]:
            expected = f"{self.content.species[member['species']]['name']} Lv. {member['level']}"
            self.assertIn(expected, dialog["message"])
        self.assertNotIn(f"{trainer['map']}:{trainer['npc']}", self.content.data["npcDialogue"]["entries"])

    async def test_mart_clerk_keeps_shop_action_and_uses_sigma_greeting(self):
        entries = self.content.data["npcDialogue"]["entries"]
        candidate = next((entry["map"], entry["npc"]) for entry in entries.values()
                         if entry["map"].startswith("johto_") and next(o for o in self.content.maps[entry["map"]]["objects"] if o["id"] == entry["npc"])["graphics"] == 68)
        map_id, npc = candidate
        await self.place(map_id, npc)
        await self.world.dispatch(self.player, {"op": "npc", "map": map_id, "npc": npc})
        dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
        self.assertEqual(dialog["title"], "Poke Mart")
        self.assertIn("shop", dialog["actions"])
        self.assertEqual(dialog["message"], render(self.content, self.player.state, self.player.username, map_id, npc))

    async def test_nurse_keeps_heal_action_and_uses_sigma_greeting(self):
        candidate = next((map_id, npc) for map_id, center in self.content.data["centers"].items() if map_id.startswith("johto_") for npc in center.get("nurseNpcIds", []) if f"{map_id}:{npc}" in self.content.data["npcDialogue"]["entries"])
        map_id, npc = candidate
        await self.place(map_id, npc)
        await self.world.dispatch(self.player, {"op": "npc", "map": map_id, "npc": npc})
        dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
        self.assertIn("heal", dialog["actions"])
        self.assertEqual(dialog["message"], render(self.content, self.player.state, self.player.username, map_id, npc))


if __name__ == "__main__":
    unittest.main()
