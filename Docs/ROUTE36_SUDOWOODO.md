# Route 36 Sudowoodo story gate

Release: **0.6.5-alpha · Route 36 Sudowoodo Story Gate**  
Baseline: **0.6.4-alpha · Autonomous Trainer Performance Hardening**  
Database schema: **3 (unchanged)**

## Purpose

The extracted Johto Route 36 map already contained the familiar odd-tree sprite but its underlying shared collision tile was passable, so a player could walk through it. This release makes that authored object a real, server-authoritative story gate without deleting or replacing any existing map, battle, autonomous-trainer or adventure feature.

The gate is deliberately **per character**. Shared map JSON remains immutable at runtime. One trainer defeating the encounter changes only that trainer's saved adventure state and client presentation; every other trainer continues to see and collide with their own uncleared odd tree.

## Authored event

`Server/data/adventure.json` defines `johto_sudowoodo` and the publisher binds it to the extracted Route 36 object rather than inventing a replacement prop:

- map: `johto_2_23` (Route 36)
- object: ID `3`, graphics `98`, tile `(24, 11)`
- prerequisite: Whitney / Plain Badge (`johto_3`)
- Key Item: `squirtbottle` / SquirtBottle
- encounter: `fr_185` / Sudowoodo, level 20, Normal variety
- encounter moves: Rock Throw (`88`), Mimic (`102`), Flail (`175`), Low Kick (`67`)

The SquirtBottle is a unique Key Item represented in the existing saved item dictionary. It has price 0 and is explicitly non-buyable and non-tradable. Using it on the odd tree does **not** consume it.

## Progression flow

1. The odd tree is solid for an uncleared character. The server enforces this in `World.walkable()` even though the extracted collision grid at that tile is `0`.
2. Before the Plain Badge, clicking the tree opens the story dialog but the **Use SquirtBottle** action is disabled. A forged action is rejected by the server as well.
3. Whitney's first valid Gym victory records the Plain Badge through the existing Adventure victory transaction. `refresh_unlocks()` then grants one SquirtBottle in the same saved character state.
4. Existing characters upgrading from 0.6.4 that already own the Plain Badge receive the SquirtBottle during additive save migration/login validation. No reset is needed.
5. The player approaches the real Route 36 object, opens its dialog and chooses **Use SquirtBottle**. The server revalidates map, object identity, proximity, uncleared state, badge, Key Item and a healthy party.
6. The server starts an ordinary authoritative wild battle against the authored level-20 Sudowoodo. Capture items, EXP, selected moves, HP/PP, battle UI and save semantics are the normal shared systems.
7. A successful defeat or capture adds `johto_sudowoodo` to that character's `adventure.storyEvents` in the battle result transaction. The path is not published as clear until the save succeeds.
8. On subsequent map/state snapshots, only that owner hides the story object and ignores its collision. Relogging retains the clear. Other accounts are unaffected.

Running away, losing, a stale/remote interaction, replaying the event after completion, or a database-save failure never clears the gate.

## SquirtBottle acquisition in NXT

The original games deliver the SquirtBottle through Goldenrod's flower-shop story sequence after Whitney. NXT currently does not execute the original games' complete NPC event-script engine. For this MMO release, the Key Item is therefore awarded directly when the Plain Badge is first recorded. This preserves the requested gameplay dependency—Whitney first, SquirtBottle second, Route 36 Sudowoodo third—while keeping the award authoritative, persistent and compatible with existing accounts.

If a later release implements the full Goldenrod flower-shop/Floria script chain, the item-award trigger can move there without changing the owner-only Route 36 clear format.

## Collision and performance contract

`World.walkable()` checks Cut trees and authored story blockers in a **single bounded pass** over map objects on the requested destination tile. This matters because the same method is used by human movement and autonomous-trainer pathing. Adding the story blocker therefore does not reintroduce the repeated whole-object-list scans or database I/O that the accepted 0.6.4 autonomous performance release removed.

Completion never writes to `world.json`, map collision arrays or shared object arrays. The only persistent delta is the owning character's saved adventure state. This keeps multiplayer isolation deterministic and avoids global map-state races.

## Security / authority boundaries

The client is presentation only. It can request an interaction, but it cannot grant itself the badge, SquirtBottle, encounter or clear flag. Server-side checks enforce:

- current session and normal command rate limits;
- exact current map and authored object ID;
- interaction proximity;
- required Plain Badge and Key Item;
- healthy party requirement;
- event not already cleared;
- item buy/trade restrictions;
- successful battle result;
- successful durable save before publication.

The client also rejects non-tradable Key Items in normal trade composition, but the server independently rejects forged trade packets.

## Upgrade

1. Back up the configured server/database.
2. Build/deploy matching 0.6.5 Client and Server files.
3. Keep the existing `config.ini`, MySQL database, certificates and account data.
4. Do **not** rerun MySQL setup and do **not** recreate autonomous trainers.
5. Leave `allow_alpha_atlas = false` for progression testing. The alpha-atlas override is intentionally an administrator/debug bypass of normal discovered-location travel rules.
6. Log in normally. Existing Plain Badge owners are migrated additively; other characters receive the SquirtBottle when Whitney is defeated.

Schema 3 remains authoritative. No SQL schema migration is introduced by this story event.
