# POKEMON NXT MMO
## 0.1.0-alpha · First networked exploration build

> **MySQL setup hotfix 1.1.0:** `Server/2 - Configure MySQL.cmd` now opens editable password fields with masking and a Show passwords option. It asks for the **existing MySQL administrator password**, not a new root password. Leave both NXT application password fields blank for automatic generation/reuse. See `Server/MYSQL_SETUP_FIX.md`. The fix does not change gameplay, protocol, database schema, root credentials or other games.

> **Automatic source build 1.1.1:** extract the full ZIP and double-click **`BUILD_ALL.bat`**. It downloads/installs missing **Go and full Python x64**, then installs isolated Python dependencies, tests, compiles and packages the game. No manual Go/Python installation is required on a normal Windows 10/11 x64 build PC. Internet is needed for missing downloads. Build tools 1.1.1 correct the PowerShell reserved-variable error during Go discovery and validation. Read **`START_HERE_BUILD.md`**. This source ZIP contains no prebuilt game EXEs; successful outputs appear under `dist/build-<timestamp>`. Gameplay remains v0.1.0-alpha; the MySQL setup 1.1.0 fix is preserved.

A new, independent client/server game for Akuma. Extracted Kanto and Johto/Sigma maps and sprites run in a native Windows app window backed by an authoritative dedicated world service. **No ROM or emulator is required to play.** This is not the existing Pokemon Vortex browser project and does not use its database.

**Start with `Docs/QUICK_START.md`.** The complete folder must be extracted before launching. The first-time server install needs an internet connection for Python dependencies; client gameplay does not download assets or access a CDN.

### What you can test now

Create an account, select Kanto or Johto and one of six starters, explore the extracted maps, encounter and capture Pokemon, gain experience, manage your party and collection, buy supplies, battle practice trainers, and challenge another connected player to a friendly duel. Usernames follow trainers as nameplates; lead-party followers and nearby movement are synchronized. General and Trade chat reach the whole world. Clicking another player opens challenge and trade actions. Exchanges support Pokemon, items and money with two-sided locking, exact-offer confirmation and an atomic ownership commit.

This build includes **859 extracted map layouts** (425 FireRed + 434 Sigma), **852 maps with a validated walkable entry tile**, and **876 catalog entries**, including forms/custom entries. These counts describe imported content, not complete original campaigns or 876 distinct official species. Seven non-walkable placeholders cannot be entered.

### Windows applications

`Client/Pokemon NXT MMO.exe` is a compiled Windows x64 launcher. It serves only the local client assets over loopback and opens **Microsoft Edge in app-window mode**, without ordinary browser tabs or address bar. The app is built with HTML/CSS/Canvas/JavaScript, not Unreal, Unity or an emulator. Edge must be installed; it is not bundled. The client does not need Python, Node.js, MySQL credentials or a ROM.

`Server/Pokemon NXT World Server.exe` is a compiled Windows x64 console launcher. It starts the Python world service from its local virtual environment and retains the administrator's CMD console. It is **not a self-contained bundled Python runtime**. Install server dependencies and configure MySQL first.

Both executables were cross-compiled and inspected as Windows PE x64 files. **They have not been executed on Windows in this build environment.** The service, real WebSocket transport, gameplay contracts and client UI were tested on Linux; see the exact coverage in `Docs/TEST_REPORT.md`.

### Folder separation

```text
Pokemon_NXT_MMO_0.1.0-alpha/
  Client/                         Player distribution; no database credentials
    Pokemon NXT MMO.exe
    config.ini                    Join IP/hostname, port, TLS and display settings
    app/                          UI, renderer and extracted PNG/JSON assets
    launcher/                     Complete Go launcher source
  Server/                         Private administrator distribution
    Pokemon NXT World Server.exe
    config.ini                    Listen address, DB, security and world settings
    1 - Install Server Dependencies.cmd
    2 - Configure MySQL.cmd
    3 - Start World Server.cmd
    Start Developer SQLite World.cmd
    server.py, nxt/, data/, extensions/, launcher/
  Tools/                          Extraction and ROM-free content publishing
  Tests/                          Regression and real-network integration tests
  Docs/                           Setup, scope, architecture, security and asset audit
```

**Give players only the Client folder. Never give them your configured Server folder, database password, TLS private key, logs or database backup.** Separate player-only and administrator packages are also supplied.

### Essential scope notes

This is a playable **networking/exploration alpha**, not a finished FireRed-equivalent MMORPG. Original story scripts, progression gates, gym/badge campaign, quests, audio/music, tile animations, full move effects, abilities, evolution, breeding and autonomous trainer bots are not implemented. Static NPCs have alpha interactions and eligible trainers have simplified practice battles; original trainer teams and story logic are not recreated.

The current followers use **two-frame extracted party icons**, not a verified complete set of directional overworld Pokemon animations. The hard account admission cap is **1,000**, but **1,000 real concurrent connections have not been load-tested**. Do not advertise this alpha as a proven 1,000-player production service.

MySQL is the default persistence backend and has implemented InnoDB transactions, character revisions and a world-writer lease. No MySQL daemon was available for this build's runtime tests. SQLite tests exercise the shared persistence contract, not a substitute claim that MySQL was verified. A separately named, explicitly selected SQLite developer mode exists for quick local testing; a MySQL failure never silently switches to it.

### Documentation

`Docs/QUICK_START.md` — local MySQL, two-PC LAN, controls, troubleshooting and admin commands.  
`Docs/ALPHA_SCOPE.md` — what is playable and what is still missing.  
`Docs/ARCHITECTURE.md` — protocol, authority, ownership, database and scaling boundaries.  
`Docs/MODDING.md` — add or edit native assets/content without any ROM.  
`Docs/NETWORK_AND_SECURITY.md` — LAN/TLS separation, accounts, backups and deployment checklist.  
`Docs/TEST_REPORT.md` — executed checks and unverified platforms.  
`Docs/ASSET_SOURCES.md` and `Docs/ASSET_REPORT.json` — exact sources and extraction audit.

The supplied ROMs are not distributed in these packages. Extracted Pokemon/Nintendo/Game Freak and ROM-hack artwork remains third-party material. This delivery does not grant public redistribution, commercial-use or trademark permissions.
