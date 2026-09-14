# Native content and extension workflow

## No ROM needed for future native edits

Runtime data is ordinary PNG plus versioned JSON. The complete build already contains its extracted assets. `Tools/repack_content.py` uses only Python's standard library and can publish future edits without either ROM, the extractor, Pillow or numpy.

Keep a clean version-controlled baseline and stop the world before publishing. Back up the database/content first. Edit the authoritative `Server/data/world.json`, add your licensed assets under `Client/app/assets`, then run from the full project root:

```text
python Tools/repack_content.py
python -m unittest discover -s Tests -v
```

The publisher validates key references, map grid dimensions, safe spawns, asset paths, encounters and learnsets. It hashes PNG contents into an asset digest, computes a pack ID over native data and that digest, and writes server/client metadata. Deploy the new server content and matching entire client asset pack together. Clients with a different pack ID cannot authenticate. There is no automatic patch server.

Publishing uses atomic replacement for individual JSON files, not a multi-file live transaction. Therefore stop the world and complete deployment before restarting. A pack ID is a content-version contract, not a DRM system or proof that an untrusted client has not modified local rendering.

## Add a species or form

Choose a new stable key, such as `custom_001`; never reuse an old key for an unrelated creature. Copy a compatible existing catalog entry as a schema reference. Supply name, types, six base stats, growth/catch/experience metadata, learnset and all five sprite paths (`front`, `back`, `shiny`, `backShiny`, `icon`). Battle assets in this pack are generally 64×64. Follower icons use a 64×32 horizontal strip containing two 32×32 frames. Alpha rendering expects that icon layout.

Use existing valid move IDs in the learnset, and verify the combat engine supports those effects; merely defining a JSON move does not implement its behavior. Author an explicit supported table in the encounter catalogs/bindings with valid species and level slots or opt in to developer commands and use `testbattle <player> <species> [level] [variety]` for a cloned, non-capturable AI duel with no progression rewards. The old `spawnwild` alias has this same safe test-duel meaning; it no longer creates a reward-bearing wild battle. Asset-only catalog additions are not automatically inserted into wild tables.

Do not remove species referenced by saved accounts. Renaming a display name is different from renaming a stable species key. A species migration needs an explicit conversion of existing character records and a backup/rollback plan. Forms/custom entries are not assumed to be distinct national-Pokedex species.

## Add or edit a map

Use a unique stable map ID. Grid cells are 16×16 native pixels, row-major arrays indexed by `y*width+x`. `collision`, `elevation` and `behavior` must each contain exactly width×height entries. The renderer uses a ground image and an optional foreground overlay; `image` is the flattened extraction preview. Images must align to the native map grid. Retain transparent foreground pixels and nearest-neighbor art scaling.

Provide a safe non-collision spawn, name, region, bank/map/section metadata, mapType, connection/warp records, NPC object entries and encounters. Copy a small known-good map as a schema guide rather than guessing field structures. Set `playable=false` for non-walkable placeholders. Test ordinary movement, walls, boundaries, elevation, native warps, NPC interaction, surf and server-side collision rejection. The publisher validates structure but does not prove semantic reachability of the whole map.

New original script effects require new authoritative server behavior. Adding a picture of a door, gym or trainer does not create its quest progression. Keep area IDs stable and migrate saved positions deliberately after geometry changes.

## Replace trainer/follower graphics

Object graphics metadata is grouped by source tag. Each sheet contains horizontal frames with declared width/height/frame count and visibleTop. The current walking renderer interprets down/up/left frames and mirrors left for right. A genuinely directional Pokemon follower set requires a new explicit animation metadata format plus rendering changes; do not pretend a two-frame icon has four directional animations.

Lead species and its current follower tile come from server entity packets. Keep that authority when improving animation. Cosmetic interpolation should not alter collision, ownership or movement decisions. Retired map layers are released from the renderer's image registry on map change, rather than accumulating all visited full-size maps indefinitely.

## Server functions and future trainer bots

Use `Server/extensions/README.md` for the current hook boundary. Add trusted `.py` modules with `register(world)`, or extend the modular server code and protocol with tests. Hooks are short synchronous callbacks; no blocking I/O or nested world lock acquisition. A disabled example is included.

Bots are **not implemented**. A future bot controller should schedule server intents, honor existing collision and battle rules, keep bounded per-tick work, and persist its own versioned state. New inventories or ownership actors require migration and transaction tests. Do not fake bot HP/captures/trades in a client or bypass player validation for convenience.

## Re-extracting the original files (optional developer task)

Only a fresh extraction needs the two original files supplied by the user. Install Pillow and numpy in a developer environment, not on player clients. The extractor accepts both paths:

```text
python Tools/extract_assets.py --firered "C:\PrivateSources\FireRed.gba" --sigma "C:\PrivateSources\Sigma.gba" --output "Client/app/assets"
python Tools/prepare_world.py "C:\PrivateSources\FireRed.gba" "C:\PrivateSources\Sigma.gba"
python Tools/repack_content.py
```

`--output` is the client asset directory, not the project root. Re-extraction is destructive to generated content and should happen in a separate checkout, not over a manually edited live pack. The exact input hashes and tables are audited in ASSET_REPORT.json. Other revisions/hacks may relocate tables or change formats and are not guaranteed compatible. No ROMs are included in the release.

## Rebuild Windows launchers

Each launcher is a standalone Go module with no third-party Go modules. On a machine with Go installed, open a CMD terminal in its launcher folder:

```bat
rem Client/launcher
set GOOS=windows
set GOARCH=amd64
set CGO_ENABLED=0
go build -trimpath -ldflags="-s -w -H=windowsgui" -o "..\Pokemon NXT MMO.exe" .

rem Server/launcher (separate terminal or cd there)
set GOOS=windows
set GOARCH=amd64
set CGO_ENABLED=0
go build -trimpath -ldflags="-s -w" -o "..\Pokemon NXT World Server.exe" .
```

`-H=windowsgui` is intentionally only for the client; the server needs its console. Review and test any rebuilt binaries on Windows before distribution. No font files are bundled by this project; the UI uses installed system fonts.
