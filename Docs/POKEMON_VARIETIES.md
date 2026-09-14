# Pokémon varieties and mirrored front sprites

## Release and safe upgrade

Gameplay **0.3.5-alpha**, based on the user-accepted **0.3.4-alpha Regional Encounters & Personal Cut** source. Build tools remain **1.3.3**. Pokémon NXT MMO is a separate server/client project from Pokémon Vortex NXT.

Download **all four** ordinary full-source ZIPs (`Pokemon_NXT_MMO_v0.3.5-alpha_Source_Varieties_Part1.zip` through `Part4.zip`) and extract them into the same destination. Their `Pokemon_NXT_MMO_v0.3.5-alpha_Source_PokemonVarieties` folders must merge into one complete source tree. Do not join/concatenate the ZIP bytes, and do not run the build from inside a ZIP. Run `BUILD_ALL.bat` from the merged folder. No previous pack, patch, original ROM, images.rar, Pillow, FFmpeg or native audio renderer is needed for a normal build.

Back up the configured server and database. Build into a fresh output folder and deploy **matching new Client and Server together**; the shared pack handshake prevents old/new content mixing. Preserve working server/client `config.ini`, the database, TLS certificates/private keys and deployment connection settings. Never overwrite a live configuration with clean release templates or rerun MySQL setup merely to upgrade. This release does not change database passwords, reset accounts, delete Pokémon or require a destructive schema migration.

Existing Pokémon retain UUIDs, owner history, level/EXP, HP/status, IVs, moves/PP, held items and progression. Legacy saved `shiny: true` becomes canonical Shiny only where the new variety field is absent; old ordinary Pokémon become Normal. No retroactive random upgrades or rerolls are applied. Valid explicit modern identity takes precedence over the legacy flag. Unknown explicit variety values fail validation rather than silently destroying a future/corrupt identity. Owner-only variety records are reconstructed from actually owned creatures where possible; historical varieties of released creatures are not guessed.

## Coverage and exact wild chances

Every **Kanto/Johto species, National Dex 1–251**, has Normal plus all **five** requested varieties: Ancient, Metallic, Shiny, Mystic and Shadow. This includes species not currently obtainable through ordinary wild pools: art/identity coverage is not a new encounter or legendary event system. Supported evolutions preserve the variety. The update does not inject starters, evolved forms or legendary Pokémon into incorrect habitats merely because art exists.

| Variety | Wild probability on fully covered species | Long-run average | Follower effect |
|---|---:|---:|---|
| Normal | 90% | 9 in 10 | Original regular follower; no extra stars |
| Ancient | 2.5% | 1 in 40 | Amber `#FFAA55` |
| Metallic | 2.5% | 1 in 40 | Cyan/silver `#91DCEC` |
| Shiny | 1.25% | 1 in 80 | Gold `#FFF07A` |
| Mystic | 2.5% | 1 in 40 | Violet `#C49AFF` |
| Shadow | 1.25% | 1 in 80 | Pink/magenta `#F879B3` |

Any non-Normal variety has **10% combined probability** for fully covered species. These are independent random rolls, not guarantees within ten/forty/eighty encounters; there is no pity counter. They are **NXT-specific, Vortex-inspired rates**, not asserted numeric Vortex odds. Both Ancient and Metallic remain distinct because both were requested. Dark was not requested and is not added. Varieties are cosmetic: no HP/damage/status/catch-rate bonuses, new moves or battle typing changes are introduced.

The server first chooses species and level through the existing FireRed/Crystal map, terrain, floor and time-of-day resolver, then makes one variety roll out of 10,000 integer tickets. Grass, cave and Surf use the same path. A client cannot supply a species, level, variety or rarity result. Trainer parties, NPC teams and new starters remain Normal unless explicitly authored otherwise; an account named “Wild” is not a generation shortcut. The existing MMO encounter cooldown/chance is unchanged.

### Additional catalog profiles and transparent limits

The 877-profile catalog includes later-generation Pokémon and Sigma/form entries, not just the 251 Kanto/Johto species. The importer binds **3,697** supplied fronts: Ancient 677; Metallic 755; Shiny 755; Mystic 755; Shadow 755. **677 profiles** have all five supplied fronts. The other 122 existing Shiny bindings retain native Shiny artwork, so every catalog profile still supports its existing Shiny identity. All Kanto/Johto requirements are fully covered.

For additional profiles with no matching art for a rolled variety, that ticket produces Normal **without retrying or redistributing the other varieties' probabilities**. A supported evolution retains an already-owned variety even when the extra-form destination has no supplied front; its regular front is used with an explicit art-availability notice in the summary/evolution preview. No unsupported art is invented or recoloured. The exhaustive per-species audit lists exactly what is supplied, native fallback or missing.

Source fronts were converted to PNG with lossless visible pixels. Excess transparent padding is trimmed and the artwork is centred in a square canvas sized to at least the native front and the full visible artwork. No visible pixels are scaled, clipped or recoloured by this authoring conversion. Runtime presentation remains bounded/pixelated; large images cannot expand UI cards or battle layout.

## Battle and collection presentation

**All player-side Pokémon use a horizontally flipped front sprite**, even Normal. Enemy sprites use the front without flipping. Back assets remain untouched in the native library for preservation but are not used by battle rendering. Sprite mirroring is composed into every player-side animation keyframe as well as its steady CSS state, so attacking, getting hit, appearing and fainting cannot temporarily reveal an unflipped/back image. Damage/HP text is not mirrored, and the player's lunge direction remains toward the opponent.

Event-time UUID and variety are attached to combat events. Switching between two varieties of the same species, residual damage and faint sequences resolve the outgoing identity correctly instead of borrowing the final party leader's art. Capture events describe the target's identity even though the acting side is the owner using the ball.

Party/storage cards, the collection variety dropdown and search, summaries, battle, trade offers and trade picker, move reminders and evolution previews share one sprite/name resolver. The Pokédex displays only varieties actually seen/caught by its owner. Learning/evolution rules remain based on canonical species, not prefixed display names. Capture, PC moves, trading and supported evolution preserve the creature's identity and UUID. Invalid requests and failed saves retain the existing transactional rollback behavior.

## Followers and multiplayer

Followers continue to use the **unchanged regular native icon sheets**, including Shiny; no front/back artwork is substituted into the overworld and no directional sheets are fabricated. The server publishes `followerVariety` with the normal nearby-player entity. A same-species party leader change to another variety updates that public identity even while standing still. Nearby clients render the matching effect locally, without sending per-frame particle data or leaking the owner's PC/dex.

Each non-Normal follower uses at most **four** deterministic time-based stars with a distinct colour, an approximately 1.8-second cycle and no accumulating particle objects. Canvas state is restored after drawing. Reduced-motion settings replace the animation with two static markers. Normal followers have no additional effect. Offline/logout and map/party updates use the existing entity lifecycle.

## Preserved systems

The accepted regional encounter species/levels/weights and Crystal morning/day/night timing remain unchanged. The **959-map** audit and **120 personal HM trees** are retained. Kanto Cut still unlocks after Misty/Cascade and Johto Cut after Bugsy/Hive, independently; saved personal tree removal, other-player collision, account ownership, badges, quests and selected moves are preserved. The battle-screen/timer fix and existing music/cry/audio cancellation behavior remain in place.

This release does not add fishing, Headbutt, contest/swarm/roaming or scripted legendary encounters, missing Sigma campaign scripts, new regions, additional evolution methods, Vortex stat perks, automatic distribution of rare Pokémon or a new map geometry importer.

## Authoring and validation

`Server/data/varieties.json` is the authoritative format-1 policy and source-art manifest. It records integer weights totaling 10,000, ordered IDs, labels, effect colours, exact asset paths, source hashes and output hashes. `Tools/publish_varieties.py` validates it, refuses unsafe/missing/mismatched files, requires all 251 complete species, publishes the shared species/policy bindings and regenerates the coverage audit. `Tools/repack_content.py` invokes the publisher and recomputes the shared pack; normal builds use the checked-in converted PNGs without network requests.

Ordinary validation:

```sh
python Tools/repack_content.py
python -m unittest discover -s Tests -v
node --test Tests/check_*.mjs
python Build/build.py --existing-environment --no-open
```

The last command is the optional developer verification mode; it does not enforce production package pins. Windows users should normally use `BUILD_ALL.bat`, which retains the established pinned environment workflow. Browser checks require separately installed Playwright/Chromium:

```sh
NXT_QA_BRIDGE=1 NXT_QA_OUTPUT=/tmp/nxt-varieties python Tests/check_varieties_browser.py
NXT_QA_BRIDGE=1 NXT_QA_OUTPUT=/tmp/nxt-cut python Tests/check_cut_browser.py
```

The bridge is an explicit local QA transport used where native loopback browser navigation is restricted; it does not establish native Edge/Windows/WebSocket/TLS/MySQL deployment acceptance. `POKEMON_VARIETIES_TEST_REPORT.md` gives the exact executed checks and remaining native acceptance.

Optional future asset reimport requires the original extracted front directory plus Pillow; use `python Tools/import_variety_assets.py --help`. Keep stable IDs and explicit aliases; do not fuzzy-match future species at runtime. Reimport requires republishing and deploying matching Client/Server. Vortex tier inspiration reference: https://wiki.pokemon-vortex.com/wiki/Variant. Original artwork rights are not assigned by this update; see `THIRD_PARTY_NOTICES.md`.
