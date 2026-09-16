# Kanto / FireRed NPC dialogue restoration — executed test report

Release: **0.6.7-alpha · Kanto FireRed NPC Dialogue Restoration**

## Reviewed ROM input

- Source: **Pokémon FireRed Version (USA, Europe) Rev 1**
- Size: **16,777,216 bytes**
- SHA-256: **729041b940afe031302d630fdbe57c0c145f3f7b6d9b8eca5e98678d0ca4d059**
- The ROM is a development/extraction input only. It is not included in the source release and is not required for a normal build.

## Static extraction audit

`Tools/extract_firered_dialogue.py` uses the existing bounded FireRed-family event-script/text decoder. It validates the exact reviewed ROM before reading offsets and does not execute ROM code, `special` handlers, native functions or arbitrary event logic.

Executed extraction result:

- FireRed maps audited: **425**
- Visible object events audited: **1,620**
- Ordinary person-NPC objects eligible for literal extraction: **669**
- Validated published Kanto dialogue bindings: **642**
- Eligible objects without a readable script pointer: **25**
- Eligible objects without a safely validated literal: **2**
- Non-regular item/Pokémon/field actors excluded: **498**
- Resolved trainer bindings excluded: **413**
- Additional trainer-type objects excluded: **40**
- Kanto Pokémon Center nurse bindings: **20 / 20**
- Published Poké Mart clerk bindings using the existing clerk graphic: **21**

The regular-NPC publication boundary is deliberately restricted to FireRed object graphics **0 through 91**. This prevents item balls, Pokémon actors, field effects and other non-person objects from being mislabeled as ordinary NPC speech. For example, the audited `kanto_10_11:2` object uses graphic 92 and contains an item/event result (`PLAYER obtained an EEVEE!`); it is correctly excluded from NPC dialogue publication.

A second extraction to a separate output file was compared byte-for-byte with `Server/data/kanto_dialogue.json` and produced an **identical result**.

## Runtime/content publication

The regional dialogue publisher now merges the reviewed FireRed and preserved Sigma sidecars into one versioned runtime structure:

- `npcDialogue.format`: **2**
- Kanto entries: **642**
- Johto/Sigma entries preserved: **2,158**
- Combined entries: **2,800**
- Server/client gameplay version: **0.6.7-alpha**
- Republished native content pack: **69a67b1c4f5b9dd46bad4f82**
- Republish inventory: **959 maps, 877 catalog entries, 14,807 PNG assets, 2,366 verified audio clips**

Ordinary Kanto NPC clicks now resolve their FireRed text using stable map/object identity. Dynamic owner placeholders are rendered from authoritative player context. Trainers and Gym Leaders are excluded and keep NXT's existing team/species/level preview and Battle action. Nurse Joy and Poké Mart clerks retain their existing service actions while using their reviewed FireRed greeting when a safe literal exists.

The accepted v0.6.6 Johto/Sigma dialogue, Pokémon Center return-context fix and Goldenrod Department Store elevator fix remain in place. The v0.6.5 Route 36 Sudowoodo story gate and v0.6.4 autonomous performance/evolution architecture are unchanged.

## Executed regression validation

### Python focused release/regression suite

Command scope covered Kanto dialogue, preserved Johto dialogue, build/source contracts, release-version alignment, interior portals, Route 36 Sudowoodo, autonomous performance, autonomous evolution/world life and Pokémon Centers.

**105 / 105 tests passed.**

### JavaScript client/renderer suite

The non-browser Node suites for adventure UI, audio integration/engine, battle FX, learnsets, registration, renderer replication and varieties completed:

**116 / 116 tests passed.**

`Tests/check_battle_browser.mjs` was also attempted, but this Linux execution environment does not have the optional `playwright` package installed, so that browser fixture could not start. The failure was `ERR_MODULE_NOT_FOUND: playwright`; it was not counted as a pass and was not treated as a gameplay regression.

### Launcher tests

- Client launcher Go package: **passed**
- World/server launcher Go package: **passed**

### Syntax and deterministic-source checks

- `python -m compileall -q Server Tools Tests Build`: **passed**
- FireRed dialogue second extraction versus shipped sidecar: **byte-for-byte identical**
- FireRed source SHA-256/size versus reviewed extraction manifest: **matched**

### Full historical Python discovery note

A complete `python -m unittest discover -s Tests -v` run was attempted separately. The execution session stopped it at its **300-second environment timeout** while tests were still progressing; all tests visible as completed before the cutoff were reporting `ok`, but there was no final unittest summary. This report therefore does **not** claim the complete historical discovery suite passed; the explicit completed suites above are the release validation basis.

## Packaging acceptance

The clean source snapshot contains **18,506 allowlisted source/content files**. The four mergeable source ZIPs are required to reproduce that snapshot exactly. Packaging acceptance checks:

- each ZIP passes CRC/integrity validation;
- extracting all four ZIPs into one fresh directory produces **18,506 files**;
- every extracted file matches the clean package source byte-for-byte by SHA-256;
- no extra file is introduced by the four-part merge;
- no ROM, database, runtime configuration, credential/private-key, build cache, log, executable or nested ZIP is included;
- the packaged Kanto/Johto dialogue, interior portal, Route 36, autonomous-performance and build/version smoke tests are rerun from the fresh merged extraction.

These checks are part of the release packaging procedure and must all pass before the four ZIPs are distributed.
