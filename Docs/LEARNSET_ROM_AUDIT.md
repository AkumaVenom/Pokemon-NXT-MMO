# v0.3.1 source learnset audit

All 876 published species now have a source-indexed learnset: 874 intact native
lists and two explicitly identified native-prefix recoveries. The prior 28
Sigma type templates are replaced by 11 valid lists without a level-one move,
15 valid lists with descending level entries, and the two recoveries described
below. No level or move is filled in from a modern database or a species type.

`Tools/extract_learnsets.py` is a standard-library-only, read-only ROM importer.
`Server/data/learnsets.json` records every published identity and all 1,776 source
manifest indices, native row order, offsets, hashes, duplicate-index aliases,
shared-species comparisons, move-definition differences, and repair evidence.
The ROMs themselves and source graphics are not modified by this importer.

## Accepted source revisions and active tables

| Source | SHA-256 | Bytes | Active pointer table | Engine literal | Pointer slots |
| --- | --- | ---: | --- | --- | --- |
| FireRed USA/Europe Rev 1 | `729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059` | 16,777,216 | `0x25d824` | `0x3ea90` | 0–411 |
| Ultra Shiny Gold Sigma Completo 1.5.0 | `62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64` | 17,632,785 | `0xa74f64` | `0x3ea7c` | 0–1339 |

Both native engines use species ID × 4 to load a pointer, then read packed
little-endian 16-bit entries. A move is `entry & 511`, its level is `entry >> 9`,
and `0xffff` ends the list. The importer verifies exact ROM hashes, a matching
engine instruction signature, six active table references, the Bulbasaur
signature, and the table boundaries before accepting any entries. A search for
a plausible learnset in unused data is insufficient evidence.

The six FireRed literals are `0x3ea90`, `0x3eb24`, `0x3eb98`, `0x43ddc`,
`0x43e34`, and `0x43f98`. Their Sigma equivalents are each 0x14 bytes earlier.
FireRed slot 412 is zero; Sigma slot 1340 is `0xffffffff`. Source manifest
entries outside those ranges are explicitly unsupported, even where some
other asset table contains a readable sprite.

## Native order and levels

The source engine does not require a level-one move. Its initial-move routine
scans native order and stops at the first move above the Pokémon's level or
at the terminator. An intact list starting at level 10 does not authorize a
manufactured level-one Tackle.

Descending levels also occur in the actual Sigma data. For example, Riolu and
Lucario list source move 183 at level 66 before their level-26 elemental
punches. Kricketune lists source move 210 at level 47 before level-25 Swords
Dance. The importer retains these sequences exactly. The level-up routine
searches for the first exact-level entry and processes its contiguous
equal-level group. None of the 876 published profiles has a level split across
separate groups. Repeated same-level moves retain their source order.

All published native entries are within levels 1–100 and source move IDs
1–354. Unsupported values, a bad pointer, an out-of-ROM read, or an absent
terminator cannot silently turn a diagnostic prefix into a valid list.

### Cyndaquil

Both supplied ROMs give Cyndaquil **Ember at level 12**, not level 10. The two
lists are byte-identical: FireRed at `0x25827c`, Sigma at `0x25820c`.

| Level | Source move ID | Move |
| ---: | ---: | --- |
| 1 | 33 | Tackle |
| 1 | 43 | Leer |
| 6 | 108 | Smokescreen |
| 12 | 52 | Ember |
| 19 | 98 | Quick Attack |
| 27 | 172 | Flame Wheel |
| 36 | 129 | Swift |
| 46 | 53 | Flamethrower |

## Two damaged native terminators

Neither recovery guesses where a plausible-looking list should stop. The
complete prefix is byte-identical to an independently terminated native list,
and a separately referenced event script begins exactly at the damaged
boundary. The repairs are restricted to these two source indices in the
accepted Sigma hash. A changed prefix, witness list, event pointer, or event
instruction signature rejects the recovery.

| Published species | Native prefix | Terminated native witness | Independent boundary evidence |
| --- | --- | --- | --- |
| `sg_933` Bouldeon | 13 entries at `0xa4ae00` | Golem source ID 76 at `0x257acc`, terminator `0x257ae6` | At `0xa4ae1a`, an NPC dialogue script begins. Object script pointer `0x7fd530` references this exact boundary, in object array `0x7fd238`, index 31. |
| `sg_943` Regieleki | 14 entries at `0xa4f448` | Manectric source ID 338 at `0x259012`, terminator `0x25902e`; also source ID 940 at `0xa4f40e` | At `0xa4f464`, a coordinate event script begins with a flag check. Coordinate event pointer `0x7e3778` references this exact boundary, in array `0x7e372c`, index 4. |

Bouldeon's first word after the prefix is `0x000f` (an invalid level-zero
entry if misread as a move). Regieleki's event bytes initially resemble some
packed moves, then reach an invalid level of 104. Reading until a later
accidental `0xffff` would import script bytes as attacks.

Both published records use `learnsetSource: "rom-recovered-prefix"`, with the
native byte hash, exact stop offset, missing-terminator marker, native witness
species, and event-pointer evidence. Their levels and moves are copied from
the existing prefix without additions. This restores a boundary; it does not
claim that the damaged source engine would avoid its original overread.

## Shared species and alternate identities

The 385 shared `fr_*` species retain FireRed learnsets in both regions. Each
`sg_*` species uses its own exact Sigma source index. Moving an owned Pokémon
between regions never replaces its learnset with a different ROM profile.

| Shared FireRed/Sigma comparison | Species |
| --- | ---: |
| Identical entries and order | 172 |
| Same entries, different native order | 131 |
| Different level/move entries | 82 |
| Total compared | 385 |

Thus 213 shared lists differ in at least their order. These are recorded as
source differences, not silently applied to canonical FireRed species.

Published alternate forms retain their own source index, including Sigma's
Unown forms. Name normalization alone is not identity evidence: the legacy
catalog importer collapses Nidoran♀ and Nidoran♂, multiple regional/Mega forms,
and many `TEMP` slots. The audit records those collisions and the distinct
native lists behind them. This update does not renumber or invent new species
keys to repair the older catalog model. In particular, existing `sg_971`
is flagged `placeholder-source-identity`; its readable Bulbasaur pointer does
not establish that `TEMP` is a real additional Pokémon. The 26 FireRed
manifest records outside its active learnset table are audited but cannot
receive fabricated native lists.

## Sigma move identities

Sigma repurposes seven of the original move IDs. Reusing the FireRed labels
for those IDs would give a correct numeric row the wrong move identity.
Those Sigma moves receive IDs `1024 + sourceMoveId`, exclusively in Sigma
species learnsets. The original numeric rows remain in `rawLearnset`
provenance and the source catalog audit. All seven are used, by 116 published
Sigma species in total.

| Sigma raw ID | Published ID | FireRed identity | Sigma source identity | Species using variant |
| ---: | ---: | --- | --- | ---: |
| 183 | 1207 | Mach Punch | Close Combat | 19 |
| 210 | 1234 | Fury Cutter | X-Scissor | 22 |
| 237 | 1261 | Hidden Power | Terastallize | 27 |
| 294 | 1318 | Tail Glow | DazlingGleam | 2 |
| 295 | 1319 | Luster Purge | MoonBlast | 22 |
| 297 | 1321 | Featherdance | Roost | 17 |
| 346 | 1370 | Water Sport | Aqua Ring | 9 |

`Faint Attack`/`Feint Attack` at ID 185 is a spelling difference, not a new
move identity, and keeps its canonical ID. The source spellings
`DazlingGleam` and `MoonBlast` are retained as metadata.

Each variant records the Sigma name, power, type, accuracy, PP, priority,
effect, effect chance, target, category byte, and exact 12-byte source record.
Sigma source type 9 remains type 9, including MoonBlast and DazlingGleam.
The engine-referenced type-name table at `0x24f1a0` still labels its seventh-byte
stride slot 9 (`0x24f1df`) `???`. A move or species name alone does not establish
an implemented modern Fairy matchup chart, so this update does not remap
source type 9 to the project's type 18 or alter Sigma species types.
Native effect IDs and parameters are evidence; a familiar modern move name
does not authorize adding modern effects absent from the supplied ROM.
The audit also exposes all 248 name/definition differences between the two
sources, including 247 binary-record differences. Unchanged move identities
continue to use the project's canonical FireRed battle definitions. This
update therefore establishes source learnset levels and separate renamed
identities; it does not claim full Sigma battle-engine parity.

## Reproduction and verification

From the project root, with the two exact user-owned ROM paths:

```sh
python Tools/extract_learnsets.py "/path/to/FireRed Rev 1.gba" "/path/to/Sigma 1.5.0.gba"
python Tools/extract_learnsets.py "/path/to/FireRed Rev 1.gba" "/path/to/Sigma 1.5.0.gba" --check
python -m unittest Tests.test_learnset_rom -v
```

`--check` re-extracts and compares the entire sidecar without writing it. The
ROM-free tests verify all 876 published profiles and all 1,776 manifest
indices, reconstruct every native list's recorded byte hash, validate the
seven explicit move aliases, exercise both narrowly bounded recoveries, and
reject malformed input. They also cover repeated levels, native descending
order, missing level-one entries, empty native lists, exact Cyndaquil levels,
and the canonical-source policy. These tests do not require distributing ROM
images with the project.
