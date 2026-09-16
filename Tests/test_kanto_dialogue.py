"""Audited Kanto/FireRed regular NPC dialogue extraction and runtime behavior."""
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

FIRERED_SHA = "729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059"
PALLET_MOM_KEY = "kanto_4_0:1"
PALLET_MOM_MESSAGE_SHA = "cce02293872ff1126b65a5b05ea65c89d0b0929ec4b8f1c2b4c3463e8d95c16c"
REGULAR_NPC_GRAPHICS_MAX = 91
TOKEN_RE = re.compile(r"\{[A-Z0-9_]+\}")
ALLOWED_TOKENS = {
    "{PLAYER}", "{KUN}", "{RIVAL}", "{VERSION}", "{EVIL_TEAM}", "{EVIL_LEADER}", "{LEGENDARY}",
    "{EVIL_TEAM2}", "{EVIL_LEADER2}", "{LEGENDARY2}", "{LEAD_SPECIES}", "{PARTY_MON}", "{NUMBER}", "{STRING}",
    "{STR_VAR_1}", "{STR_VAR_2}", "{STR_VAR_3}",
} | {f"{{PARTY_MON_{i}}}" for i in range(1, 7)}


class PublishedKantoDialogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / "Server/data/world.json")
        cls.world = cls.content.data
        cls.sidecar = json.loads((ROOT / "Server/data/kanto_dialogue.json").read_text(encoding="utf-8"))
        cls.entries = {key: entry for key, entry in cls.world["npcDialogue"]["entries"].items() if key.startswith("kanto_")}

    def test_reviewed_firered_provenance_and_release_version_are_published(self):
        self.assertEqual(self.world["version"], "0.6.7-alpha")
        self.assertEqual(self.world["npcDialogue"]["format"], 2)
        self.assertEqual(self.sidecar["source"]["sha256"], FIRERED_SHA)
        self.assertEqual(self.sidecar["source"]["size"], 16777216)
        self.assertEqual(self.world["npcDialogue"]["sources"]["kanto"]["sha256"], FIRERED_SHA)
        self.assertFalse(self.world["npcDialogue"]["policies"]["kanto"]["scriptExecution"])

    def test_every_published_entry_targets_a_real_regular_nontrainer_kanto_npc(self):
        trainer_keys = set(self.world["adventureRom"]["trainers"])
        for key, entry in self.entries.items():
            self.assertEqual(key, f"{entry['map']}:{entry['npc']}")
            self.assertTrue(entry["map"].startswith("kanto_"), key)
            self.assertEqual(entry.get("sourceRegion"), "kanto", key)
            self.assertNotIn(key, trainer_keys)
            obj = next(o for o in self.world["maps"][entry["map"]]["objects"] if o["id"] == entry["npc"])
            self.assertFalse(obj.get("trainerType", 0), key)
            self.assertNotIn("storyEvent", obj, key)
            self.assertLessEqual(obj["graphics"], REGULAR_NPC_GRAPHICS_MAX, key)
            self.assertEqual(entry["sourceObjectIndex"], obj["sourceObjectIndex"], key)
            self.assertEqual(entry["sourceLocalId"], obj["sourceLocalId"], key)

    def test_audit_accounts_for_all_firered_visible_objects_and_regular_npc_scope(self):
        audit = self.sidecar["audit"]
        self.assertEqual(audit["visibleObjects"], 1620)
        self.assertEqual(audit["eligibleObjects"], 669)
        self.assertEqual(audit["dialogueEntries"], 642)
        self.assertEqual(audit["dialogueEntries"], len(self.sidecar["entries"]))
        self.assertEqual(audit["dialogueEntries"], len(self.entries))
        self.assertEqual(audit["withoutScriptPointer"], 25)
        self.assertEqual(audit["withoutValidatedLiteral"], 2)
        self.assertEqual(audit["excludedNonRegularObjects"], 498)
        self.assertEqual(audit["excludedTrainerBindings"], 413)
        self.assertEqual(audit["excludedTrainerTypeObjects"], 40)
        self.assertEqual(audit["eligibleObjects"], audit["dialogueEntries"] + audit["withoutScriptPointer"] + audit["withoutValidatedLiteral"])
        self.assertEqual(audit["visibleObjects"], audit["eligibleObjects"] + audit["excludedNonRegularObjects"] + audit["excludedTrainerBindings"] + audit["excludedTrainerTypeObjects"] + audit.get("excludedStoryObjects", 0))

    def test_pallet_mom_literal_has_exact_reviewed_rom_provenance(self):
        entry = self.entries[PALLET_MOM_KEY]
        self.assertEqual(entry["sourceScript"], "0x168c81")
        self.assertEqual(entry["sourceText"], "0x18d449")
        self.assertEqual(hashlib.sha256(entry["message"].encode()).hexdigest(), PALLET_MOM_MESSAGE_SHA)
        self.assertIn("{PLAYER}", entry["message"])

    def test_nonregular_item_and_field_objects_are_not_misrepresented_as_npc_speech(self):
        # Celadon rooftop Eevee is object graphics 92 and its source script contains
        # an acquisition/result string.  It must not be presented as regular speech.
        self.assertNotIn("kanto_10_11:2", self.entries)
        obj = next(o for o in self.world["maps"]["kanto_10_11"]["objects"] if o["id"] == 2)
        self.assertGreater(obj["graphics"], REGULAR_NPC_GRAPHICS_MAX)

    def test_dynamic_tokens_are_safe_and_owner_context_is_rendered(self):
        player_tokens = multiline = 0
        for key, entry in self.entries.items():
            message = entry["message"]
            self.assertTrue(message.strip(), key)
            self.assertLessEqual(len(message), 1800, key)
            self.assertFalse(any(ord(ch) < 32 and ch != "\n" for ch in message), key)
            tokens = set(TOKEN_RE.findall(message))
            self.assertEqual(tokens, set(entry.get("dynamicTokens", [])), key)
            self.assertFalse(tokens - ALLOWED_TOKENS, key)
            rendered = render(self.content, {"party": [], "creatures": []}, "AkumaVenom", entry["map"], entry["npc"])
            self.assertIsNotNone(rendered, key)
            self.assertFalse(TOKEN_RE.search(rendered), key)
            multiline += "\n" in message
            player_tokens += "{PLAYER}" in message
        self.assertGreater(multiline, 300)
        self.assertGreater(player_tokens, 20)
        self.assertIn("AkumaVenom", render(self.content, {"party": [], "creatures": []}, "AkumaVenom", "kanto_4_0", 1))

    def test_all_kanto_center_nurses_and_mart_clerks_keep_rom_greetings_available(self):
        nurses = [(map_id, npc) for map_id, center in self.world.get("centers", {}).items() if map_id.startswith("kanto_") for npc in center.get("nurseNpcIds", [])]
        self.assertEqual(len(nurses), 20)
        self.assertTrue(all(f"{map_id}:{npc}" in self.entries for map_id, npc in nurses))
        mart_entries = []
        for key, entry in self.entries.items():
            obj = next(o for o in self.world["maps"][entry["map"]]["objects"] if o["id"] == entry["npc"])
            if obj["graphics"] == 68:
                mart_entries.append(key)
        self.assertEqual(len(mart_entries), 21)


class RuntimeKantoDialogueTests(unittest.IsolatedAsyncioTestCase):
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
        state = self.world.initial("AkumaVenom", "Kanto", "fr_4", 0)
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

    async def test_clicking_ordinary_kanto_npc_returns_firered_text(self):
        await self.place("kanto_4_0", 1)
        await self.world.dispatch(self.player, {"op": "npc", "map": "kanto_4_0", "npc": 1})
        dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
        self.assertEqual(dialog["message"], render(self.content, self.player.state, self.player.username, "kanto_4_0", 1))
        self.assertIn("AkumaVenom", dialog["message"])
        self.assertEqual(dialog["actions"], [])

    async def test_real_kanto_trainer_and_gym_leader_keep_existing_team_preview_ui(self):
        trainers = [t for t in self.content.data["adventureRom"]["trainers"].values() if t["map"].startswith("kanto_") and t["team"]]
        ordinary = next(t for t in trainers if not self.world.adventure.gym(t))
        leader = next(t for t in trainers if self.world.adventure.gym(t))
        for trainer in (ordinary, leader):
            await self.place(trainer["map"], trainer["npc"])
            await self.world.dispatch(self.player, {"op": "npc", "map": trainer["map"], "npc": trainer["npc"]})
            dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
            self.assertEqual(dialog["title"], trainer["name"])
            self.assertIn("battle", dialog["actions"])
            for member in trainer["team"]:
                self.assertIn(f"{self.content.species[member['species']]['name']} Lv. {member['level']}", dialog["message"])
            self.assertNotIn(f"{trainer['map']}:{trainer['npc']}", self.content.data["npcDialogue"]["entries"])

    async def test_mart_and_nurse_keep_services_while_using_firered_dialogue(self):
        entries = self.content.data["npcDialogue"]["entries"]
        mart = next((entry["map"], entry["npc"]) for key, entry in entries.items() if key.startswith("kanto_") and next(o for o in self.content.maps[entry["map"]]["objects"] if o["id"] == entry["npc"])["graphics"] == 68)
        await self.place(*mart)
        await self.world.dispatch(self.player, {"op": "npc", "map": mart[0], "npc": mart[1]})
        dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
        self.assertEqual(dialog["title"], "Poke Mart")
        self.assertIn("shop", dialog["actions"])
        self.assertEqual(dialog["message"], render(self.content, self.player.state, self.player.username, *mart))

        nurse = next((map_id, npc) for map_id, center in self.content.data["centers"].items() if map_id.startswith("kanto_") for npc in center.get("nurseNpcIds", []))
        await self.place(*nurse)
        await self.world.dispatch(self.player, {"op": "npc", "map": nurse[0], "npc": nurse[1]})
        dialog = next(packet for packet in self.drain() if packet["type"] == "dialog")
        self.assertIn("heal", dialog["actions"])
        self.assertEqual(dialog["message"], render(self.content, self.player.state, self.player.username, *nurse))


if __name__ == "__main__":
    unittest.main()
