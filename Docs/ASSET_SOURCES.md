# Extracted asset sources and audit

These are the exact two user-provided source files used for this build. They are not included in any output ZIP. The game loads the resulting PNG/JSON data directly; no source ROM is opened at runtime.

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

Imported 434 layouts, 1339 raw sprite slots and 151 object-frame sheets. Raw slots include unused/duplicate/form entries; this is not a distinct-species count.

## Published native pack

Pack: `0a8cdb1a321bac58cdfce7e6`. 10,902 PNG files, 859 map records, 852 safe-entry maps, 876 filtered/deduplicated catalog entries. Every published catalog entry has front, back, shiny front, shiny back and icon asset paths validated by the build tests.

The binary decoding pipeline handles GBA pointers, LZ77 blocks, 4bpp tiles, BGR555 palettes, map blocks, primary/secondary tilesets, foreground layers, collision/elevation/behavior grids, object sprites, native connections/warps, species metadata and compatible moves/learnsets. Sigma relocates tables and includes additional content. The extractor preserves discovered source identifiers and documents warnings.

Some scanner warnings reflect probing beyond a valid table or rejecting unused slots; they are not a count of missing legitimate assets. Conversely, successful structural decoding is not proof of complete extraction of everything in either ROM. Original ARM/event code, story text systems, music/cries, tile animations and additional unlocated/custom script resources are not shipped as a working game engine.

Original encounters were recovered from the structurally validated tables where possible; missing/custom data uses labeled alpha fallback encounters. Sigma-only learnsets use explicit alpha templates. Party icons are used as followers rather than claiming complete directional overworld sprite coverage.

## Technical references

The implementation used primary format/decomposition references for the GBA FireRed structures, then decoded the supplied bytes. These references are not additional ROM downloads.

```text
https://github.com/pret/pokefirered
https://github.com/pret/pokefirered/blob/master/include/global.fieldmap.h
https://github.com/pret/pokefirered/blob/master/src/fieldmap.c
https://github.com/pret/pokefirered/blob/master/src/event_object_movement.c
https://github.com/pret/pokefirered/blob/master/src/data/object_events/object_event_graphics_info.h
```

## Ownership and distribution

The original game/hack artwork, names and trademarks are third-party material. User-provided files were transformed for this requested project; that does not grant rights to publicly redistribute or commercially use the extracted assets. No claim is made that the assets are original NXT artwork or that the project is endorsed by Nintendo, Game Freak, The Pokemon Company or the ROM-hack authors. Review the applicable permissions before sharing beyond your authorized test environment.
