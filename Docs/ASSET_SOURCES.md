# Extracted asset sources and audit

These are the two exact ROM byte revisions used for the graphics, audio and v0.3.0 adventure extraction. The original extraction filenames below remain as provenance. The newly supplied FireRed `(8).gba` and Sigma `(5).gba` inputs have identical SHA-256 hashes. ROMs are not included in either release ZIP. The game loads the resulting PNG/JSON/audio data directly; no ROM is opened at runtime.

## Kanto

`Pokemon - FireRed Version (USA, Europe) (Rev 1)(5).gba`

Size: 16,777,216 bytes. Header revision: 1. Decoded map table: `0x352718`.

SHA-256:

```text
729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059
```

Imported 425 layouts, 437 raw sprite slots and 151 object-frame sheets. Raw slots include unused/duplicate/form entries; this is not a distinct-species count.

## Johto

`Pokemon Ultra Shiny Gold Sigma Completo 1.5.0(2).gba`

Size: 17,632,785 bytes. Header revision: 0. Decoded map table: `0x71c8ac`.

SHA-256:

```text
62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64
```

The original importer exported 434 layouts, 1339 raw sprite slots and 151 object-frame sheets. v0.3.0 recovers another 100 referenced Sigma layouts, bringing this source to 534 published maps. New Bark Town, Johto towns, their interiors and gym assets use the supplied Sigma tilesets and source object graphics. Raw slots include unused/duplicate/form entries; this is not a distinct-species count.

## Published native pack

The initial graphics pack was `0a8cdb1a321bac58cdfce7e6`: 10,902 PNG files, 859 maps and 876 filtered/deduplicated species entries. Those figures describe the original import, not the current release.

The v0.3.0 pack contains **959 maps** (425 FireRed + 534 Sigma), **11,110 PNG files** and the same **876 stable species keys**. Its pack hash is calculated from the final published data and recorded in `Server/data/world.json`; it changes when content changes. Every published species has front, back, shiny front, shiny back and icon asset paths validated by the build tests. Shared species retain canonical species art and identity; Johto map, tileset, NPC and regional music choices come from Sigma.

The binary decoding pipeline handles GBA pointers, LZ77 blocks, 4bpp tiles, BGR555 palettes, map blocks, primary/secondary tilesets, foreground layers, collision/elevation/behavior grids, object sprites, native connections/warps, species metadata and compatible moves/learnsets. Sigma relocates tables and includes additional content. The extractor preserves discovered source identifiers and documents warnings.

Some scanner warnings reflect probing beyond a valid table or rejecting unused slots; they are not a count of missing legitimate assets. Conversely, successful structural decoding is not proof of complete extraction of everything in either ROM. Original ARM/event code, story text systems, tile animations and additional unlocated/custom script resources are not shipped as an original game engine. The later audio update did extract and implement music, effects and cries; its provenance remains in `AUDIO_ASSET_REPORT.json` and `AUDIO_GUIDE.md`. The existing 818 Ogg clips and 1,548 cry WAV clips are preserved.

Original encounters were recovered from the structurally validated tables where possible; missing/custom data uses labeled alpha fallback encounters. v0.3.0 adds 463 validated native Sigma learnsets; 28 malformed/out-of-order/missing-level-one source lists retain labeled alpha templates. Party icons are used as followers rather than claiming complete directional overworld sprite coverage.

## Adventure extraction in v0.3.0

`Server/data/adventure_rom.json` records 1,294 validated trainer-to-NPC associations, all sixteen regional gym challenges, 321 supported evolution rules across 317 canonical species, 24 verified evolution items and the additional Sigma learnsets. Each party retains source trainer ID, species IDs, levels, move IDs, held-item metadata and ROM offsets. Every NPC association points to the normalized visible source object.

Source teams are not evidence that original event scripts, rematch flags, AI, held-item effects or prize formulas run unchanged. First-victory rewards, objective rewards and progression gates are authored MMO systems. Unresolved conditional trainers, double battles, unsupported moves/evolution methods and malformed source lists are listed explicitly in the sidecar. The six standard starter choices and shared species retain their stable canonical species identities.

Read `ADVENTURE_ROM_DATA.md` for exact source hashes, table offsets, normalization, extraction commands and limitations. `Server/data/interior_repairs.json` records the recovered-map and portal audit; `Tools/repair_interiors.py` implements the reproducible transform.

## Technical references

The implementation used primary format/decomposition references for the GBA FireRed structures, then decoded the supplied bytes. These references are not additional ROM downloads.

- [FireRed decompilation project](https://github.com/pret/pokefirered)
- [Field map structures](https://github.com/pret/pokefirered/blob/master/include/global.fieldmap.h)
- [Field map implementation](https://github.com/pret/pokefirered/blob/master/src/fieldmap.c)
- [Object movement implementation](https://github.com/pret/pokefirered/blob/master/src/event_object_movement.c)
- [Object graphics structures](https://github.com/pret/pokefirered/blob/master/src/data/object_events/object_event_graphics_info.h)
- [Event instruction macros](https://github.com/pret/pokefirered/blob/master/asm/macros/event.inc)

## Ownership and distribution

The original game/hack artwork, names and trademarks are third-party material. User-provided files were transformed for this requested project; that does not grant rights to publicly redistribute or commercially use the extracted assets. No claim is made that the assets are original NXT artwork or that the project is endorsed by Nintendo, Game Freak, The Pokemon Company or the ROM-hack authors. Review the applicable permissions before sharing beyond your authorized test environment.
