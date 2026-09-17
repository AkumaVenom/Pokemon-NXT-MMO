# GBA Battle System Completion

Release: **0.6.8-alpha · GBA Battle System Completion**

Pokemon NXT's battle runtime is server-authoritative. This release replaces the earlier partial move-effect layer with a ROM-backed Gen-III singles implementation driven by reviewed FireRed Rev 1 and Ultra Shiny Gold Sigma 1.5.0 battle metadata. Clients request an action; the server owns legal-move checks, PP, order, accuracy, damage, status, volatile state, switching, battle termination, experience and durable rewards.

## Reviewed ROM inputs

The ROMs are development inputs only. They are never copied into a build or required at runtime.

| Source | Size | SHA-256 |
| --- | ---: | --- |
| FireRed USA/Europe Rev 1 | 16,777,216 bytes | `729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059` |
| Ultra Shiny Gold Sigma Completo 1.5.0 | 17,632,785 bytes | `62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64` |

`Tools/extract_battle_mechanics.py` is a bounded static extractor. It verifies both hashes before reading reviewed GBA tables and never executes ROM code. The generated `Server/data/battle_mechanics.json` records source offsets/raw move bytes so shipped mechanics can be audited without redistributing either ROM.

## Published battle data

The runtime publishes **361 selectable move records**: all **354 canonical FireRed move IDs** plus **7 separately identified Sigma aliases** already used by NXT content. Those records represent **198 active move-effect IDs** in the published move corpus. All 361 records are covered by a one-turn execution regression that requires every move to resolve without an exception.

For moves, the extractor publishes native effect ID/name, base power, type, accuracy, PP, secondary chance, target byte, priority, flags, category byte, source move ID, source ROM hash, table offset and raw 12-byte record. Canonical FireRed physical/special category follows the Gen-III type split. The seven reviewed Sigma aliases retain their native Sigma category byte and source identity instead of silently overwriting the canonical FireRed move with the same raw slot number.

For all **877 published species profiles**, the extractor also records the selected ROM base-stat source fields needed by combat: gender ratio, base friendship, ability IDs and held-item IDs. FireRed Pokédex weights are used for Low Kick where an exact reviewed identity exists; matching Sigma identities reuse that exact FireRed value.

## Implemented move-system scope

The engine covers the active Gen-III move-effect families used by the two source sets, including ordinary and multi-hit damage; accuracy/evasion; critical stages; stat changes and screens; weather; major status; confusion, Attract and volatile effects; residual damage/recovery; trapping; Substitute; Protect/Endure; fixed and variable damage; OHKO moves; recoil/drain; two-turn and forced-repeat moves; Bide; Counter/Mirror Coat; priority; recharge; Transform/Mimic/Sketch; Disable/Encore/Spite; Metronome/Mirror Move/Sleep Talk/Assist; Nature Power/Secret Power/Camouflage; Hidden Power; Return/Frustration/Present; Future Sight/Wish/Yawn/Perish Song; Stockpile/Spit Up/Swallow; Baton Pass; Rapid Spin; Trick/Thief/Knock Off/Recycle; Role Play/Skill Swap/Imprison; Magic Coat/Snatch; Focus Punch; Endeavor; Eruption; Low Kick; Weather Ball; and the remaining active FireRed move-effect families represented in the published table.

This release also preserves source-specific rules that were previously easy to approximate incorrectly: FireRed's rounded accuracy-stage table, strict OHKO threshold, Psywave's 4-bit rejection/10%-step distribution, Present's byte thresholds, lower-level wild Roar/Whirlwind check, Protect/Endure chain cap, move-copy/call exclusions, Thunder paralysis, Charge duration, dynamic Hidden Power/Weather Ball type propagation, Foresight immunity/evasion handling, and owner-side terrain selection for Nature Power, Secret Power and Camouflage.

Battle terrain is selected authoritatively by the world from the player's current map/tile/surf state. No client terrain label can choose a different Nature Power, Secret Power or Camouflage result.

## Autonomous temporary-move compatibility hotfix

The accepted 0.6.8 release includes a runtime correction for autonomous wild battles. The battle engine can expose a temporary move list that differs from the saved creature record: **Transform** copies the opponent's current move slots and **Mimic** can replace a move for that battle only. `Battle.usable()` returns indices into that temporary battle view. Autonomous move scoring must therefore read the same current battle view rather than `mon['moves']`.

The previous scorer mixed those two representations. A one-move Ditto that transformed into a four-move opponent produced legal slots `[0, 1, 2, 3]`, then attempted to read slots 1-3 from Ditto's one-entry persistent list and raised `IndexError` from the world tick. The corrected scorer uses the battle-authoritative move view and transformed type view for evaluation, while leaving the persistent Pokémon record untouched. A bounded valid-slot fallback prevents future temporary-move extensions from escalating one legal AI action into a periodic world-service exception.

This changes no move data, damage rules, save format, content pack, database schema, bot population or scheduler cadence.

## Preserved MMO contracts

The update does not replace or bypass NXT's persistence/replication architecture. Wild, story, trainer, Gym Leader, player duel and autonomous-trainer battles use the same server battle runtime. Bot population batching and zero-routine-population-reload behavior from v0.6.4 remain intact. Route 36 Sudowoodo, owner-only Cut/story collision, both regional NPC dialogue layers, Pokémon Center/Goldenrod portal fixes, PC/trade ownership, varieties, growth and learnset persistence stay in place.

Newly created Pokémon now keep a stable 32-bit personality value used by Gen-III-style gender/ability selection, source base friendship and the ROM-held-item roll. Existing Pokémon remain compatible: records without these additive fields use stable/default fallbacks, so no database schema reset or player-save wipe is required.

## Deliberate boundaries

This is a **high-fidelity server implementation, not a cycle-perfect GBA emulator**. The following boundaries are explicit rather than guessed:

- Pokemon NXT currently runs **single battles**. FireRed's doubles-only Follow Me and Helping Hand semantics have no valid ally/target topology here, so those moves fail cleanly instead of receiving fabricated singles behavior.
- **491 Sigma hack-expanded identities** do not have a safely reviewed Pokédex-weight mapping. Their exact Low Kick weight cannot be derived from the reviewed tables, so they carry an explicit `unknown-fallback` weight. FireRed identities and safely name-matched Sigma identities use ROM-backed weights.
- The move-effect layer is substantially complete for the published FireRed/Sigma move corpus, but this release does **not** claim every GBA engine quirk, every held-item restriction, every ability edge case, double-battle targeting, animation script or RNG-instruction sequence is bit-identical to cartridge execution.
- Capture mechanics and battle graphics/audio presentation are NXT systems and are not claimed to be ROM-emulator implementations by this document.

These limits are kept visible so future refinements can improve a specific reviewed edge case without silently changing unrelated gameplay.

## Reproducible extraction

From a source checkout with the two reviewed ROMs available locally:

```text
python Tools/extract_battle_mechanics.py --firered <FireRed.gba> --sigma <Sigma.gba>
python Tools/repack_content.py --root .
```

The normal source build does **not** execute this extraction and does not need either ROM. It consumes the already audited generated JSON and source assets.
