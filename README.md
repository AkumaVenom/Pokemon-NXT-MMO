# Pokemon NXT MMO

## 0.3.3-alpha · Battle screen correction · Build tools 1.3.3

This release corrects the battle entry regression: browser timers are invoked with their proper context, the battle dialog opens before effects start, and an effect failure restores usable battle controls. It preserves the previous sound cancellation and battle feedback. See `Docs/BATTLE_SCREEN_FIX.md` for validation and upgrade steps.

Battles show short attack lunges from either side, hit reactions, floating damage and effectiveness text beside the affected Pokémon. Feedback comes from accepted server battle events and does not change combat outcomes. Rapid turns retire old effects and sound tails; repeated snapshots do not replay them. Reduced-motion settings are respected. See `Docs/BATTLE_FEEDBACK.md` for behavior, validation and update instructions.

This update corrects level-up learning across all 876 published Pokémon profiles using the supplied FireRed and Sigma ROMs. It replaces the remaining 28 fallback Sigma lists, separates seven renamed Sigma move identities, clears invalid queued choices and adds an explicit Move Reminder. Your selected moves, ownership and server progress are preserved; no account reset is needed.

**Cyndaquil learns Ember at level 12 in both supplied ROMs.** Its summary now shows the complete native level-up list and next move. Open a Pokémon from **P → Party & storage**, then use **Move Reminder** to recover eligible current-species moves. Replacing a move requires your confirmation. See `Docs/LEARNSET_GUIDE.md`, `Docs/LEARNSET_ROM_AUDIT.md` and `Docs/LEARNSET_TEST_REPORT.md`.

**Download both full-source ZIPs, Part 1 and Part 2. Extract both into the same destination so their identically named project folders merge, then run `BUILD_ALL.bat`.** Both parts are required and together contain the entire updated source and all assets. No previous source pack, ROM, FFmpeg or separate audio renderer is needed.

### Play the adventure

Choose either region and any supported starter. Explore the native FireRed and Sigma maps, challenge nearby trainers and Gym Leaders, capture Pokémon, gain EXP and manage your team. Press **J** for the journal and badges, **G** for the Pokédex, **P** for the party, **B** for the bag and **M** for the atlas. Talk to **Nurse Joy inside a Pokémon Center** to restore HP, status and PP; Center services also provide PC storage. Healing from the old menu is removed.

The pack includes **959 maps** (425 FireRed + 534 Sigma), **876 catalog entries**, **1,294 native trainer associations**, **16 Gym Leaders**, **317 species with supported evolution rules** and **876 audited native learnsets** (874 intact and two independently bounded native-prefix recoveries). These are content counts, including forms, shared rooms and placeholders; they do not imply complete original story campaigns. All **2,366 existing audio clips** are retained, with native music bindings extended to recovered rooms.

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
