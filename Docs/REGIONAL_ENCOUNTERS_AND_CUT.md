# Regional encounters and personal HM Cut

## Release and upgrade

Gameplay **0.3.4-alpha**, based on the supplied **0.3.3-alpha BattleScreenFix** source. Build tools remain **1.3.3**; this release extends their source-data allowlist and required-file checks. Both Client and Server must be rebuilt/deployed together. The pack handshake rejects an older client.

Back up your working source and database. Extract both full-source ZIP parts into the same directory, merging their identically named project folders, then run `BUILD_ALL.bat`. The complete source includes all existing assets; neither original ROMs nor an audio re-render is required. The optional small patch is an alternative for the exact uploaded 0.3.3 baseline, not an additional prerequisite for the full source.

Build to a fresh output folder. Preserve your working Server/config.ini, database, certificates/private keys, client connection settings and deployment files. Do not replace these with clean templates or rerun MySQL setup merely to update. No account reset, destructive schema migration or credential change is part of this release. Old saves acquire validated Cut state during ordinary login; already-earned regional badges are recognized without a gym rematch.

## Normal encounters

The previous terrain fallback manufactured starter-area Pokémon for maps without recovered tables. It is removed from both preparation and live runtime. All **959 map IDs** now have an explicit, audited binding: **248** contain ordinary encounter pools (including two zone-only maps), and **711** intentionally do not. A house, gym, laboratory or map without a verified counterpart does not silently inherit Sentret/Hoothoot.

Kanto uses the **124 original FireRed table records** already extracted into the supplied pack, preserving slot order, species, level ranges and method separation. This includes the additional FireRed areas in the asset set. Existing Sigma maps which explicitly duplicate Kanto locations also receive their matching FireRed tables; bindings use stable map IDs, never runtime name guessing. There are **177 default FireRed bindings** including those duplicates.

The Johto locations use **78 normalized Crystal location/floor tables**, with morning/day/night grass slots and water where applicable. There are **69 default Crystal bindings**, plus two zone-only bindings. Routes 26–28, Tohjo Falls, Victory Road and Mt. Silver use their Crystal progression tables rather than inappropriate starter lists. A species' rarity and level are independent of the player's party strength; rare low-level slots in late areas remain low-level when Crystal specifies them.

### Time, terrain and probabilities

Crystal time follows the **world server's local clock**, not a client-provided time: morning 04:00–09:59, day 10:00–17:59, night 18:00–03:59. Keep the server OS timezone consistent with the schedule desired for the world. Periods are resolved for each encounter, so a restart is not required when the time changes. FireRed pools have no invented day/night split.

FireRed grass uses twelve ordered weights `20,20,10,10,10,10,5,5,4,4,1,1`; its Surf pool uses `60,30,5,4,1`. Crystal grass uses seven slots `30,30,20,10,5,4,1`; Surf uses `60,30,10`. Repeated species entries are retained, because their levels and probabilities may differ. FireRed slot level ranges use uniform selection. Crystal Surf keeps its base through base+4 distribution with integer weights `89,76,51,26,14` (256 total), preserving the original byte-threshold/rejection behavior's distribution.

Walking, cave-floor and Surf eligibility are resolved on the authoritative server at the player's actual tile. Water requires Surf and a water table; it never falls back to land Pokémon. Explicit cave/floor bindings permit the relevant floor behaviors. Warp cells, blocked terrain, Centers and Gyms do not become wild-search shortcuts. Both automatic walking encounters and the manual search button use the same resolver. Client requests cannot supply the species, level, encounter method or clock.

The existing configurable MMO per-step encounter chance and cooldown remain in force. This update corrects the ordered species/level distributions, not the original cartridge's frame-by-frame step RNG, repel/ability effects or map-rate execution. Original rate metadata is retained for future work.

### Existing Sigma geometry

Johto's maps are still the supplied **Sigma layouts**, not newly imported Crystal graphics. Some maps combine multiple floors; explicit half-open tile rectangles select the correct floor table. Sprout Tower's combined entry floor stays encounter-free; its second and third floors use their respective tables. The laboratory beneath a merged Ruins of Alph chamber stays encounter-free. Slowpoke Well, Whirl Islands, Mt. Silver and Ice Path have documented subareas rather than one whole-map starter list. Tin Tower's ordinary encounter floors share Crystal's matching pool. Extended Sigma Victory Road rooms use the Crystal Victory Road table; Ice Path's additional exit geometry has an explicit authoring adaptation.

`ENCOUNTER_CUT_AUDIT.json` is the exhaustive per-map record, with source table, intentional no-pool reason, zone rectangles and every Cut-tree position. `Server/data/encounter_bindings.json` is the editable authority. Sigma-only Hoenn/Alola/other extra locations without a FireRed/Crystal counterpart are explicitly left without invented pools. This is not a reconstruction of every hack-specific encounter table.

**Special events are not added by this release.** Fishing and Rock Smash data already present in the FireRed catalog are retained but their gameplay is not implemented here. Headbutt, Bug-Catching Contest, swarms, roaming Pokémon, fixed legendary encounters, Safari-specific capture rules and original story encounter gates are separate systems. Ruins of Alph gets the ordinary Unown chamber pool, not a recreation of its puzzle/letter-unlock scripts. This distinction matters when comparing a complete cartridge walkthrough to the MMO.

## Automatic regional Cut

| Current source region | Required victory | Saved badge | Scope |
|---|---|---|---|
| Kanto | Misty, Cerulean Gym | `kanto_2` / Cascade Badge | Kanto-map Cut trees |
| Johto | Bugsy, Azalea Gym | `johto_2` / Hive Badge | Johto-map Cut trees |

The starting region and chosen starter do not substitute for the badge check. Winning either region's second gym unlocks that region's Cut field ability; winning the other second gym unlocks the other. Total badge count is not a shortcut. The existing world uses `kanto_*` and `johto_*` source banks: the latter includes Sigma's retained duplicate Kanto scenery, and those objects follow their Johto-bank license. It is not silently reclassified from a duplicate location name.

The original games obtain HM01 separately from the badges' permission to use Cut outside battle. The requested MMO behavior deliberately grants the **field ability automatically at the badge win** instead. No HM inventory item, compatible-party search or forced replacement of a Pokémon's four combat moves is needed. The journal shows both regional licenses and requirements. A successful qualifying gym victory includes the unlock in the same saved progression transaction; a loss or failed save does not grant it.

Approach a small HM tree and click its sprite (or use the existing nearby-interact key **E**). The dialogue explains the requirement. Its **Cut tree — locked** button is visibly disabled with accessibility state while locked. Once licensed, **Cut tree** sends one map-scoped interaction and waits for the server; the client does not hide the tree optimistically.

## Personal trees, collision and persistence

All **120 graphic-95 HM-tree objects** in the published pack use the shared Cut interaction. Rocks (96), Strength boulders (97), other NPCs and ordinary scenery are not changed. Cutting records the stable map/object ID pair in the owner's `adventure.cutTrees`. The server validates current map, object type/identity, nearby distance, the correct badge and whether the character is busy. Requests from an old map/menu are rejected; repeat cuts are idempotent.

The save succeeds **before** the tree disappears or success is announced. Failure leaves the previous state and obstacle intact. Only the owning player's private state includes the cut flags; nearby player/scene packets do not broadcast them. The client removes that tree's sprite and mouse-hit target from its own renderer. The authoritative movement resolver removes the exact tree cell's obstruction for that character, while retaining water, elevation and other objects' collision rules. The shared map grids are not modified.

Another account still sees and collides with its own tree until it qualifies and cuts it. Cut flags survive movement, map changes, relogging and normal stored-state reloads. They are **permanent personal clearing**, not a global respawn timer or a single-player-style map-reentry reset. Logging out resets the renderer so another account cannot inherit the former account's hidden objects. Migration filters invalid map IDs/object IDs and cannot turn arbitrary saved flags into wall/rock removal.

## Nidoran identity correction

A baseline name-normalization collision merged Nidoran♂ into Nidoran♀. Ordinary FireRed/Crystal encounters need both. The existing unused male art and original catalog facts restore stable key `fr_32`; female `fr_29` remains unchanged as an identity. Six FireRed male slots and eight source-ID-32 trainer entries are corrected. Native learnset provenance and existing cry binding are restored, and both level-16 evolution identities are separated correctly.

Existing captured creatures are not guessed into a different sex/species. The catalog now has **877 entries and 877 audited learnsets** (875 validated, two independently bounded recoveries), with **322 supported evolution rules across 318 species**. Historical 0.3.1 reports describe their original 876-profile baseline rather than the additive identity repair.

## Maintaining and validating the source

`Tools/repack_content.py` applies adventure/interior repairs, the additive species identity and native learning data, then exhaustive encounter bindings before calculating the shared content-pack hash. Startup and publication use the same table/zone validator. Missing/stale map bindings, unsupported species, malformed weights, out-of-bounds or overlapping zones fail closed. The original assets are not re-rendered. Build source snapshots must retain all four new JSON sidecars, the publisher and runtime modules; the allowlist and required-source regression test enforce this.

```sh
python Tools/repack_content.py
python -m unittest discover -s Tests -v
node --test Tests/check_adventure_ui.mjs Tests/check_renderer_replication.mjs
```

The normalized Crystal catalog can also be compared to `Tools.crystal_encounter_catalog.build(species)` without a network or ROM. The automated test suite performs this comparison. See `REGIONAL_ENCOUNTERS_CUT_TEST_REPORT.md` for executed results and platform boundaries.

## Reference data

The supplied FireRed extraction remains the source of the FireRed tables and ROM-derived assets. The following primary disassembly/decompilation files were checked on 2026-09-13 for the factual game data and badge rules. Normalized factual encounter data is included locally; runtime/build do not fetch these URLs.

- FireRed tables: https://github.com/pret/pokefirered/blob/master/src/data/wild_encounters.json
- FireRed Misty and HM01 events: https://github.com/pret/pokefirered/blob/master/data/maps/CeruleanCity_Gym/scripts.inc and https://github.com/pret/pokefirered/blob/master/data/maps/SSAnne_CaptainsOffice/scripts.inc
- Crystal ordinary tables: https://github.com/pret/pokecrystal/tree/master/data/wild (johto_grass.asm, johto_water.asm, kanto_grass.asm, kanto_water.asm, probabilities.asm)
- Crystal level selection and byte-percent macro: https://github.com/pret/pokecrystal/blob/master/engine/overworld/wildmons.asm and https://github.com/pret/pokecrystal/blob/master/macros/data.asm
- Crystal Bugsy and HM01 events: https://github.com/pret/pokecrystal/blob/master/maps/AzaleaGym.asm and https://github.com/pret/pokecrystal/blob/master/maps/IlexForest.asm

Exact locally shipped catalog digests are recorded in the generated audit and `world.encounterPolicy.sources`. Original ROMs are not distributed. Existing third-party notices remain applicable.
