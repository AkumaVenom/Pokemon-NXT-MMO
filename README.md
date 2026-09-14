# Pokemon NXT MMO

## Standard-user Windows build correction · 1.3.4

This source includes the correction for the two variety publisher tests that failed
with **`WinError 1314: A required privilege is not held by the client`**. The tests now
use isolated real copies of the small variety-front directory, not symbolic links
or hard links. Both checks remain active, including exact sprite checksums and
rejection of unsafe/cross-species asset paths. No administrator session, Developer
Mode, permission change, dependency downgrade or test bypass is required.

The gameplay version stays **0.3.5-alpha**, and the content pack remains
**`76fad1c40143e106528d0c53`**. Client/server gameplay, sprites, rarity, followers,
encounters, Cut and saved accounts are unchanged. The build banner is **1.3.4**.
See **`Docs/WINDOWS_BUILD_FIX_1.3.4.md`** for repair steps and validation limits.

## 0.3.5-alpha · Pokémon varieties and mirrored front sprites · Build tools 1.3.4

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

**Download all FOUR full-source ZIPs, Parts 1–4. Extract every part into the same destination so the identically named `Pokemon_NXT_MMO_v0.3.5-alpha_Source_PokemonVarieties` folders merge, then run `BUILD_ALL.bat`.** These are ordinary mergeable ZIPs, not byte-split volumes: do not concatenate them. All four parts are required and together contain the complete source and assets. No previous pack, original ROM, images.rar, Pillow, FFmpeg or audio renderer is needed for a normal build.

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
