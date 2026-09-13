# Adventure data from the supplied ROMs

> **Learnset update:** The learnset extraction counts and rejection rules recorded below describe the original 0.3.0 adventure importer. Version 0.3.1 applies `Server/data/learnsets.json` afterward and replaces all 28 remaining templates. The current source audit and recovery evidence are in `LEARNSET_ROM_AUDIT.md`. Trainer, evolution and item extraction described here remains applicable.


The v0.3.0 adventure pack imports trainer parties, trainer-to-NPC associations,
evolution rules and additional Sigma learnsets from the same two ROM revisions
as the accepted graphics/audio pack. The running client and server do not read
ROM files. Ordinary `BUILD_ALL.bat` builds use the reviewed JSON sidecar.

## Verified sources

| Source | SHA-256 | Trainer table | Evolution table |
| --- | --- | --- | --- |
| FireRed USA/Europe Rev 1 | `729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059` | `0x23eb38` | `0x2597c4`, five slots per species |
| Ultra Shiny Gold Sigma Completo 1.5.0 | `62d1a99f5b64a45cd4f6364273743f9d8961e9c439d8201bfeedb27c02f32c64` | `0x23eac8` | `0xbfffc0`, eight slots per species |

The reader validates ROM hashes against the accepted extraction manifest,
pointer ranges, trainer header/party layouts, move IDs, species mappings, the
six Kanto starter evolution anchors, engine references to evolution tables,
and evolution item IDs/names. Event instruction layouts were checked against
the [pret FireRed event macros](https://github.com/pret/pokefirered/blob/master/asm/macros/event.inc).
Sigma's relocated tables were located and verified directly in the supplied
ROM; FireRed offsets were not substituted for Sigma definitions.

## Published coverage

- **1,294 trainer-to-NPC records:** 413 FireRed and 881 Sigma records, including
  the sixteen original regional gym challenges.
- **321 supported evolution rules across 317 canonical species:** level,
  trade, and verified evolution-item methods.
- **24 evolution items:** six standard stones plus eighteen Sigma items,
  including its Link Cable, Fairy Dust and other native item-trigger methods.
- **463 Sigma species learnsets** decoded from the relocated pointer table
  `0xa74f64`, referenced by the Sigma engine at `0x3ea7c`.
- **959 normalized map object lists**, preserving source object-array indices
  and local IDs for every visible NPC.

`Server/data/adventure_rom.json` stores each trainer's source, source trainer
ID, script address, exact object-array index, party address, species IDs,
levels, custom moves, held-item IDs and source IV scalar. Party composition and
levels are not level-scaled substitutions. For example, FireRed Brock retains
Geodude 12 and Onix 14; Sigma Falkner retains Pidgey 10, Pidgeotto 12 and Noctowl
14. MMO prize money, battle AI and progression gates are separately authored.
Original held-item effects, trainer personality generation and event scripts
are not implied by the presence of these source fields.

## Correct NPC identities

Sigma contains invisible movement-type-76 placeholders and duplicate local
NPC IDs. Treating them as visible trainers can put an obsolete leader in the
same room as the real leader or bind a battle to a different object.

Normalization reads the original object array, removes invisible placeholders,
keeps the first visible occurrence of each original local ID, and assigns an
unused ID only to subsequent visible duplicates. Unique visible IDs never
change. `sourceObjectIndex` and `sourceLocalId` retain the original identity.
Center services, trainer bindings and rendered objects use this one mapping.

The original Sigma Chuck gym was absent from the earlier decoded map set. It
is now recovered as `johto_1_88`, with the real Chuck event at NPC 17, tile
`9,6`, script `0x959b47`. The same recovered interior asset is used in the
world and the adventure registry.

## Deliberate limits

The extractor follows a bounded set of known event commands, branches and
calls until their first trainer battle. It never executes ARM code or scans
arbitrary text bytes as scripts. Unknown paths and ambiguous conditional teams
are omitted. Leaders have explicit first-challenge adapters; source rematch or
story flags are not treated as an implemented original campaign. Double
battles and teams containing moves unavailable in the runtime move catalog are
excluded. The `unsupported` section records these decisions for future work.

Species shared by both regions keep the evolution rules of their stable
canonical species key (`fr_*` uses FireRed; `sg_*` uses Sigma). Changing home or
traveling between regions cannot change an owned Pokémon's evolution rules.
Both ROM rule sets remain in `evolutionsBySource` for provenance. Friendship,
time, stat-comparison and other unimplemented methods are not silently changed
into simple level evolutions. Two Sigma form evolutions with incompatible
experience curves remain excluded until an explicit migration is supported.

Twenty-eight Sigma source learnsets are out of level order or have no valid
level-one entry. Their existing labeled fallback remains in use; the pack
does not relabel a guessed replacement as ROM data. Some valid Sigma lists
themselves reuse another species' native list; the extractor preserves the
supplied ROM's actual pointer and contents.

## Rebuilding and checking this sidecar

After running interior recovery, use Python (the adventure reader and its
tests require only the standard library):

```text
python Tools/extract_adventure_data.py "FireRed Rev 1.gba" "Sigma 1.5.0.gba"
python -m unittest discover -s Tests -p test_adventure_rom.py -v
```

Apply recovered interiors, `normalizedObjects`, `speciesOverrides` and the
verified item metadata before repacking the versioned client/server content.
The sixteen ROM-independent regression tests cover instruction boundaries,
calls/branches, malformed pointers, hidden/duplicate NPCs, party data layouts,
every published trainer binding, both gym sets, evolution targets/experience
curves and Sigma learnset order. Supplied ROMs are development inputs and are
not included in either release archive.
