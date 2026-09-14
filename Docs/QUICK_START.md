# Pokemon NXT MMO · Windows quick start

For the complete 0.3.0 gameplay and operator guide, see [ADVENTURE_GUIDE.md](ADVENTURE_GUIDE.md). This page covers setup and the first multiplayer test.

## Source edition: automatic build prerequisites

The source `BUILD_ALL.bat` now downloads/installs missing Go and Python and produces `dist/build-<timestamp>`. No manual Go installation is needed. Follow this quick-start in that new output. Its server dependency BAT recognizes the bootstrapped Python on the same PC even without PATH/`py.exe`. A different server-only PC still needs its own Python runtime. See `AUTOMATIC_BUILD.md`.

## 1. Extract the complete package

Use a normal writable folder, for example `C:\Games\PokemonNXT`. Do not launch an EXE from inside the ZIP. Keep `Client/app` beside the client EXE and `Server/data`, `Server/nxt` and `Server/server.py` beside the world launcher. Avoid protected installation directories during this private alpha.

The client is Windows x64 and uses installed Microsoft Edge in a dedicated app window. The server needs **64-bit Python 3.11 or newer** with the Python launcher and a running **MySQL 8.x** installation. The PyMySQL driver also supports MariaDB, but compatibility with your particular MariaDB/XAMPP version still needs acceptance testing. PHP and Apache are not used by NXT.

Windows executables are unsigned development builds. Review their included source and file hashes under your normal security policy; do not disable operating-system protections to run them. A native Windows launch was not available in the build environment.

## 2. Install the world service dependencies

Start your MySQL service. In the `Server` folder, run:

```text
1 - Install Server Dependencies.cmd
```

This creates `Server/.venv` and installs the requirements there. It does not install Python itself or modify the other game's environment. Initial dependency installation needs internet access. A failed install leaves its error visible in the console; resolve that error before continuing.

## 3. Configure a separate MySQL database

Run:

```text
2 - Configure MySQL.cmd
```

The corrected setup opens a normal password form with masking dots, native paste/selection and a **Show passwords** checkbox. The defaults are host `127.0.0.1`, port `3306`, database `pokemon_nxt_mmo` and application user `pokemon_nxt`.

**Existing administrator password** means the password ALREADY assigned to the MySQL account, usually `root`. This does not create a root password, and it is not your Windows password or a game account. Leave it blank ONLY if that existing MySQL account truly has no password. The field passes an empty value unchanged; it cannot bypass authentication. The installer never changes root's password.

Click **Test administrator login (no changes)**. Correct the fields and retry in the same window if needed. Connection/refused-password/privilege/TLS failures have distinct explanations. Start XAMPP's MySQL service first when that is your database installation; use the actual port you configured there.

Accept `localhost` for the account's world-server host when MySQL and the world service are on the same PC. Leave BOTH **NXT application password** boxes blank to generate a strong password on a fresh configuration or reuse an existing matching configured password. To choose a custom application password, enter the same 12-256 character value in both boxes. Do not reuse the administrator field for this new password.

Click **Configure NXT database and save**. The verified APPLICATION password is written only to `Server/config.ini`, never to clients. The ADMINISTRATOR password is not written to that file. `POKEMON_NXT_DB_PASSWORD`, when set, overrides the INI at runtime; setup now rejects a mismatching stale override before provisioning instead of silently saving unusable credentials.

The workflow creates a separate NXT database and grants the dedicated application user access to it. It does not drop databases, alter root or touch Pokemon Vortex tables. A reused application account is verified before DDL; an unknown existing application password is not reset. Supply it or choose a NEW dedicated username such as `pokemon_nxt2`, while keeping the same NXT database name to retain its data. MySQL creation/grant operations may partly succeed before a later failure; setup does not claim transactional rollback of DDL. Failed logins do not replace config.ini.

`Server/MYSQL_SETUP_FIX.md` explains the corrected flow and console fallback. The GUI works without adding a pip UI dependency when the Python installation includes Tcl/Tk; otherwise an interactive masked console fallback is used.

Schema tables are created automatically on the first successful world startup. Tables use InnoDB on MySQL. Database schemas newer than this server are rejected instead of downgraded. This is schema version 1; no old NXT production schema is assumed to exist.

## 3b. Set up internet hosting, if needed

For internet players or the error **Cannot load TLS files**, run **`2b - Configure Online Hosting.cmd`**. Enter the public IP/domain players will use and generate a private-world certificate, or import your existing certificate/key. It saves matching TLS settings and creates a public-only player connection kit. Keep your already configured MySQL settings.

Follow **`ONLINE_HOSTING.md`** for trusting a generated certificate on each player PC, matching client settings and forwarding the game port. The local/LAN plaintext examples below apply only when you have kept TLS off for isolated LAN testing. Once TLS is enabled, use the kit's hostname/port and `tls=true` on every client.

## 4. Start the administrator console

Run:

```text
3 - Start World Server.cmd
```

Alternatively open `Pokemon NXT World Server.exe`. A successful startup prints the world name, content pack, listen address, database backend and player cap. **Confirm it says `Database: mysql` for your MySQL acceptance test.** Keep this console open.

The default world listener is `0.0.0.0:7777`. `0.0.0.0` is a bind address, not a client join address. The administrator uses the console, not an in-game admin account.

The HTTP health endpoint is `/health` on the configured world port. It reports public status and pack metadata, not credentials. Startup failures are also recorded under `Server/logs/world.log`.

## 5. Connect the client on the same PC

Leave `Client/config.ini` as:

```ini
[server]
host=127.0.0.1
port=7777
tls=false
```

Launch `Client/Pokemon NXT MMO.exe`. The window starts at login. A stopped world produces a connection error rather than loading an offline mock world. Select **Create account**, enter a username of 3–20 ASCII letters/digits/underscores and a password of 10–128 characters, choose a region/appearance/starter, then enter.

Usernames are unique case-insensitively and become the visible nameplate. Passwords are not remembered by the game. There is no email verification, account recovery or password-change UI in this alpha; use test credentials that are not reused elsewhere.

The six starters are Bulbasaur, Charmander, Squirtle, Chikorita, Cyndaquil and Totodile. New characters start with one level-5 partner, 3,000 currency, 20 Poke Balls and five Potions by default. These amounts are configurable on the server for newly created characters. Starter and home region are independent: any of the six partners can start in either region. On later visits, choose **Log in** and use the same account credentials to continue the saved character.

## 6. Two-PC LAN acceptance test

Keep the world service and MySQL on the host PC. Give the second PC **only the entire Client folder**. On that PC, set `Client/config.ini` to the host's actual private LAN address, such as:

```ini
[server]
host=192.168.1.50
port=7777
tls=false
```

That address is an example, not a detected address. Use the world host's `ipconfig` output. Allow inbound TCP `7777` on the trusted private network for the world service when prompted by Windows Firewall. The listening process is the server virtual environment's Python process. The client never connects directly to MySQL; do not open port `3306` to players.

Create two different accounts and choose the same region. Pallet Town and New Bark Town are convenient meeting points. Move one trainer a tile away if both spawn on the same spot. Click the other trainer/nameplate to challenge or trade. Test General and Trade chat, different followers, item/money exchange, logout/relogin and a server restart. A single account cannot be online twice.

Plaintext LAN mode is only for an isolated trusted test network. Passwords are exposed to a network observer without TLS. Internet connections require the direct TLS setup described in `NETWORK_AND_SECURITY.md`.

## Controls and the adventure loop

| Action | Control |
| --- | --- |
| Move | WASD or arrow keys |
| Interact with a nearby NPC | E, or click the NPC |
| Challenge / trade / inspect / local chat mute | Click another trainer or nameplate |
| Global chat | Enter; select General or Trade |
| Party and Pokémon storage | P |
| Adventure Journal and badge progress | J |
| Pokédex discoveries | G; D remains the move-right key |
| World atlas | M |
| Bag and supplies | B |
| Crisp integer world zoom | + / − or viewport buttons |
| Fullscreen | F11 |
| Extra save, Surf, return home | Right-side field controls |

Walk on tall grass for encounters. **Search for wild** works on encounter terrain. Approach a supported trainer NPC and select **Challenge trainer** to battle its extracted team. Trainer battles cannot be fled or used to catch the opponent's Pokémon. Original trainer sight scripts are not simulated.

There are eight ordered Gym challenges in Kanto and eight in Johto / Sigma. Earn earlier badges in the same region before its later Gym Leaders. Open **J** to review each region's next challenge, saved badges and goals. Completed goal rewards are claimed once from the Journal. **G** opens the searchable seen/caught record; unseen species are not exposed in that view.

### Pokémon Centers, storage and growth

Enter a Pokémon Center, approach Nurse Joy and press **E**. Choose **Yes, please heal my party** to restore party HP, PP and status. There is no remote Restore party button. Nurse and PC services require being within two tiles of the recognized service NPC and free of a battle or trade.

Press **P** to inspect and reorder the party or view PC storage. Deposit and withdraw near a Pokémon Center PC service or through Nurse Joy's **Open Pokémon storage** option. Keep at least one healthy partner in the party; withdrawing requires an empty party slot. Moving away or changing maps invalidates service access.

Inspect a Pokémon when **Growth choices ready** appears. Full move sets receive an explicit forget/decline choice instead of an automatic replacement. Available evolutions can be accepted, paused with **Not now**, and resumed later. Compatible evolution items—including Sigma's Link Cable and Fairy Dust—show their actual names and are used from the Pokémon's inspection panel. Buy supplies near a Poké Mart; owned healing items remain usable in the field.

### Travel, Surf and administrator exploration settings

The atlas can always be viewed and searched, including its interior-map list. Earn two badges in total to receive the **Travel Pass**, which permits travel to visited outdoor waypoints and the two starting towns. Visit other outdoor locations on foot before selecting them as waypoints. Interior maps remain browsable but are not ordinary travel destinations; enter buildings, caves and other interiors through their doors. Unavailable layouts cannot be selected; the search shows up to 120 result cards at a time.

Earn Koga's **Soul Badge** for Kanto Surf, and Morty's **Fog Badge** for Johto Surf. The controls follow the current region's permission. Step onto land before disabling Surf. **Return home** remains available outside battles/trades when an unimplemented original scripted exit leaves you stuck.

Fresh adventure configurations set these `[world]` options:

```ini
allow_alpha_atlas = false
allow_alpha_surf = false
save_interval_seconds = 5
```

Existing server configurations keep their own values. An administrator can explicitly retain `allow_alpha_atlas=true` for unrestricted exploration travel and field purchasing, or `allow_alpha_surf=true` for unrestricted Surf. Restart after changing configuration. These exploration overrides do not re-enable remote party healing or bypass PC proximity.

Important actions save before their success is reported. Movement saves periodically, with five seconds as the fresh default, and the established logout/shutdown saving remains active. **Save now** requests an extra save. Reconnect with **Log in** to continue the same account.

These are authored MMO progression rules using extracted teams and regional assets. They do not execute every original FireRed/Sigma story script, puzzle, ability, move effect or evolution condition. The full supported scope and sixteen Gym Leaders are documented in [ADVENTURE_GUIDE.md](ADVENTURE_GUIDE.md).

## Trading safely

Both trainers must be nearby and free of battles/other trades. The invited trainer must accept. Select up to six Pokemon and item/money quantities, then **Apply edited offer**. The panels above the editor show the server-accepted offers. Local unsent edits disable locking and confirmation until applied.

Both participants lock their current offer, inspect both panels, then confirm the **same revision and digest**. Applied changes reset both locks and confirmations. Neither owner can be left without a Pokemon. A completed swap updates both inventories and an audit record in one transaction. A disconnect, timeout, invalid ownership or failed database transaction cancels or rejects the uncommitted exchange. “Secure exchange” in the UI refers to these ownership checks; it does not make plaintext LAN transport encrypted.

## Local administrator console

Type commands in the **world-server terminal**, not player chat. The console trusts the OS user controlling this server process; no in-game rank grants access. There is no RCON/HTTP admin endpoint or extra port. Windows elevation is not required. Redirected or piped input is not accepted; EOF disables input without stopping the world.

```text
help
who
playerinfo TrainerName
team TrainerName
species Pikachu
givepokemon TrainerName Pikachu 20 ancient
giveitem TrainerName pokeball 10
givemoney TrainerName 1000
heal TrainerName
maps "Azalea Town"
saveall
help teleport
help ban
shutdown 60
```

A destructive command prints **PREVIEW** and a token; nothing changes until you enter `confirm <printed-token>`. Tokens expire after 60 seconds by default and become invalid if the targeted account, session, character or relevant configuration changes. Use `cancel` to discard previews and `cancelshutdown` to cancel a scheduled shutdown/restart. Commands accept exact usernames, `#accountID` or `id:ID`; Pokémon edits require an owned UID or `party:1..6`.

Developer commands are disabled by default. With explicit configuration opt-in, `testbattle TrainerName Pikachu 10 shiny` starts a **cloned AI test duel**, not a capturable wild encounter. The legacy `spawnwild` alias now has that same restricted sandbox meaning. No rewards, captures or gym wins are produced. Player chat, announce, broadcast, whisper and mute commands are intentionally absent.

Use `shutdown`, confirm its token, or press Ctrl+C and wait for **World server stopped cleanly**. `restart` also requires confirmation and is supported by the supplied launchers after successful save/lease release; direct Python invocation exits with 75 for an external supervisor. Do not force-close during saves. Read **`Docs/LOCAL_ADMIN_CONSOLE.md`** for all commands, audit paths, config and scope.

## Explicit developer SQLite mode

After installing dependencies, `Start Developer SQLite World.cmd` starts a separate developer database at `Server/data/development.sqlite3`. MySQL is not required for this explicitly selected mode. The console labels it clearly. It does not convert or import MySQL accounts, and its saves are separate. This is useful for a local first look, **not evidence that your MySQL deployment works**.

## Display settings

Defaults `pixel_scale=0` and `ui_scale=0` select responsive UI sizing, integer world pixel scaling and device-pixel-ratio canvas rendering. The app opens maximized. Text and UI are separate from pixel art. Optional manual values are world scale 1–8 and UI scale 0.8–2.0. Keep both at zero for the default 4K-aware presentation. Test moving the window between monitors with different Windows scaling factors during Windows acceptance.

## Troubleshooting

**Edge not found:** install Edge or provide its complete `msedge.exe` path in `Client/config.ini` under `[launcher] edge_path`. Do not put a URL there. Closing the app causes the loopback helper to exit after its configurable idle period, normally 90 seconds.

**Missing TLS certificate/key:** run `2b - Configure Online Hosting.cmd` in the built Server folder. Restoring only config.ini without its certificate files cannot start a TLS listener. See `ONLINE_HOSTING.md`.

**World unavailable:** start MySQL and the world console; check host/port/TLS on both sides. The remote PC must not use `127.0.0.1` for a world on another PC. Restart the client after changing its INI.

**Access denied / database not configured:** rerun the MySQL setup with correct existing admin credentials and a dedicated app account. Check `POKEMON_NXT_DB_PASSWORD`. Do not change the other game's root credentials. `Check Configuration.cmd` performs a non-mutating configuration/dependency/connection check.

**Content out of date:** use Client and Server folders from the same build. Do not copy only a new EXE over old data. Custom content changes require republishing and deploying the matching packs.

**Too many login attempts:** the default is six new WebSocket login connections per source IP per minute. Repeated manual reconnects or several testers behind one NAT may hit this deliberately conservative limit. Wait a minute; an administrator can adjust the limit for a trusted test while retaining a rate limit.

**Already online:** log the account out of its other window. Use separate accounts for multiplayer. After connection loss, allow cleanup to complete before reconnecting.

**Missing exit or unusual Sigma area name:** extraction preserves repurposed map layouts and stable IDs; original scripts are not running. Use Return home, or the atlas when the destination is available under your Travel Pass or administrator exploration settings. Report the map ID and coordinates with the issue.


## World startup reports another owner or has no log

Startup fix **1.1.2** records startup diagnostics before settings/content/database loading, shows the full log path, and releases its own lease if a later startup stage fails. The original alpha could leave a lease behind after a failed listener/TLS/extension startup while writing no error to world.log.

Use the supplied World Startup Fix hotfix for an already configured Server folder; no rebuilding or MySQL setup rerun is required. Start only one NXT world for the same database. The corrected server automatically waits up to 65 seconds for an abandoned lease to expire; if another world refreshes it, it explains that the running world must be shut down. It never clears a live lease forcibly. A future heartbeat prompts a clock check instead of unsafe takeover.

Read the precise startup cause and log path in the console. For an occupied port, stop the other NXT world or select a free server port and match the client configuration. See `Server/WORLD_STARTUP_FIX.md` and `Docs/WORLD_STARTUP_FIX_TEST_REPORT.md`.
