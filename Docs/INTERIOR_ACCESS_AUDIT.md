# Interior access and native destinations — v0.3.0

This update repairs the entrance pipeline across both supplied regions. It uses the FireRed and Ultra Shiny Gold Sigma map layouts and destination records. It does not run original ARM code or claim to reproduce every original story script or gym puzzle.

## What was broken

The previous movement handler treated every warp event as a teleporter, including unused events on ordinary floor. It also rejected solid animated door tiles before checking their entrance event.

New Bark Town demonstrates both defects. The real door at **(22,7)** targets **johto_4_0**, the native house interior. A separate event on the ordinary front step at **(22,8)** points to **johto_0_0**, a battle facility. That floor event is now inert, and walking up through the actual door opens the house. The previously missing native upstairs map **johto_1_93** has also been recovered, so its staircase works in both directions.

The other three New Bark Town doors retain their native destinations: **(13,4) → johto_4_3**, **(17,15) → johto_33_0**, and **(7,13) → johto_32_2**.

## Extraction and validation

| Result | Count |
|---|---:|
| Maps retained from the working source | 859 |
| Referenced Sigma maps recovered from the supplied ROM | 100 |
| Total native maps | 959 |
| Validated static warp triggers | 3,726 |
| Validated dynamic return triggers | 87 |
| Solid animated doors enabled through validated entrance logic | 577 |
| Ordinary floor or other non-warp events left inert | 1,189 |
| Pokémon Center building doors tested by actual movement in both directions | 60 |
| Gym leaders reached by actual movement from their native exterior entrances | 16 |

The extractor formerly stopped scanning some Sigma map banks after an invalid entry. Recovery now follows referenced map IDs directly, validates each layout and tileset, and preserves its original ID, image, collision, elevation, objects, music ID and source header. This recovers the missing house upstairs, Chuck's gym, compound Center rooms, caves and other referenced native areas. A separate event-count cap truncated a 147-event Sigma map to 128 events; all 147 are retained.

Destination indices are **zero-based**. They are not decremented. Native reciprocal links and exact arrival records provide validation.

One source-ROM typo has a uniquely provable correction: **johto_1_58 warp 10** used the absent destination **johto_58_1**. Its exact inverse is **johto_1_58 warp 6**, targeting warp 10. The bank/map bytes are corrected in the content transform and recorded with the original value in `interior_repairs.json`.

Invalid coordinates, invalid target indices, absent target maps, unplayable layouts and destinations without a safe adjacent arrival remain inactive. The report preserves the reason for every inactive event. These include unused source leftovers, such as the disconnected old Sigma Lavender Center layout; they are not fabricated into new buildings. Real exterior Center entrances are covered by the 60-door round-trip test.

## Runtime ownership and saving

`Server/nxt/portals.py` plans a transition without modifying content or player state. An active door requires the correct approach direction. A normal floor event can never trigger a portal merely because it contains a valid-looking destination pointer.

Arrival positions use the actual target event or its immediately adjacent standable tile. There is no fallback to a distant room or arbitrary map spawn. Native room walls retain their collision except for the explicitly documented gym adaptations below.

Shared interiors with dynamic exits keep a bounded **warpReturns** stack in each account's server-side state. Two trainers entering the same Cherrygrove Center through different doors return to their respective entrances. The destination and return context are committed together before the server publishes the map change. Saving, logout and relog preserve this context. A failed database commit leaves the player at the source and sends no destination map packet.

## Explicit MMO gym navigation adaptations

The adventure provides native trainer and gym challenges with pre-opened puzzle passages. Original electric-switch, quiz, Strength, and ice puzzle scripts are not executed by this server.

| Gym | Explicit adaptation |
|---|---|
| Lt. Surge | Apply the original FireRed script's open electric-gate metatiles and collision. |
| Blaine | Apply the original FireRed script's six open quiz-door states, including their surrounding door-frame tiles. |
| Chuck | Clear only the two blocking Strength-boulder objects at (8,20) and (8,15). Other objects and native room tiles remain intact. |
| Pryce | Open one snow-bank choke point at (5,33), using the adjacent native ice floor from (5,32). |
| Clair | Open one upper landing passage at (8,5), using the adjacent native floor from (7,5). Clair's boulder objects remain intact. |

The FireRed gate graphics are decoded from the supplied ROM's actual `setmetatile` records, not redrawn approximations. Surge's open script starts at **0x16b78f**; Blaine's open-door blocks occupy **0x16e18f–0x16e2e9**. Exact per-tile offsets and metadata are recorded in `Server/data/interior_navigation.json`.

Across these adaptations there are **50 declared tile writes** and **two removed blocker objects**. Some tile writes update frames around a passage without changing collision. Eight separate PNG variants provide the four visually altered maps' composite and ground layers. Original source PNG files remain byte-identical. A regression test verifies that all changed image pixels lie inside declared patch tiles. Its PNG decoder uses only the Python standard library, so the ordinary pinned build does not need Pillow. The decoder was independently compared against Pillow for all eight source/output PNGs.

## Reproducibility

Runtime and ordinary builds do not require ROMs. The checked-in content transforms and assets are sufficient.

To regenerate the audit and native image variants from the same supplied ROM revisions:

```text
python Tools/repair_interiors.py --firered PATH_TO_FIRERED.gba --sigma PATH_TO_SIGMA.gba
```

The source hashes are recorded in `Server/data/interior_repairs.json`. No ROM images are included in the release.

Content publication applies `repair_interiors.apply(world, root)` to recover maps and attach validated portal rules. After canonical ROM object normalization and Center object patches, it applies `repair_interiors.apply_navigation(world, root)`. The final world is then repacked for both Client and Server. Publication is designed to be repeatable.

## Verification

`Tests/test_interior_access.py`: **16 tests passed using the pinned build environment**. Evidence: `Docs/evidence/interior_access_0.3.0_tests.txt`.

The tests cover all 60 registered Center building entrances with real `World.move` commands and SQLite commits, all 16 gym leaders reached from native exterior doors, Leaf's front step/downstairs/upstairs/return route, different accounts returning through different shared Center entrances after relog, save-failure rollback, inert dummy floor events, source image preservation, and containment of the declared navigation edits.

These checks validate game logic, native content and persistence on the test runtime. They do not claim Windows graphics-driver, live MySQL, router or large-player-count validation.
