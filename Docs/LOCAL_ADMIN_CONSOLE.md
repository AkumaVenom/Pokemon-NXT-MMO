# Pokémon NXT MMO — Local administrator console

**Release:** gameplay **0.3.6-alpha**, build tools **1.4.1**. Based on the user-accepted 0.3.5 Pokémon Varieties source with the 1.3.4 Windows build fix. This is Pokémon NXT MMO, not Pokémon Vortex NXT. Proposal selection is recorded separately in `LOCAL_ADMIN_PROPOSAL_AUDIT.md` / `.json`.

**Build 1.4.1 correction:** The temporary SQLite test handles now close explicitly on success and failure. No commands, gameplay data, migration rules or deployment settings are changed. See `WINDOWS_BUILD_FIX_1.4.1.md`.

## 1. Build, upgrade and start

Download **all four** `Pokemon_NXT_MMO_v0.3.6-alpha_Source_ConsoleBuildFix_Part1.zip` through `Part4.zip`. Extract them into the **same new destination**, merging their identical `Pokemon_NXT_MMO_v0.3.6-alpha_Source_LocalAdminConsole` folders. They are ordinary ZIPs, not byte-split volumes: do not concatenate them. Run `BUILD_ALL.bat` only when all four are extracted. The banner should show **build 1.4.1 / gameplay 0.3.6-alpha**. All original game assets are included; no previous patch, ROM, images.rar, image renderer or audio extractor is needed.

Before upgrading a working deployment, **back up its database and configured server**, then stop the old world cleanly. Build into fresh output and deploy the matching new Client and Server. Preserve the existing server `config.ini`, database, certificates/private keys and the client's working connection settings. Do not copy clean templates over private configurations, reset accounts, change passwords or rerun MySQL setup merely to update.

The first new startup automatically adds **schema-2 account-control/audit tables**. An upgrade refuses a recent (or future-clock) old-world lease before adding these tables/advancing the version. Stop the old world first; after an unclean stop, let its abandoned lease expire and retry. Existing account, password, character and trade records are preserved. No privileges are granted to any game account. Existing schema creation permissions are required, as with a fresh installation. DDL failure must be fixed before starting; a failed MySQL connection never falls back to SQLite.

**Rollback requires the pre-upgrade database backup and its matching old deployment.** The old schema-1 server intentionally refuses a schema-2 database. Never manually lower `nxt_schema.version` or delete audit/control tables to force a downgrade. Stop the new server first, restore the backup, and restore matching old Client/Server programs.

Start the built `Pokemon NXT World Server.exe` or `3 - Start World Server.cmd` as usual. Wait for **Local console ready**, then type `help` at **NXT>**. The developer SQLite launcher is still a deliberately separate backend, not a MySQL migration. Its existence does not enable developer commands automatically.

## 2. Trust boundary — local terminal only

The operating-system account that can open/control this world-server console is the administrator. A normal Windows user session can run it; elevation and Developer Mode are not required. Protect the Server folder, console/session and database with appropriate OS permissions. Remote Desktop/SSH or other OS-level access to that same session is outside the game protocol's trust boundary; this feature is not physical-presence attestation.

There is **no RCON port, HTTP admin endpoint, WebSocket admin opcode, player/staff rank, client admin UI or chat command parser**. The existing game listener still only exposes its normal health/world routes. An optional leading `/` is accepted *in this console*, not interpreted in player chat. Naming a game account `Admin` or sending an `OWNER` role in a client packet grants nothing.

Redirected/piped stdin is deliberately not accepted. `--no-console` disables the input task. EOF disables console input but leaves the world running; use a normal terminal or restart through the launcher to regain input. The reader uses a daemon input thread, a 32-entry queue and capacity reservations **before** event-loop callbacks, so a long paste cannot accumulate unbounded callbacks or lose its EOF marker. Lines are limited to 1,024 characters and twenty tokens. Each command runs serially on the world event loop, under the same lock as gameplay. No shell, SQL or Python evaluation command is provided.

## 3. First commands and selection

```text
help
help Pokemon
help givepokemon
who
playerinfo AdminAkuma
team AdminAkuma
collection AdminAkuma
species Pikachu
items ball
moves Tackle
maps "Azalea Town"
```

Use **exact usernames** (case-insensitive), **`#accountID`** or **`id:ID`**, not partial player names. Account commands generally work online or offline; live-session commands such as kick, ipinfo, tradecancel and testbattle require the player online. Do not type square brackets or angle brackets shown in syntax help. Put names containing spaces inside double quotes.

For a Pokémon, use its **exact owned UID** shown by `team`/`collection`, or `party:1` to `party:6`. A species name is not a creature identity. Ownership is checked on every operation. For species, maps, items and moves use a native ID or a unique exact name. Ambiguous duplicate map names reject and list matching IDs; no region is guessed. Catalog searches are substring filters, 50 results per page. `species "" 2` requests page 2 without a filter.

## 4. Practical administration

```text
givepokemon AdminAkuma Pikachu 20 ancient
givepokemon AdminAkuma "Mr. Mime" 18 mystic
giveitem AdminAkuma pokeball 20
givemoney AdminAkuma 1000
heal AdminAkuma
saveall
```

Each grant creates a new unique Pokémon using its real species profile and native level/moves. It enters the party if there is space; otherwise it remains in PC storage. Collection and stack/currency caps reject rather than silently discarding or clamping. The six variety names are **normal, ancient, metallic, shiny, mystic, shadow**. Unsupported extra-form variety art rejects; all 251 Kanto/Johto species retain their complete accepted coverage. Admin grants do not change wild rarity.

All gameplay-changing Pokémon/item/currency/location edits require the target to be outside battle/trade. Heal restores the party, not every stored Pokémon. Healall atomically heals **online idle parties** and explicitly lists skipped busy sessions. Removal keeps at least one healthy party member. Level/EXP/nature/IV edits preserve ownership, variety and chosen move slots; recalculating stats preserves existing damage and does not revive fainted Pokémon. Raising levels uses native learning queues. Lowering levels removes unearned pending choices but deliberately does not erase chosen combat moves. `setexp` chooses the highest valid level threshold at or below the requested total; `setlevel` honors the exact requested level even when low-level thresholds coincide.

`learn` uses an earned pending/native reminder move and an explicit slot; `evolve` honors authored eligibility, deferred choices and required level/stone/trade conditions, consuming the required stone. These are not arbitrary species/move swaps. `addmove` is separately developer-gated. `setivs` input order is **HP ATK DEF SPA SPD SPE**, with each value 0–31. No EV, ability, independent gender or nickname mechanic is invented. `setshiny true` means Shiny and `false` means Normal; use `setvariety` for the other identities.

## 5. Confirmation and failure behavior

```text
setvariety AdminAkuma party:1 shadow
```

This prints a **PREVIEW** and a generated token. **No change has happened yet.** Enter `confirm` followed by that actual token within 60 seconds by default. Tokens are single-use and bind the exact command, target accounts, live/saved character snapshot, current session, battle/trade and relevant config/schedule. Movement or another state update can invalidate a preview. Ask the player to stand still and finish busy gameplay before previewing again. A relogged/replacement session cannot inherit an old kick confirmation. `cancel <token>` discards one preview; `cancel` discards them all.

State candidates are detached copies. Input, ownership, bounds, map collision, developer policy and confirmation are checked before mutation. Character/control changes and their success audit commit **in one lease-fenced database transaction**. Clients receive private state and public follower/map changes only after commit. A database/audit transaction failure rolls the whole batch back and publishes no grant, reward, changed tree or partial account control. A newer stored revision rejects rather than overwriting it. Cancellation waits for an admitted commit and publication before shutdown/logout can save.

The local audit must be writable before execution. If its final append fails **after** the database commits, the console explicitly says **COMMITTED** and points to the authoritative database audit: **do not repeat the command**. If an unexpected live-presentation operation fails after commit, the console reports the same committed status and stops the world safely for inspection/recovery; it does not falsely promise rollback or retry a grant.

## 6. Moderation, account restrictions and passwords

```text
warn AdminAkuma "Please return to the permitted testing area"
kick AdminAkuma "Maintenance check"
ban AdminAkuma 2h "Testing account restriction"
unban AdminAkuma
lockaccount AdminAkuma "Owner maintenance"
unlockaccount AdminAkuma
freeze AdminAkuma
unfreeze AdminAkuma
blocktrade AdminAkuma true
blocktrade AdminAkuma false
warnings AdminAkuma
history AdminAkuma 20
```

Read the printed preview/confirmation requirement for each command. Ban accepts `permanent` or bounded durations such as `30s`, `10m`, `2h`, `7d` (maximum 365 days); a timed ban starts when confirmation executes. Ban expiry is checked on admission without a restart. An independent lock remains after unban, and a ban remains after unlock. Login rechecks the control record and verified password hash **after** expensive verification, under the admission lock, so a reset/lock/ban racing authentication wins before a player is published.

Freeze persists across relog/restart and blocks gameplay actions while leaving login, existing chat, ping, save and logout available. It is applied only while the target is idle, avoiding an unwinnable frozen live battle. Movement rejection carries the normal authoritative acknowledgement so client prediction can settle. Trading restrictions persist, reject both invitation directions, and cancel an active trade/offer only after the restriction is saved. No uncommitted assets are exchanged by trade cancellation. Warnings use an ordinary private notice, not a new chat/announcement command.

`resetpassword <player>` requires confirmation, generates a fresh strong password and displays it **once in this local terminal after successful commit**. It does not accept a password argument; there is no password in a command line, local audit or DB audit. Existing sessions are disconnected and in-flight old-password logins are rejected. Hand the new password to the account owner through your own secure channel and protect terminal scrollback/session recordings. A failed reset does not display a new password and leaves the old hash valid. There is no password-recovery email or forced-change UI added in this release.

## 7. World, maintenance and diagnostics

`teleport <player> <map> [x y]` uses the map's safe spawn when coordinates are omitted, or validates an explicit land tile. It does not place players on walls, water, blocked objects or warps. Personal HM-tree collision is evaluated for that specific character. Home, badges, personal Cut flags, Pokémon and other progress are preserved; stale interior return stacks are cleared. `goto <player> <destination-player>` (alias `bring`) chooses a safe nearby tile and has **no implicit console avatar**. `unstuck <player>` returns to the safe home spawn without granting a badge.

`saveall` (alias `dbsave`) checkpoints all online characters in a transaction, including current party checkpoints during battles; it does not resolve or award unfinished battles. Completed turns already use the existing durable battle transaction. `save <player>` checkpoints one target; `save` with no target is the same all-online operation. These commands do not claim to force the database engine's physical storage hardware to flush beyond its own commit settings.

`shutdown [seconds]` and `restart [seconds]` accept 0–3,600 seconds and require confirmation. `cancelshutdown` cancels a scheduled operation before shutdown starts. Scheduled notices are private maintenance notices, not a general announcement/chat interface. Clean shutdown stops admission, finishes admitted operations, saves characters, closes sockets and releases this world's lease. The supplied EXE/CMD launchers restart **only** on exit code **75** returned after a successful requested clean restart; crashes, failed saves and other errors do not auto-restart. Running Python directly returns 75 for a supervisor rather than spawning another Python process itself. Ctrl+C remains a direct OS request for clean shutdown and is not confirmation-gated.

`serverinfo` reports actual population, pack, battle/trade counts and tick timings. `time` reports real server-local time and Crystal's encounter period; it does not override day/night. `memory` reports actual OS working-set/RSS when available plus Python GC counters; `gc` does not promise memory will return to the OS. `connections`/`ipinfo` show current directly connected peers only in this trusted terminal, not fabricated historical addresses or geolocation. Keep these readouts private. `economy` aggregates real stored accounts and live balances using bounded DB pages; it is an explicit administrative aggregate, not an untrusted player query.

## 8. Configuration and safe reload

Old working configurations need no edits for normal console access. These optional defaults also appear in clean templates:

```ini
[console]
enabled = true
allow_developer_commands = false
disabled_commands =
confirmation_seconds = 60
```

`disabled_commands` is a comma-separated list, e.g. `givepokemon, setmoney, gp`; aliases resolve to their canonical command and cannot bypass a restriction. Unknown names/options and invalid bounds fail closed with an actionable startup/config error. Help, confirmation and cancellation controls cannot be disabled individually. Confirmation lifetime must be 15–300 seconds. Turning `enabled` off disables the whole console; re-enabling then requires editing the file and a restart.

After editing, type `reloadconfig` and confirm its token. Reload accepts **only `[console]` and `[world] registration_enabled`**. Changes to DB/network/TLS/content/gameplay values reject; restore those edits or perform a clean restart. The file is re-read at confirmation and a changed config invalidates the preview. The console never rewrites your config. Successful reload clears pending confirmations. No live script/content reload, arbitrary shell/test runner or cache-clearing shortcut is installed.

## 9. Developer tests — explicit opt-in

Set `allow_developer_commands = true`, reloadconfig and confirm. This grants no rights to player clients; it only reveals the ten local developer commands. Turn it back off after testing.

```text
testbattle AdminAkuma Pikachu 10 shiny
win AdminAkuma
clonepokemon AdminAkuma party:1
```

A console test battle is a specially tagged **AI duel with cloned rosters**, no real battle items and no capture/reward/EXP/currency/gym effects. `win`, `lose` and `endbattle` can finish only this kind of battle. They reject normal wild/trainer/gym/PvP battles. The legacy `spawnwild` alias has this same new sandbox meaning; it is not a reward-bearing wild encounter. `clonepokemon`, `sethp`, `setstatus`, `addmove`, `clearmoves` and `createaccount` are deliberate testing tools affecting the selected real character or creating an ordinary account, so use a disposable testing account. The gate is not a separate database sandbox for those edits.

Supported test statuses are none, burn, poison, toxic, paralysis and sleep; unsupported freeze-status mechanics are not invented. `createaccount <username> <Kanto|Johto> <starter>` requires confirmation and creates a normal account with a generated password shown once. No account deletion/reset, staff rank ladder or reward-bearing forced-battle result is added.

## 10. Audit, preservation and testing

Local attempts/previews/rejections/successes are recorded in **`Server/logs/admin-console.jsonl`**, rotating at about 4 MB with five older files. Successful operations also live in DB **`admin_audit`** plus **`admin_audit_targets`**, transactionally with their changes, ordered by an increasing audit sequence. The actor is `LOCAL:<OS user>@<host>`; records include time, canonical command, validated arguments, account IDs, source revisions and concise action details. Account restrictions live in `account_controls`. Full character snapshots, password hashes, plaintext passwords, DB credentials and certificates are not copied into these audits. `history`, `warnings`, `tradehistory` and bounded `logs` expose only their documented records locally. Protect and back up audits; no automated destructive retention/purge command is provided.

All prior image/audio bytes, five extra varieties and rarity policy, mirrored-front battles, follower sparkles, FireRed/Crystal encounter data and personal Cut behavior are retained. Startup/build publishing selects the new console modules and docs and excludes live configs, DBs, logs, private keys and tool caches. The previous Windows link-free variety tests remain enabled.

See **`LOCAL_ADMIN_TEST_REPORT.md`** for actually executed checks and platform limitations. The optional `Tests/ui_acceptance.py` now runs the maintained variety/Cut browser fixtures with disposable in-process services; it no longer relies on piped legacy admin input. No production pipe bypass or browser-accessible admin endpoint is introduced. Native Windows/Edge and live MySQL must be checked on the deployment; Linux/SQLite tests and Windows cross-compilation do not prove those results.

## 11. Complete installed command reference

All commands below are local-only. “Confirm” means an expiring, unchanged-state preview is mandatory. “Dev” requires the configuration gate. Help omits disabled/dev-locked commands dynamically. Aliases follow exactly the same policy and syntax as their canonical command.

### Console

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `help [command\|category]` | commands | Validated | Filtered command help and exact syntax. |
| `confirm <token>` | — | Validated | Execute one unexpired, unchanged destructive preview. |
| `cancel [token]` | — | Validated | Discard a pending destructive preview, or all previews. |

### Information

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `serverinfo ` | status | Validated | Version, pack, uptime, sessions, battles, trades and tick timing. |
| `who [page]` | players | Validated | Online account IDs, names and maps; 50 per page. |
| `online ` | — | Validated | Current online player count. |
| `version ` | — | Validated | Gameplay version, content pack and console protocol. |
| `uptime ` | — | Validated | Elapsed time for this world process. |
| `time ` | — | Validated | Actual server-local clock and current Crystal encounter period. |

### Players

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `playerinfo <player>` | profile, stats | Validated | Account/character summary without credentials. |
| `where <player>` | location | Validated | Authoritative saved/current location. |
| `team <player>` | pokemon | Validated | Party slots, stable Pokémon IDs, varieties, levels and HP. |
| `collection <player> [page]` | — | Validated | Owned Pokémon IDs, including PC storage; 50 per page. |
| `pokemoninfo <player> <uid\|party:N>` | — | Validated | Detailed owned Pokémon, growth and moves. |
| `bag <player>` | — | Validated | Current inventory with stable item IDs. |
| `money <player>` | balance | Validated | Current currency balance. |

### Catalog

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `species [query] [page]` | — | Validated | Find exact species keys and available varieties. |
| `items [query] [page]` | — | Validated | Find item keys and names. |
| `moves [query] [page]` | — | Validated | Find move IDs and names. |
| `maps [query] [page]` | — | Validated | Find playable map IDs, region and safe spawn. |
| `iteminfo <item>` | — | Validated | Inspect an existing item definition. |

### Pokemon

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `givepokemon <player> <species> [level=5] [variety=normal]` | gp | Validated | Grant a new unique Pokémon; overflow remains in PC storage. |
| `removepokemon <player> <uid\|party:N>` | rp | Confirm | Remove one owned Pokémon, preserving a viable party. |
| `heal <player>` | — | Validated | Restore party HP, status and PP. |
| `healall ` | — | Confirm | Atomically heal all online idle parties; busy players are listed/skipped. |
| `evolve <player> <uid\|party:N> [target]` | — | Validated | Apply an eligible authored evolution, consuming its item when required. |
| `setlevel <player> <uid\|party:N> <1..100>` | — | Confirm | Set exact level/threshold XP; preserve identity and chosen moves. |
| `setexp <player> <uid\|party:N> <total>` | — | Confirm | Set bounded species-curve total XP and corresponding level. |
| `learn <player> <uid\|party:N> <move> <slot:1..4>` | — | Validated | Teach an earned native move into an explicit slot. |
| `forget <player> <uid\|party:N> <slot:1..4>` | — | Confirm | Forget one chosen move; empty moves use existing Struggle. |
| `setnature <player> <uid\|party:N> <nature>` | — | Confirm | Set a supported nature by name or 0..24 ID. |
| `setivs <player> <uid\|party:N> <HP ATK DEF SPA SPD SPE>` | — | Confirm | Set six IVs (0..31); recalculate stats without healing damage. |
| `setvariety <player> <uid\|party:N> <variety>` | — | Confirm | Set Normal/Ancient/Metallic/Shiny/Mystic/Shadow with verified art. |
| `setshiny <player> <uid\|party:N> <true\|false>` | — | Confirm | Compatibility form: true=Shiny, false=Normal. |

### Inventory

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `giveitem <player> <item> <1..999>` | gi | Validated | Add to an existing supported inventory stack. |
| `removeitem <player> <item> <1..999>` | — | Confirm | Remove an exact quantity, never silently clamp. |
| `setitem <player> <item> <0..999>` | — | Confirm | Set an exact supported item stack. |
| `clearinventory <player>` | — | Confirm | Clear bag items only; not Pokémon, badges or money. |

### Economy

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `givemoney <player> <amount>` | — | Validated | Add currency within the existing 2,000,000,000 cap. |
| `removemoney <player> <amount>` | — | Confirm | Remove currency only when the balance covers it. |
| `setmoney <player> <0..2000000000>` | — | Confirm | Set an exact balance. |
| `economy ` | — | Validated | Aggregate account and currency totals, including live balances. |

### World

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `teleport <player> <map> [x y]` | tp, teleportplayer, setlocation | Validated | Move to a verified walkable tile; never bypass object collision. |
| `goto <player> <destination-player>` | bring | Validated | Move an explicit player to a safe tile near another player. |
| `unstuck <player>` | — | Validated | Return a character to its safe home spawn; no badge grants. |

### Trading

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `tradecancel <player>` | — | Validated | Cancel an active trade/invitation without transferring assets. |
| `tradehistory <player> [limit:1..100]` | — | Validated | Inspect committed trades for an account. |
| `blocktrade <player> <true\|false>` | — | Confirm | Persistently block/unblock trading; cancel an active offer on block. |

### Moderation

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `warn <player> <reason>` | — | Validated | Record a durable warning; notify an online player privately. |
| `warnings <player> [limit:1..100]` | — | Validated | Read recorded local-console warnings. |
| `kick <player> [reason]` | — | Confirm | Disconnect the selected online session; never a replacement session. |
| `ban <player> <permanent\|10m\|2h\|7d> <reason>` | — | Confirm | Persist a timed or permanent login ban and disconnect. |
| `unban <player>` | — | Confirm | Remove the account ban without clearing an independent lock. |
| `freeze <player>` | — | Confirm | Persist an idle-player gameplay freeze; chat/login remain available. |
| `unfreeze <player>` | — | Validated | Remove the gameplay freeze. |
| `history <player> [limit:1..100]` | — | Validated | Read the transactional administrative audit for an account. |

### Accounts

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `lockaccount <player> <reason>` | — | Confirm | Persist a login lock independent of bans; disconnect if online. |
| `unlockaccount <player>` | — | Confirm | Remove only the independent account lock. |
| `resetpassword <player>` | — | Confirm | Generate a fresh strong password, show once here, then disconnect. |

### Diagnostics

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `connections ` | — | Validated | Local-only session IDs, names and directly connected peer addresses. |
| `ipinfo <player>` | — | Validated | Local-only current transport peer; no fabricated historical IP. |
| `gc ` | — | Validated | Request Python cyclic garbage collection and report collected objects. |
| `memory ` | — | Validated | Report actual process memory where supported and GC counts. |
| `threads ` | — | Validated | List current process thread names/IDs. |
| `logs [lines:1..100]` | — | Validated | Read recent local console audit events, with bounded output. |

### Maintenance

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `save [player]` | — | Validated | Checkpoint one account, or every online account when omitted. |
| `saveall ` | dbsave | Validated | Checkpoint every online character atomically. |
| `reloadconfig ` | reload | Confirm | Reload only console policy and registration_enabled; reject other edits. |
| `shutdown [seconds:0..3600]` | stop, quit | Confirm | Schedule a clean save/disconnect/lease-release shutdown. |
| `restart [seconds:0..3600]` | — | Confirm | Cleanly stop and ask the supplied launcher to restart (exit 75). |
| `cancelshutdown ` | — | Validated | Cancel a scheduled shutdown/restart before it begins. |

### Developer

| Command and arguments | Aliases | Gate | Behavior |
|---|---|---|---|
| `createaccount <username> <Kanto\|Johto> <starter>` | — | Dev + Confirm | Create an ordinary test account; show generated password once locally. |
| `clonepokemon <player> <uid\|party:N>` | — | Dev + Validated | Copy one Pokémon for testing with a new unique ownership ID. |
| `testbattle <player> <species> [level=5] [variety=normal]` | battle, spawnwild | Dev + Validated | Start a cloned AI test duel: no real rewards/capture/items or gym wins. |
| `win <player>` | — | Dev + Validated | Finish only a console-created test duel as a win. |
| `lose <player>` | — | Dev + Validated | Finish only a console-created test duel as a loss. |
| `endbattle <player>` | — | Dev + Validated | Cancel only a console-created test duel. |
| `sethp <player> <uid\|party:N> <hp>` | — | Dev + Confirm | Set a test Pokémon HP within its real stat bounds. |
| `setstatus <player> <uid\|party:N> <none\|burn\|poison\|toxic\|paralysis\|sleep>` | — | Dev + Confirm | Set only statuses the battle engine implements. |
| `addmove <player> <uid\|party:N> <move> <slot:1..4>` | — | Dev + Confirm | Teach any existing move into an explicit slot for testing. |
| `clearmoves <player> <uid\|party:N>` | — | Dev + Confirm | Clear moves for testing; the existing Struggle fallback remains. |
