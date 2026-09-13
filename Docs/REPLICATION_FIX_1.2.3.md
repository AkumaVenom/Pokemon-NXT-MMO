# Starter, multiplayer, login and saving fix 1.2.3

## Build the complete source

Extract **both** `Pokemon_NXT_MMO_v0.2.0-alpha_Replication_1.2.3_Part1_Source.zip` and `Pokemon_NXT_MMO_v0.2.0-alpha_Replication_1.2.3_Part2_Audio.zip` into the same new destination. Their shared project folder must merge. Run `BUILD_ALL.bat` from the extracted folder; its banner is **1.2.3**. Use the matching Client and Server from the successful `dist/build-...` output. Close old client windows and launch the new client executable directly; an old desktop shortcut may still run the unfixed client.

Part 1 contains code, templates, maps, sprites, cry WAVs and the audio catalog. Part 2 contains all 818 music/effect OGGs. The existing extracted FireRed/Sigma audio and its implementation are retained. No ROM or audio conversion is needed for a normal build.

## Why the starter was wrong

The old client changed the selected starter whenever the home-region field changed: Johto forced Chikorita and Kanto forced Bulbasaur. Therefore selecting Charmander and then Johto submitted Chikorita to the server. This was reproducible in the actual client form handlers; it was not caused by both followers sharing one sprite.

Region and starter are now independent. The visible registration summary names both choices. Submission freezes those exact choices before waiting for a connection, prevents duplicate submissions and locks the form until success or a recoverable error. The server requires an explicit valid starter and home for registration. Login restores the existing character; changing starter/home fields in a login packet cannot replace it.

## Player ownership and world updates

Queued packets own a snapshot of their nested data. Another action cannot mutate a previously queued party, inventory or battle view. Commands must come from the current player session. Private state packets identify their owner, and the client rejects another owner's state or an older revision. A replacement session cannot inherit an earlier session's autosave completion or private UI state.

Map loading buffers incoming scene deltas, including follower changes and departures, until local assets are ready. It applies the latest state for each player and discards superseded map loads. Logout invalidates pending loads and player hit targets. Interactions during map loading cannot target objects from the previous map.

## Login and reconnects

Rejected authentication sockets are retired before a retry. A submitted login has a bounded response timeout, so a stalled server cannot leave the form permanently locked. If account creation times out, the client explicitly says to try **Log in** with the same credentials; it does not automatically register again.

Idle connection checks no longer consume login attempts. Real authentication attempts remain rate limited, and a cooldown is returned as a visible login error. Invalid stored password hashes fail verification. Username lookup remains case insensitive; passwords remain case sensitive.

A returning account loads its character inside the same server lock used for the previous session's final save and removal. This prevents an overlapping reconnect from loading old progress just before the old session saves. Cleanup from an old socket cannot remove the replacement socket.

## Automatic server-side saving

| Progress | Persistence behavior |
| --- | --- |
| New account and selected starter | Written together before entering the world |
| Party order, purchases, item use and healing | Database commit before success/state publication |
| Wild/trainer battle turns, captures, XP, rewards, HP and PP | Database commit before the completed turn is published |
| Player trades | Both owners committed atomically before success |
| Map transitions, home travel and Surf changes | Database commit before confirmation |
| Ordinary walking and facing | Automatic dirty-state checkpoints; **5-second default** for fresh configurations |
| Logout and orderly server shutdown | Final save of the current character |

Players do not need to press **Save now** to retain progress; that button requests an additional checkpoint. Passwords and character ownership remain server-side. The client cannot submit a character save or choose another account's Pokémon.

An admitted database transaction completes together with its live-state publication before a cancelled socket is cleaned up. Failed durable actions leave committed progress unchanged. Revision checks prevent older autosave snapshots from overwriting newer durable actions.

The movement interval is a target while the database is healthy, not a zero-loss guarantee for power cuts. An abrupt process or machine failure may lose walking since the latest successful checkpoint; important acknowledged progress is already committed. Existing deployments keep their configured `[world] save_interval_seconds`; set it to `5` to adopt the new default. Active battle sessions are not resumed after disconnect, although completed non-duel turns are saved. Friendly duel battle state is temporary by design.

## Existing installations

This is a source update, with no character-specific repair tools and no account reset. Building creates a new output; it does not open or erase the deployed database. Existing accounts retain their saved starter. The registration fix applies to newly created accounts and cannot infer an earlier intended choice from an already saved character.

When deploying, stop the old world cleanly using its `shutdown` command, back up its database and private deployment files, then use the new matching Client and Server. Keep the existing Server database settings, database, certificates/private key and the client's working connection settings. Do not overwrite working configurations with clean build templates. If you want an entirely separate fresh world, configure a separate empty database; deleting the old world is not part of this update.

The PowerShell HOME build correction, pinned prerequisite downloads, world lease/startup logging fix 1.1.2 and TLS setup 1.2.2 remain included. Network addresses and certificate policy have not changed.

See `REPLICATION_TEST_REPORT.md` for measured validation and platform limits.
