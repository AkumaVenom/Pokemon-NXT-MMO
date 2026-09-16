# Pokemon NXT MMO

### Route 36 Sudowoodo story gate — personal collision, SquirtBottle and persistent battle clear

The **0.6.5-alpha Route 36 Sudowoodo Story** update turns the existing odd-tree sprite on Johto Route 36 into an authoritative per-character story obstacle. Before it is cleared, the exact authored tile is solid even though the shared ROM collision tile is passable. Defeating Whitney grants the saved **SquirtBottle** Key Item; clicking the odd tree and choosing **Use SquirtBottle** starts the authored **Lv. 20 Sudowoodo** encounter. Defeating or capturing Sudowoodo saves the event as cleared and removes that tree/collision only for that character. Running, losing, disconnecting before a successful save, or another player's completion cannot open your path.

This update is additive to the accepted **0.6.4-alpha Autonomous Trainer Performance Hardening** baseline. The 2,000-bot population, in-memory authority, batched persistence, ranked/off-screen simulation, captures, travel and bot evolution remain unchanged. The movement hot path evaluates environmental blockers in one bounded object pass so the new story collision does not reintroduce whole-object-list scan amplification for human or autonomous movement. See `Docs/ROUTE36_SUDOWOODO.md` and `Docs/ROUTE36_SUDOWOODO_TEST_REPORT.md` for the progression, security/persistence contract and executed validation.

## 0.6.5-alpha · Route 36 Sudowoodo Story · Build tools 1.4.1

**Preserved Windows/build and performance corrections:** the ordinary-user Windows source builder still closes temporary SQLite probe connections correctly, retains CRLF launcher contracts and schema-3 lease protection. The accepted 0.6.4 autonomous-performance architecture remains intact; this release adds no SQL schema bump and requires no bot or player reset.

Type commands in the **world-server terminal on the host PC**, never in player chat. The console provides **81 canonical commands and 21 aliases** selected/adapted from the supplied proposal for NXT's existing systems. It is not an RCON service, HTTP admin panel or client permission rank. The operating-system account controlling the server process is trusted; Windows elevation is not required.

Use `help`, `who`, `help givepokemon`, `team TrainerName` and `species Pikachu` to begin. Manage Pokémon (all six varieties), inventory, currency, safe locations, account restrictions, saves and maintenance. Readouts and edits accept exact usernames or `#accountID`; Pokémon edits accept exact owned UUIDs or `party:1` through `party:6`. Destructive edits require short-lived single-use confirmations bound to unchanged state and session identity. Writes and their successful administrative audits commit together before clients see them. Developer/test commands are disabled by default; isolated test duels cannot award gym wins, money, captures or experience.

**Chat commands are intentionally excluded**, including announce, broadcast, mute and whisper. Unsupported gameplay systems are not exposed as pretend commands. See **`Docs/LOCAL_ADMIN_CONSOLE.md`** for the complete command reference, configuration, safety model, examples, upgrade and rollback instructions; **`Docs/LOCAL_ADMIN_PROPOSAL_AUDIT.md`** maps every proposal row to its implementation or explicit exclusion. Current executed checks are recorded in **`Docs/LOCAL_ADMIN_TEST_REPORT.md`**.

**Upgrade:** back up the database and configured deployment, stop the old server, then deploy matching rebuilt Client and Server. Schema 3 remains authoritative; this update adds no new SQL schema version. The preserved 0.6.4 performance migration keeps its idempotent activity index, and 0.6.5 adds only character-save story/key-item fields. Existing Plain Badge owners receive the SquirtBottle additively when their save is validated; accounts without the badge are unchanged until they defeat Whitney. Existing accounts, autonomous identities, bot Pokémon, ratings, rivalries and activity history are preserved. Preserve your configurations and certificates; do not rerun MySQL setup for this update.

The accepted **1.3.4 standard-user Windows build correction is preserved**: the variety publisher tests use isolated real sprite copies, not privileged links. No Developer Mode, elevated console, dependency downgrade or skipped variety checks is needed. Its historical repair guide is `Docs/WINDOWS_BUILD_FIX_1.3.4.md`.

## Preserved 0.3.5 Pokémon varieties and mirrored front sprites

Ancient, Metallic, Shiny, Mystic and Shadow are now persistent cosmetic Pokémon identities. All **251 Kanto/Johto species** have all five supplied variety fronts. The import also binds matching supplied fronts for supported later-generation/Sigma profiles: **3,697 additional fronts** in total, with an exhaustive coverage/provenance audit. Unsupported extra forms are not given invented recolours.

**Every player-side battle Pokémon now uses its horizontally flipped front sprite, including Normal.** The opponent uses its unflipped front. Attack, damage, faint and switch effects retain that orientation, including switches between two varieties of the same species. Back sprites remain in the original asset library for preservation, but are not used for battle presentation.

Normal wild rolls are **90%**; Ancient, Metallic and Mystic are **2.5% each**; Shiny and Shadow are **1.25% each**. These are NXT-specific Vortex-inspired cosmetic rates, not a claim about Vortex's exact numeric odds. The authoritative regional encounter resolver still chooses the species and level first. Variety does not change stats, moves, capture difficulty, map habitats or gym progression.

Variety survives captures, relogging, PC transfers, trades and supported evolutions. Existing Shiny Pokémon are migrated without rerolling, healing or resetting their progress. Followers retain the existing regular icon sheets and gain a bounded, animated colour-coded sparkle effect visible to nearby players. Collection filters, full names, summaries, trade screens, battle portraits and owner-only Pokédex variety records use the same identity.

Read **`Docs/POKEMON_VARIETIES.md`** for exact rates, upgrade steps and supported scope, **`Docs/POKEMON_VARIETIES_TEST_REPORT.md`** for executed checks, and **`Docs/POKEMON_VARIETY_ASSET_AUDIT.json`** for per-profile coverage.

### Preserved 0.3.4 regional encounters and personal Cut

This release replaces starter-area fallback spawns with explicit FireRed/Crystal location and floor tables, including Crystal morning/day/night pools and separate Surf selection. Every one of the 959 maps has an audited encounter decision; 248 contain pools, and places without a verified normal encounter table do not invent one.

**Cut unlocks automatically after Misty in Kanto or Bugsy in Johto, independently per region.** Click a small HM tree to open its enabled/locked Cut button. Cutting durably removes that tree's sprite and collision only for your character; other trainers must cut their own. All 120 HM trees use this behavior. Existing qualifying badges are recognized on login and no combat move slot is overwritten.

See **`Docs/REGIONAL_ENCOUNTERS_AND_CUT.md`** for upgrade instructions, exact rules, the Nidoran♂ identity repair and the existing Sigma-layout/special-encounter limits; see **`Docs/REGIONAL_ENCOUNTERS_CUT_TEST_REPORT.md`** for executed checks. The exhaustive map/tree audit is `Docs/ENCOUNTER_CUT_AUDIT.json`.

### Preserved battle and learning fixes

The preserved 0.3.3 fix corrects the battle entry regression: browser timers are invoked with their proper context, the battle dialog opens before effects start, and an effect failure restores usable battle controls. It preserves the previous sound cancellation and battle feedback. See `Docs/BATTLE_SCREEN_FIX.md` for validation and upgrade steps.

Battles show short attack lunges from either side, hit reactions, floating damage and effectiveness text beside the affected Pokémon. Feedback comes from accepted server battle events and does not change combat outcomes. Rapid turns retire old effects and sound tails; repeated snapshots do not replay them. Reduced-motion settings are respected. See `Docs/BATTLE_FEEDBACK.md` for behavior, validation and update instructions.

The previous update corrected level-up learning across all 876 then-published Pokémon profiles using the supplied FireRed and Sigma ROMs. It replaces the remaining 28 fallback Sigma lists, separates seven renamed Sigma move identities, clears invalid queued choices and adds an explicit Move Reminder. Your selected moves, ownership and server progress are preserved; no account reset is needed.

**Cyndaquil learns Ember at level 12 in both supplied ROMs.** Its summary now shows the complete native level-up list and next move. Open a Pokémon from **P → Party & storage**, then use **Move Reminder** to recover eligible current-species moves. Replacing a move requires your confirmation. See `Docs/LEARNSET_GUIDE.md`, `Docs/LEARNSET_ROM_AUDIT.md` and `Docs/LEARNSET_TEST_REPORT.md`.

**Download all FOUR full-source ZIPs, Parts 1–4. Extract every part into the same destination so the identically named `Pokemon_NXT_MMO_v0.6.5-alpha_Source_Route36SudowoodoStory` folders merge, then run `BUILD_ALL.bat`.** These are ordinary mergeable ZIPs, not byte-split volumes: do not concatenate them. All four parts are required and together contain the complete source and assets. No previous pack, original ROM, images.rar, Pillow, FFmpeg or audio renderer is needed for a normal build.

### Play the adventure

Choose either region and any supported starter. Explore the native FireRed and Sigma maps, challenge nearby trainers and Gym Leaders, capture Pokémon, gain EXP and manage your team. Press **J** for the journal and badges, **G** for the Pokédex, **P** for the party, **B** for the bag and **M** for the atlas. Talk to **Nurse Joy inside a Pokémon Center** to restore HP, status and PP; Center services also provide PC storage. Healing from the old menu is removed.

The pack includes **959 maps** (425 FireRed + 534 Sigma), **877 catalog entries**, **1,294 native trainer associations**, **16 Gym Leaders**, **318 species with supported evolution rules** and **877 audited native learnsets** (875 intact and two independently bounded native-prefix recoveries). These are content counts, including forms, shared rooms and placeholders; they do not imply complete original story campaigns. All **2,366 existing audio clips** are retained, with native music bindings extended to recovered rooms.

Interior traversal recognizes actual doorway and transition behaviors. It no longer activates dummy pavement warps such as the event in front of Leaf’s Johto house. One hundred referenced Sigma rooms were recovered, including its upstairs and Chuck’s gym. Center entry/exit routes and each nurse’s counter access are tested. Read the exact recovery and exception audit in `Docs/INTERIOR_ACCESS_AUDIT.md`.

See **`Docs/ADVENTURE_GUIDE.md`** for play and upgrade instructions, **`Docs/ADVENTURE_TEST_REPORT.md`** for executed validation, and **`Docs/ALPHA_SCOPE.md`** for remaining mechanics limits.

### Keep your working server

Build into a fresh folder and deploy its matching Client and Server together. Back up the existing database and configured server first; preserve its `config.ini`, database, certificates and private deployment files. Preserve the client’s working connection settings. Do not replace these with clean release templates or rerun MySQL setup merely to upgrade. Existing characters receive additive state and validated move-queue migration when they next log in; no account reset or character-specific repair is needed.

For badge-gated play, set these existing Server/config.ini `[world]` settings to `false`:

```ini
allow_alpha_atlas = false
allow_alpha_surf = false
```

Fresh builds already use those settings. Older configurations may still enable unrestricted administrator exploration. With the defaults, the atlas remains readable; travel unlocks after two badges and is limited to discovered outdoor locations and home hubs. Interiors are entered through their doors. Surf unlocks separately through Kanto’s fifth and Johto’s fourth badges. Important gameplay mutations save before success; movement checkpoints follow your configured interval.

### Build and host

`BUILD_ALL.bat` finds or installs full Python and Go on Windows x64, installs isolated pinned dependencies, validates the complete content, runs tests and builds separate Client and Server packages. Outputs appear in `dist/build-<timestamp>`. The accepted PowerShell HOME correction, startup recovery/logging 1.1.2, online TLS setup 1.2.2 and replication/persistence fixes 1.2.3 remain included.

Follow `Docs/QUICK_START.md` for first-time MySQL setup and `Docs/ONLINE_HOSTING.md` for hosting. `Server/2b - Configure Online Hosting.cmd` creates or imports a certificate for the public address and exports a public client connection kit. Existing working hosting settings do not need regeneration for this update.

The Go client launcher serves bundled assets on loopback and opens Microsoft Edge in an app window. It does not need Python, a ROM or MySQL credentials. The world launcher starts the Python service using its server environment. Give players **only the Client distribution**, never the configured Server directory or its private keys.

### Scope and provenance

This is an independent MMO alpha using ROM-derived art, maps, music and supported gameplay data. It does not execute the original ROM story scripts or reproduce every puzzle, ability, held-item effect, move effect, evolution condition, breeding system or battle animation. Gym access adjustments and journal/stock/travel rules are documented MMO adaptations. Some malformed Sigma data remains explicitly unsupported; source placeholders are not fabricated into unrelated rooms.

The original ROM files are not included. Regional art remains sourced from the respective supplied ROM; no generated replacement artwork is used. Detailed provenance is in `Docs/ASSET_SOURCES.md`, `Docs/ADVENTURE_ROM_DATA.md` and `Docs/CENTER_ASSET_AUDIT.md`. The project’s existing third-party notices remain applicable.

Native Windows/Edge and a live MySQL deployment require their own acceptance checks. The release test report distinguishes executed checks from those platform limits.
