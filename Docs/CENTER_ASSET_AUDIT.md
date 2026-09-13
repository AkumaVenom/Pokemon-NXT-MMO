# Pokemon Center and regional Nurse Joy audit

Adventure update 0.3.0 — audited against the supplied FireRed Rev 1 and Ultra Shiny Gold Sigma 1.5.0 ROMs.

The committed registry covers **42 Pokemon Center maps and two additional healing stations, with 53 Nurse Joy interactions**. Some Sigma map records combine several separate reception rooms; each healing counter has its own nurse identity and safe return position.

| Source assets | Center maps | Other healing stations | Nurse Joy interactions |
|---|---:|---:|---:|
| FireRed / Kanto | 19 | 1 | 20 |
| Sigma / Johto and its additional source areas | 23 | 1 | 33 |

## How coverage was established

`Tools/prepare_centers.py` checks exact ROM SHA-256 identities, scans every extracted and recovered map header, and identifies the native center secondary tileset and the healing-desk metatile. Native Nurse Joy event declarations must call the verified common healing script. A sprite ID alone does not grant a healing service. The two nonstandard Tower/Frontier receptions and the custom Route 32 reception were also checked visually against their decoded source maps.

Every registered nurse has a clear standing tile two tiles south of the counter, matching the server interaction distance. A conservative collision/elevation flood fill verifies a path from that position to a native doorway or stair record. `respawnByNpc` preserves the specific reception in combined Sigma maps. The separate interior-warp audit validates routing; this center audit does not execute the original ROM story scripts.

Kanto uses `objects/kanto/64.png`; Sigma uses `objects/johto/64.png`. Both sheets were decoded independently from their respective ROM and matched byte for byte to the packaged files. Their hashes differ: Sigma retains its own Nurse Joy sprite, rather than substituting the FireRed version. Maps, furnishings and counters remain the corresponding source-region assets.

## Corrected source-data omissions

- `johto_8_0`: the native Lavender reception has a complete healing machine and counter but an empty object table. Nurse Joy is added at the verified counter tile `(7, 2)`, using the Sigma sprite.
- `johto_1_58`: a recovered Sigma map combines seven healing receptions. Six already had native nurses; the small seventh reception receives a Sigma nurse at `(76, 2)` with unused ID 29.
- `johto_34_61`: the source declares both Nurse Joy and a different NPC with local ID 5. The shared object normalization retains Nurse Joy ID 5 and assigns the duplicate NPC ID 1, retaining its `sourceLocalId` and original `sourceObjectIndex`. Center and trainer bindings consume the same normalized IDs.

Hidden source actors on `johto_34_20`, `johto_34_26`, `johto_34_36` and `johto_34_40` are not healing centers: their scenery is a station, gym, house or tower, and there is no healing counter. Native movement type 76 is removed by the shared object normalization. Link-service floors and the National Park contest reception are not mislabeled as healing centers.

## Runtime contract

`Server/data/centers.json` is an audit/build input. The publication pipeline first applies canonical object normalization and then `apply_centers(world, registry)`, which adds the two verified nurses and includes the center registry in the hashed world pack. The server uses `world.centers` as authoritative content. It validates the current map, exact nurse identity and interaction distance before restoring party HP, status and PP and saving the result.

PC storage is available through the nurse reception dialog (`nursePcAccess`). The source PC graphics are furniture metatiles, not interactive NPC event records, so the registry does not invent NPC IDs for them.

Normal builds and game clients need no ROM. The importer never executes native ARM code or event scripts, and no original ROM files are packaged.

## Reception inventory

| Map | Source area | Nurse IDs | Kind |
|---|---|---|---|
| `johto_1_58` | Alola Islands | 1, 7, 9, 11, 18, 27, 29 | pokemon-center |
| `johto_2_10` | Battle Frontier | 1 | healing-station |
| `johto_5_4` | Viridian City | 1 | pokemon-center |
| `johto_6_5` | Pewter City | 3 | pokemon-center |
| `johto_7_3` | Cerulean City | 1 | pokemon-center |
| `johto_8_0` | Lavender Town | 1 | pokemon-center |
| `johto_9_1` | Vermilion City | 1 | pokemon-center |
| `johto_10_12` | Celadon City | 1 | pokemon-center |
| `johto_11_5` | Fuchsia City | 1 | pokemon-center |
| `johto_12_5` | Cinnabar Island | 1 | pokemon-center |
| `johto_13_0` | Indigo Plateau | 1, 9, 11 | pokemon-center |
| `johto_14_6` | Saffron City | 1 | pokemon-center |
| `johto_16_0` | Mahogany Town | 1 | pokemon-center |
| `johto_21_0` | Blackthorn City | 1 | pokemon-center |
| `johto_31_3` | Cianwood City | 1 | pokemon-center |
| `johto_32_0` | Cherrygrove City | 1 | pokemon-center |
| `johto_33_2` | Violet City | 1 | pokemon-center |
| `johto_34_1` | Azalea Town | 1 | pokemon-center |
| `johto_34_10` | Route 32 | 5 | pokemon-center |
| `johto_34_11` | Route 32 | 9 | pokemon-center |
| `johto_34_61` | Lavender Town | 5, 7 | pokemon-center |
| `johto_35_1` | Goldenrod City | 1 | pokemon-center |
| `johto_36_0` | Ecruteak City | 1 | pokemon-center |
| `johto_37_0` | Olivine City | 1 | pokemon-center |
| `kanto_2_10` | Trainer Tower | 1 | healing-station |
| `kanto_5_4` | Viridian City | 1 | pokemon-center |
| `kanto_6_5` | Pewter City | 3 | pokemon-center |
| `kanto_7_3` | Cerulean City | 1 | pokemon-center |
| `kanto_8_0` | Lavender Town | 1 | pokemon-center |
| `kanto_9_1` | Vermilion City | 1 | pokemon-center |
| `kanto_10_12` | Celadon City | 1 | pokemon-center |
| `kanto_11_5` | Fuchsia City | 1 | pokemon-center |
| `kanto_12_5` | Cinnabar Island | 1 | pokemon-center |
| `kanto_13_0` | Indigo Plateau | 2 | pokemon-center |
| `kanto_14_6` | Saffron City | 1 | pokemon-center |
| `kanto_16_0` | Route 4 | 1 | pokemon-center |
| `kanto_21_0` | Route 10 | 1 | pokemon-center |
| `kanto_31_3` | Seven Island | 1 | pokemon-center |
| `kanto_32_0` | One Island | 1 | pokemon-center |
| `kanto_33_2` | Two Island | 1 | pokemon-center |
| `kanto_34_1` | Three Island | 1 | pokemon-center |
| `kanto_35_1` | Four Island | 1 | pokemon-center |
| `kanto_36_0` | Five Island | 1 | pokemon-center |
| `kanto_37_0` | Six Island | 1 | pokemon-center |

## Reproducing the audit

With the two supplied ROM files available locally:

```text
python Tools/prepare_centers.py --firered <FireRed.gba> --sigma <Sigma.gba>
python -m unittest discover -s Tests -p test_centers.py -v
```

The 12 center contract tests cover Kanto receptions, all principal Johto town receptions and Route 32, every counter's geometry/access, multiroom nurse identities, the two missing-nurse additions, duplicate source identity handling, exclusion of hidden placeholders/link rooms, source-region sprite hashes, PC access metadata, idempotent application and rejection of conflicting geometry or NPC additions. Actual service transaction and multiplayer tests are maintained with the world/adventure tests.
