# Johto / Sigma NPC dialogue restoration

Release: **0.6.6-alpha · Johto Sigma NPC Dialogue Restoration**  
Source revision: **Pokemon Ultra Shiny Gold Sigma Completo 1.5.0**  
Reviewed ROM SHA-256: `62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64`  
Reviewed ROM size: **17,632,785 bytes**

## What changed

Ordinary visible NPC interaction in the Johto / Sigma map set now uses dialogue recovered from the reviewed GBA ROM instead of the previous generic NXT exploration sentence whenever a safe static talk literal could be established. The published content contains **2,158 validated dialogue entries across 534 Johto / Sigma maps**.

The extraction audit covers **4,429 visible source objects**. NXT intentionally excludes **881 existing trainer bindings**, **139 additional trainer-type objects**, **284 Cut objects**, and the **1 authored Route 36 Sudowoodo story object** from dialogue replacement. This preserves the gameplay UI already attached to those objects.

Of the remaining **3,124 eligible objects**, **2,158** have a validated static dialogue literal, **166** do not expose a readable script pointer, and **800** do not yield a safe literal through the bounded static script paths supported by this extractor. The latter set includes props, special/native-script objects, signs/effects and conditional interactions whose correct runtime state cannot be reconstructed safely from one click without executing more of the original engine. Those objects keep NXT's existing controlled fallback instead of receiving guessed text.

## Trainer and Gym Leader contract

Trainer and Gym Leader interaction is deliberately unchanged. Their ROM talk text does **not** replace the existing NXT challenge dialog. Clicking one still shows the trainer name, Pokémon species and levels, and the existing battle action before the fight. This is enforced both by extraction policy and publish-time validation.

## Service NPCs

Service behavior remains authoritative in NXT:

- Nurse Joy keeps the existing **Heal** and eligible **PC** actions. When a validated Sigma greeting exists, that greeting is displayed in the same dialog.
- Poké Mart clerks keep the existing shop action while using their validated ROM greeting where available.
- Pokémon Center storage terminals keep the existing storage action. A ROM literal is used only when the same visible object has a validated text binding.
- Cut trees and the Route 36 Sudowoodo object continue to use their dedicated persistent owner-only interaction UI.

Dialogue is presentation data only; it cannot authorize healing, shopping, battles, story clears or field moves.

## Static extraction safety model

`Tools/extract_sigma_dialogue.py` is intentionally a **bounded static extractor**, not a GBA emulator and not a ROM script executor. It:

1. accepts only the exact reviewed Sigma ROM revision recorded in `Tools/extraction_manifest.json`;
2. walks known FireRed-family event instructions with bounded call depth and instruction-state limits;
3. follows both unknown conditional branches but prefers the ordinary fall-through/default route when selecting a literal;
4. decodes only validated text pointers and supported Gen III text controls;
5. preserves line and page breaks for the web dialogue UI while stripping formatting/audio control codes;
6. records source script, command, text and object offsets for every published entry; and
7. rejects trainer, trainer-type, authored story and Cut bindings before publication.

This release does **not** execute the original ROM's flags, native `special` functions, choice menus, cutscenes, arbitrary quest state or door/bridge scripts. Therefore a multi-state original NPC is represented by the safest statically reachable talk literal, not by a claim that the complete original event script has been reproduced.

## Dynamic text tokens

Player-name and party/species substitutions that can be mapped safely are rendered from the current NXT character at click time. A small number of source strings use ROM string variables normally filled by native/script state. When that value cannot be proven statically, NXT substitutes a conservative readable context value rather than exposing raw `{STR_VAR_*}` tokens or executing the ROM function that would have populated them.

Kanto interaction is not changed by this Sigma dialogue layer.

## Re-extraction for development

A normal source build **does not require the ROM**. The validated result is already bundled as `Server/data/johto_dialogue.json` and is republished into the signed content identity by `Tools/repack_content.py`.

For a developer audit with the exact reviewed ROM:

```text
python Tools/extract_sigma_dialogue.py "<path-to-reviewed-sigma-rom.gba>" --root .
python Tools/repack_content.py --root .
```

The extractor aborts if the supplied ROM hash or size differs. The ROM itself must never be copied into a source release, client, server build or source ZIP.

## Persistence and performance

This update requires **no database schema change, account reset or player-save migration**. Dialogue is immutable content attached to the world pack. Runtime lookup is a bounded dictionary lookup performed only when a player explicitly interacts with an NPC; it is not part of autonomous-trainer simulation, movement persistence or the 10 Hz world tick. The accepted v0.6.4 bot-performance architecture and the v0.6.5 Route 36 owner-only story state remain unchanged.

Build and deploy matching Client and Server outputs so their world pack identities agree. Keep the existing database, configured `Server/config.ini`, TLS material and player data.
