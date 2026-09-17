# Item Gameplay Repair

Release: **0.6.10-alpha** · Date: **2026-09-18**

## Scope and correction

The 0.6.9 implementation correctly collected map items but did not supply their complete gameplay actions. This release fixes that missing integration. All 125 unique pickup identities have explicit action contracts. The catalog has 128 original definitions plus one crafted Fast Ball. It is an additive replacement over the complete 0.6.9 source, not a new database or a new set of map pickups.

## Player actions

**Capture:** in a wild battle choose `Battle item`, select the owned ball, and explicitly confirm the throw. Timer Ball starts at 1× on turn 1, reaches 2.1× on turn 12 and caps at 4× on turn 31; the display uses server-computed modifiers. Repeat Ball consults caught history, not seen history. Net Ball checks Water/Bug typing, Dive Ball requires underwater terrain, Nest Ball uses level, Master Ball guarantees wild capture, and Luxury Ball records its friendship effect. Trainer capture is rejected. A failed legitimate capture spends exactly one ball. Captured creatures retain the ball identity.

**Medicine and training:** choose the owned Pokémon rather than implicitly affecting the lead. Battle targets are restricted to the battle party; field targets are owned creatures. Revives select fainted partners. Ether/Max Ether and PP upgrades select the move. PP Up/Max never exceed three upgrades; healed PP respects the new cap. Vitamins use the GBA 100-per-vitamin-stat and 510-total EV caps; earned EVs have a 255 per-stat cap. Rare Candy advances native growth/learn/evolution logic. No-effect and incompatible uses do not consume inventory.

**Machines and evolution:** `Teach…` shows compatible Pokémon and a specific slot to replace. Existing knowledge is not duplicated. TMs are consumed only after success; HM09 is reusable. `Evolve…` lists actual compatible outcomes for that token. The source's unusual HM09/Sing assignment is preserved rather than replaced with guessed vanilla data.

**Held items:** use `Give to Pokémon…`; use `Take held item` on the Pokémon detail panel to return it. Exchanges return the previous item before committing. A full return stack is rejected atomically. Existing holders retain `(source, native ID)` identity, and uncatalogued old Kanto identities roundtrip through a labeled reserve instead of disappearing. Source namespace follows Trick, Thief, Knock Off and Recycle. Equip Flame Ball for its Fire boost; it is not a capture ball.

**Field/services:** Repels count accepted steps and survive map transitions/relogin; an unsuccessful step does not consume protection. The last protected step is still protected. Escape Rope checks the source map's permission and a recorded safe entry before moving/consuming. Valuables have a real clerk-only sale action. Poké Flute, Blue/Yellow Flutes and Sacred Ash use their explicit party/status contexts. Rotom Pad opens existing records; SquirtBottle retains the Route 36 story action.

## Source evidence and reproduction

Extraction input is the exact user-supplied **Ultra Shiny Gold Sigma Completo 1.5.0** ROM: SHA-256 `62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64`, 17,632,785 bytes. The extractor verifies that identity, bounds reads, and never executes ROM code. Neither a ROM nor an emulator is required for ordinary builds/runtime; the ROM is not packaged.

`Server/data/item_mechanics.json` records native names/prices/held-role bytes and relevant function/table pointers, the exact referenced machine table at `0x45A80C`, 64-bit compatibility masks at `0xA91D80`, EV yields, 81 item-evolution edges and source map flags. The stale vanilla machine table at `0x45A5A4` is intentionally not used. Machine assignments are TM01/Superpower, TM02/Headbutt, TM05/Roar, TM12/Sweet Scent, TM17/Protect, TM21/Whirlpool, TM36/Sludge Bomb, TM48/Thunderbolt, and HM09/Sing. Source compatibility can be unusual; it is not broadened by guessing.

Developer reproduction, with the exact ROM supplied locally:

```text
python Tools/extract_item_mechanics.py "path/to/the/reviewed/Sigma.gba"
python Tools/repack_content.py
```

For a normal content rebuild, only the second command is required. The publisher requires complete explicit item/species metadata, validates source IDs and move IDs, and hashes the final matched server/client pack. Stable persisted item/species/map keys are not renamed.

## Native evidence versus NXT adaptations

A native item name alone is not proof of later-generation behavior. This source reuses older hold-effect IDs for renamed objects. Verified role mappings include **Sticky Barb → Clamperl Special Defense ×2**, **Enigma Stone → Latios/Latias Special Attack and Special Defense ×1.5**, **Rose/Odd Incense → 5% incoming-accuracy reduction**, and **Flame Ball/Dragon Bone → type boosters**. They deliberately do not receive unrelated later-generation effects just because the name matches.

The following are authored NXT implementations and are marked in the per-item audit, not presented as exact cartridge behavior:

- Choice Scarf and Power Anklet/Band/Lens use their named Speed/choice-lock or +4 training-EV roles. Wide Lens follows the described accuracy boost; Destiny Knot follows this source's Fairy-boost description by boosting published source type 9, including Moonblast/Dazlinggleam; it does not target nonexistent type 18 or rename the global type table. Dragon Shell is a reviewed Seadra/Kingdra evolution alias.
- **White Apricorn:** Kurt, in the real Azalea house `johto_34_13`, exchanges one for a Fast Ball immediately. NXT Fast Ball gives 4× for species base Speed ≥100, otherwise 1×; the cartridge crafting wait and its full historical ball quirks are not recreated.
- **Coin Case:** a persisted wallet with an explicit Poké Mart coin/prize exchange. There is no slot machine or gambling game.
- **Pokéblock Case:** consumes a Lum or Sitrus Berry to make a block, then feeds a selected owned Pokémon for condition/sheen/friendship. There is no full Berry Blender or contest minigame.
- **Tera Orb:** once per non-duel battle alongside an attack, changes the selected active Pokémon to its primary original species type for defense and appropriate STAB until battle end. The Orb is not consumed. This is not the complete later-generation Tera type selection, recharge and interaction system.

## Safety and known boundaries

All effect parameters, prices, compatibility, capture RNG, owner targets, map services and limits come from authoritative content/state, never the client. Field item commands run under the existing world lock, operate on detached copies, and commit inventory plus outcome together. Persisted request receipts reject duplicate/payload-reused submissions. A failed database write leaves both item and effect unchanged. Battle items use the battle snapshot transaction and cannot be smuggled through field-use during a battle/trade/freeze.

Skill Capsule switches only distinct regular ability slots and **rejects destination ability IDs outside 1–77 without consumption**. The existing engine does not implement the full expanded Sigma/later-generation ability corpus; this update does not disguise a switch into those unsupported IDs as a working new ability. Existing ability-edge limitations remain. PP restoration while transformed is explicitly rejected until switching out, preserving persistent move PP rather than mutating the wrong temporary move set. Original full story/minigames, doubles-only effects, and existing unresolved-weight cases remain outside this repair.

No SQL schema bump/reset is needed. New state fields are additive. Existing move lists retain their packet shape; absent `ppUps` means zero without gratuitous save rewrites. Already-collected items become usable in place; players do not need to recollect balls. Back up production database/configuration, stop the old process, deploy matching rebuilt server and client, and retain the configured database. Native Windows/Edge operation is not certified by Linux or bridged-DOM tests.

## Validation entry points

```text
python -m unittest discover -s Tests
python -m unittest discover -s Tests -p test_item_mechanics.py -v
node --test Tests/check_adventure_ui.mjs
python Tests/check_items_browser.py
```

The last command needs Playwright/aiohttp and an installed Chromium selected through `NXT_BROWSER_PATH`; it uses disposable accounts/database. `NXT_QA_BRIDGE=1` selects the repository's local DOM/asset fixture with real aiohttp WebSocket transport when native navigation is unavailable. It does not alter browser policy. Bridged transport is explicitly distinguished from native browser/Edge acceptance in the report.

## Reference code

The supplied ROM's hash-pinned records are the source of Sigma-specific identity. Reviewed primary reference code for the inherited GBA mechanics:

- pret/pokefirered `src/battle_script_commands.c`: https://raw.githubusercontent.com/pret/pokefirered/master/src/battle_script_commands.c
- pret/pokefirered `include/constants/hold_effects.h`: https://raw.githubusercontent.com/pret/pokefirered/master/include/constants/hold_effects.h
- pret/pokefirered `include/global.fieldmap.h`: https://raw.githubusercontent.com/pret/pokefirered/master/include/global.fieldmap.h
- pret/pokefirered `include/constants/abilities.h`: https://raw.githubusercontent.com/pret/pokefirered/master/include/constants/abilities.h

See `ITEM_GAMEPLAY_COVERAGE.json` for the full per-item matrix and `ITEM_GAMEPLAY_TEST_REPORT.md` for actual executed checks. Native evidence and authored adapters remain separate in those artifacts.
