# Alpha scope and acceptance boundaries

Gameplay **0.2.0-alpha**, including ROM audio integration. Build tools **1.2.0** preserve world startup fix **1.1.2** and the automatic Go prerequisite correction.

## Implemented slice

There is a real server-dependent client login and registration flow, authoritative tile movement with collision/elevation checks and native connection/warp records, map-local interest replication, username nameplates, lead-party follower replication, global General/Trade chat, static NPC interaction and practice battles, wild encounters/capture, experience and learned moves, party/collection management, items/currency, friendly PvP challenges and transactional two-owner trades. The client is not displaying a predetermined offline multiplayer video.

The collection limit defaults to 240 Pokemon and the active party to six. Captures fill available party slots or enter the collection. Trading can exchange up to six creatures plus supported items/money. Public nearby entity packets contain a name, location, appearance, lead species and activity flags, not the other player's private inventory, password hash or complete party.

The combat engine handles basic singles turn resolution: move PP, ordinary damage, speed/priority ordering, types, STAB, accuracy, selected statuses, switching, items and capture. Friendly duels use cloned battle resources and do not consume persistent HP/items. Practice NPC battles use alpha-selected teams. Some variable-power moves are approximations; unsupported status/advanced effects are disabled. FireRed-compatible species use decoded FireRed level-up learnsets; Sigma-only species have explicitly tagged type-template learnsets.

Music, effects and cries now play through the client sound mixer. All 859 map headers have source music bindings, including explicit silence and inherited music. Each source has move sound-script metadata for IDs 1–354; playback follows a selected native script path with explicit delays, repeated effects and applicable cry callbacks. Visual-task completion timings are approximated because the MMO does not run the original GBA battle-animation renderer. Server-confirmed action cues accompany the implemented battle, capture, healing, shopping, party, save and trade flows. This does not enable unsupported move mechanics or recreate unimplemented story events. See `AUDIO_GUIDE.md` for exact content boundaries.

## Region extraction versus campaign completion

425 FireRed and 434 Sigma layouts were exported. 852 have a non-collision entry tile. That test does not prove every square, every native warp or every region passage is playable. Static maps, object frames, collisions and native connection metadata are assets/data; original event scripts are a separate executable system that this alpha does not implement.

FireRed's extracted set contains its additional areas, not only mainland Kanto. Sigma repurposes and adds areas, so its whole set is labeled Johto / Sigma, not asserted to be a clean Johto-only map list. The atlas deliberately exposes stable source map IDs for testing. Duplicate names, unused variants, unusual interior assets and hack-specific graphical inconsistencies may remain.

The encounter scanner recovered 124 distinct FireRed map headers and 35 Sigma table entries. Maps without a compatible recovered table use documented low-level alpha fallback encounters. Some maps have only water/fishing data. Alpha practice battles do not imply original trainer teams. Do not represent this as complete original wild distributions, scripted legendary events or universal natural availability of every catalog entry.

## Explicitly not implemented

Original FireRed/Sigma story execution; a complete gym/badge/league campaign; original dialog and quests; script-controlled doors/bridges/unlocks; animated environment tiles; full battle visual effects; full move/ability/item mechanics; evolution, breeding, eggs and EV training; fishing/rock-smash progression; original trainer line-of-sight AI; autonomous account-like trainer bots; guilds, auctions, mail, friend lists, cross-shard travel or account recovery.

No complete directional overworld follower set was established. This alpha animates each available lead species using its extracted two-frame party icon, including fallback presentation for tiny/atypical forms. Follower position and species are server-replicated, but this is not four-direction HGSS-style follower animation. Shiny follower colors are not promised; battle front/back shiny art is available.

No signed installer, auto-patcher or self-updating launcher is supplied. The Windows client depends on installed Edge, and the Windows server depends on Python packages and a separately installed database. Distribute matching whole client packs manually during alpha.

## Capacity and persistence claims

The hard maximum is 1,000 authenticated accounts. A deterministic admission test admits 1,000 in-memory player records and rejects account 1,001. This is not a 1,000-socket stress test. The build has not established a 1,000-player hardware specification, latency guarantee, sustained tick budget, memory ceiling, recovery SLA or denial-of-service resilience.

The server uses one authoritative process, one serialized persistence connection, a world operation lock and local area-of-interest replication. There is a bounded outgoing queue and bounded pre-login admission. Dense crowds and trade/save contention still require profiling. Multiple independent world processes may not share this database; a lease and fencing checks enforce that boundary.

MySQL/InnoDB is implemented but not runtime-tested in this environment. Shared store/transaction behaviors were exercised against explicit temporary SQLite databases. The shipped dependency versions also require a Windows acceptance pass; the local aiohttp test version differed from the install pin. Read TEST_REPORT.md before declaring any platform accepted.

The historical reports describe their own releases. `AUDIO_TEST_REPORT.md` records the checks performed for 0.2.0-alpha; automated decoding, event and mixer tests do not establish a native Windows listening or live MySQL acceptance pass.

## Suggested first acceptance session

On two Windows PCs: provision the dedicated MySQL database, create distinct accounts, meet in Pallet Town, verify names/movement/followers, send both chat channels, capture a creature, reorder the party, trade Pokemon/items/currency, duel, cancel a trade, disconnect one side before confirmation, relog both accounts, restart the server, and verify ownership/money persisted. Repeat region travel to New Bark Town and test fullscreen/Windows DPI. Keep the first alpha private until these checks pass.

For audio, listen across an area boundary, a warp, surfing, wild and trainer battles, capture, healing and a low-HP warning. Open Sound during a battle, adjust each volume separately, test background muting, then close and reopen the launcher to confirm the mix persists. Check both source regions and a music loop longer than one full cycle. Refer to `AUDIO_GUIDE.md` if a Sigma species uses a shared cry.
