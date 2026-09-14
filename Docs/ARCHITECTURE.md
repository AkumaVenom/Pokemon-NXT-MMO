# Architecture and invariants

## Processes and boundaries

The Windows x64 client launcher serves `Client/app` on a random loopback port and opens installed Edge with an app-window URL and temporary profile. `/bootstrap` exposes only connection/display settings and a helper heartbeat token. Static serving cannot traverse to the private Server folder and does not offer directory listings. The helper checks the Host header, restricts the content policy, serves no CDN scripts and listens only on 127.0.0.1. Runtime asset loading uses PNG and JSON, never the GBA images or emulator code.

The actual multiplayer transport is a WebSocket from the client to the configured world listener, using subprotocol `nxt.v1`. Only `/health` and `/world` are routed by the service. The administrator console is standard input in the separate server process, not an HTTP administration API or client role.

`server.py` owns network admission, authentication, startup/shutdown, logging, periodic jobs and console commands. `nxt/config.py` validates configuration. `nxt/security.py` validates values, rate limits and hashes passwords. `nxt/content.py` loads native data and creates/calculates creatures. `nxt/world.py` owns world intents, movement, social invitations, ownership and replication. `nxt/combat.py` is the alpha singles resolver. `nxt/store.py` is the MySQL/SQLite persistence boundary. Client `renderer.js` owns world pixels and picking; `app.js` owns UI/protocol state; `styles.css` controls responsive presentation.

## Network handshake and intents

The server first sends `hello` with version, pack, world name and cap. The client submits `auth` with mode, credentials and matching pack; registration also selects home, starter and appearance. Successful admission emits `joined`, `map`, private `state` and chat history. Authentication is mandatory before gameplay; no local offline login is accepted.

Client commands are intents: `move`, `chat`, `invite`, `invite.answer`, `trade`, `party`, `buy`, `use`, `heal`, `travel`, `surf`, `unstuck`, `save`, `ping`, `npc`, `battle`, `encounter`. See the dispatch implementation for exact payloads. The server derives damage, capture outcomes, ownership, money, positions and names. Clients do not write SQL or submit trusted final combat/trade states.

At 10 Hz by default, the world builds 8-tile spatial buckets and diffs nearby entities within the configured map-local interest radius. Per-recipient visibility is reset on map change. A client sees updates for nearby trainers/followers, not every player in every map. World chat intentionally crosses map/region boundaries. The renderer interpolates authoritative entity changes rather than trusting client teleports; movement sequences and step timing reject replay/speed abuse.

## Persistent schema 1

| Table | Purpose |
|---|---|
| `nxt_schema` | Migration version; protects against accidental downgrade |
| `accounts` | Stable account ID, unique case-insensitive login key, display username, scrypt hash, ban flag |
| `characters` | One versioned JSON aggregate per account with indexed numeric revision |
| `trade_audit` | Unique trade ID and exchange payload written with both resulting owner states |
| `world_leases` | Single world writer, heartbeat and fencing identity |

Pokemon are individually identified by immutable UUIDs inside the owner aggregate. A character contains location, party UUIDs, owned creature records, items and currency. The aggregate intentionally avoids separately saving party and inventory rows in inconsistent states; it is not a fully normalized per-Pokemon SQL design. JSON state is persisted in LONGTEXT on MySQL, with application-level validation and revisions. Independent analytical queries may require a later read model or migration.

MySQL tables use InnoDB. SQL values are bound parameters. A database/application username in setup is separately identifier-validated. Passwords are scrypt hashes with independent salts (N=131072, r=8, p=1), and hashing is performed outside the event loop with a two-operation semaphore. The server does not store cleartext account passwords or echo them to logs.

## Trade commit contract

Each exchange has a UUID, participants, offers, revision, lock set and confirmation set. Participants must be nearby and unoccupied before invitation acceptance. Applying an offer validates ownership/quantities, increments its revision and clears both participants' previous approval. Each final confirmation refers to the same revision and SHA-256 offer digest.

The final operation rechecks current ownership and capacity, calculates both new character aggregates, acquires their database rows in account-ID order, inserts one unique audit record, and updates both owner states in one transaction. In-memory ownership is replaced only after the store reports success. A replayed trade ID, stale revision, non-owner UUID, negative quantity, invalid digest or incomplete last-Pokemon state is rejected. Failure-injection and cancel-on-disconnect tests cover uncommitted exchanges. This is not a formal verification or claim of fault tolerance against every database failure.

Ordinary important state changes commit before success is acknowledged. Movement is marked dirty and saved periodically, on request, logout and orderly shutdown. Delayed autosave snapshots cannot overwrite a greater persisted revision. A crash can still lose movement since the last save; log/transaction semantics are not a rollback-free guarantee for every unfinished battle. Active battle and invitation/trade sessions are not restored after process restart.

A fresh world acquires the database writer lease. Heartbeats renew it every 10 seconds; stale takeover is allowed after 60 seconds. Mutating store operations check the current lease owner inside their transaction, preventing an old paused world from resuming ownership writes after takeover. This is single-world fencing, not multi-shard replication. The service stops when lease maintenance or critical periodic persistence fails.

## Extension contracts

Only trusted administrator-installed `.py` files in `Server/extensions` are loaded. Underscore-prefixed files are disabled. `register(world)` may attach short callbacks with `world.hook`. Current events are login, logout, move, battle_end and trade_complete. Hooks are not sandboxed and must not block, recursively take the world lock or invent client-authoritative state.

Future trainer bots should have a scheduled intent queue that goes through the same collision, combat and ownership services. Do not implement bots by granting public socket clients a trusted NPC flag. New persistent fields need an explicit migration and regression tests. Stable catalog/map/item keys must remain stable across releases, because existing accounts reference them.

## Scaling boundary

Area-of-interest diffs reduce ordinary replication, but do not establish capacity by themselves. One world lock and one store connection serialize significant work. Scrypt login work, dense scenes, autosave batches, JSON sizes, large collections and simultaneous trades need load measurements. The highest allowed configured cap is 1,000; deployment should begin far below it. Do not add a second process sharing the same DB or bypass the lease to increase capacity. Partitioning and durable cross-partition ownership would need a separate architecture update.

## 0.3.5 cosmetic variety identity

`Server/nxt/varieties.py` validates policy and migrates/serializes the creature's canonical `variety` plus derived legacy `shiny` flag. Wild identity is rolled after the authoritative encounter resolver, not in generic creature creation. Capture/PC/trade/evolution retain identity; `adventure.varietyDex` remains private. Public entity replication includes only `followerVariety` needed to render nearby native-icon sparkles. `Client/app/varieties.js` centralizes front-only art, names, event UUID identity and bounded deterministic effects. `Tools/publish_varieties.py` publishes the sidecar and checks hashes before the shared pack is computed. See `POKEMON_VARIETIES.md` for boundaries.
