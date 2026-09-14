# 0.3.5 Pokémon varieties validation

> **Windows portability correction, 2026-09-14:** The original Linux checks below
> did not expose two unconditional test-fixture symlinks. The supplied Windows
> build log reached 523 tests but failed in those two fixtures with WinError 1314.
> Build tools **1.3.4** replace them with private real copies and keep the tests
> active. See `WINDOWS_BUILD_FIX_1.3.4.md` and its test report for the correction.
> The historical results below are not a claim that the original Windows build
> succeeded.

Release date: **2026-09-14**. Baseline: user-accepted **0.3.4-alpha Regional Encounters & Personal Cut** complete source. This report distinguishes source/runtime verification from native Windows deployment acceptance.

## Executed checks

| Check | Result |
|---|---|
| Complete Python suite, working source | **523 discovered: 522 passed; one native-Windows test skipped** |
| Same complete suite, clean build-selected source, latest published assets | **523 discovered: 522 passed; one skipped** |
| Combined JavaScript suite | **112 reported tests passed; zero failures** |
| New variety Python module | **29 tests passed** |
| New variety JavaScript module | **15 tests passed** |
| Exhaustive 10,000-ticket rarity selection | Exact 9,000/250/250/125/250/125 counts; one roll per result |
| Supplied Kanto/Johto fronts | **251 species × five varieties = 1,255 fronts present** |
| Complete imported art validation | **3,697 fronts/frames**, source/output hashes and visible RGBA pixel preservation passed |
| Original game artwork/audio | **11,110 PNGs + 818 OGGs + 1,548 WAVs byte-identical**; six original documentation PNGs also unchanged |
| Native maps, encounters and species facts | All **959 maps** and **877 species' non-variety facts** exactly equal to baseline; authoritative encounter policy and source sidecars unchanged |
| Two-account Chromium variety browser check | **PASS**, real DOM/canvas/WAAPI, actual service and temporary SQLite, zero page errors |
| Preserved two-account Cut browser check | **PASS**, both regions, owner/peer isolation and relogging |
| Go tests, Windows-target static checks and x64 cross-compilation | **Passed**, client GUI/server console PE headers verified |
| Actual Linux launcher HTTP smoke checks | **All 26 passed** |
| Full developer-mode build | **Succeeded**, clean snapshot, republish, regressions, launchers, archive verification and completed output publication |

The combined JavaScript count includes the existing audio engine script as a reported unit (it separately checks its internal assertions). The build invokes audio and general UI groups separately; the final subgroup's count alone is not the whole 112-test result. The single Python skip is the Windows-only PowerShell bootstrap helper on Linux.

## Identity, server authority and failure cases

Tests validate policy format, ordered identities, exact integer weights, all ticket boundaries, source-art hashes, full 251 coverage, native Shiny fallback and missing-art Normal tickets without probability redistribution. Invalid weights/paths/hash changes/unknown saved identities are rejected. Publisher and migration are idempotent. Generic creature generation and an account literally named “Wild” cannot bypass the intended wild-only variety roll.

The production encounter path chooses the authoritative map species and level first. Client-supplied species, level and variety fields cannot select an outcome. All six identities pass real capture/database save, PC transfer, relog, supported level/stone/trade evolution and owner-to-owner trade checks. Legacy Shiny state remains Shiny without rerolling, healing or altering selected moves. Canonical modern identity takes precedence over stale compatibility flags. Owned historical variety records are reconstructed privately; unsupported extra evolution art keeps the identity and displays the documented regular-front notice.

Failure-injection covers encounter start, capture, login migration and trading. Failed saves do not grant a capture, spend a ball, leak success, transfer ownership or change live/stored state. Existing regional Cut/badge/progression and character-specific collision regressions remain enabled. Every original source-manifest file remains present; original media are unchanged.

## Presentation and browser checks

Real shared helpers are loaded in the JavaScript fixtures rather than replacing variety logic with mocks. Tests cover collection filters/dex chips/evolution notes, five safe effect colours, native follower sheets, bounded four-star drawing, deterministic animation, canvas-state restoration, two-static-star reduced motion, old/public Shiny compatibility, and no effect for Normal.

Player-side sprites use front art and retain the horizontal mirror in steady state and every Web Animations keyframe. Opponents and popup/HP text are not mirrored. Attack translation still moves toward the opponent. UUID plus event-time variety handles same-species switching, residual damage and outgoing faint animations. Owner-side capture events identify the target, not a same-species party member.

`Tests/check_varieties_browser.py` registers two independent accounts against the actual aiohttp service with a temporary SQLite database. It stages known six-variety party prerequisites and deterministic wild/capture RNG for repeatable verification; it is not a claim of randomly encountering every variant in a campaign. The fixture exercises the real collection dropdown and front bytes, six battle identities, Normal-to-Ancient same-species switching, actual player attack/hit transforms (81 computed samples retain a negative determinant), peer follower identity/colours, native regular icon references, real item-menu Shadow capture, saved creature UUID and fresh-page relogging. The peer never acquires the owner's catch. No page errors occurred.

Chromium **144.0.7559.96** was used at **1440×1000** and **900×680**. Screenshots of the six-card collection, Normal/Shadow battles, coloured follower effects and compact battle were inspected for readable controls, correct identity and orientation, bounded sprites and no clipping. Imported artwork was not generated or recoloured; only source transparent padding was normalized.

The existing Cut browser fixture was rerun: both regions retain enabled/locked controls, real tree clicking, owner movement through the cleared tile, the other account remaining blocked, map/character isolation and fresh-page persistence.

## Environment and exact boundaries

Linux; Python **3.13.5**; Node **22.16.0**; Go **1.23.2 linux/amd64**; aiohttp **3.13.3**; cryptography **46.0.4**. The full build used `python Build/build.py --existing-environment --no-open`. Production dependency pins were **not installed or asserted**. PyMySQL is absent here; SQLite fixtures do not establish live MySQL/MariaDB acceptance. The ordinary Windows `BUILD_ALL.bat` workflow still manages its established pinned environment.

The container restricts native loopback browser navigation. Browser checks used the explicit `NXT_QA_BRIDGE=1` local DOM/asset/aiohttp-WebSocket transport bridge. This exercises shipped UI/rendering and actual server handling but is **not native browser WebSocket, Edge launcher, Windows input/audio hardware, public TLS or live MySQL acceptance**. Existing native socket/TLS Python and launcher HTTP checks are separate. Windows binaries were cross-compiled and inspected, not run on Windows.

Neither full cartridge story progression nor every tile/species in manual play, 1,000 concurrent clients, new special encounter systems, a live production database, a newly implemented evolution method or all-five art for every additional Sigma profile is claimed. Native acceptance should include two Windows PCs on the deployment's actual transport/database: fresh and migrated accounts, existing Shiny creatures, all six portraits, capture/save/restart, storage, trade, evolution, same-species battle switching, owner/peer follower effects, and the previously accepted encounter/Cut/audio/battle controls.

## Evidence and reproducibility

- `evidence/varieties_build.json`: successful clean developer build and exact environment/pack.
- `evidence/varieties_browser.json`: actual two-account variety browser result.
- `evidence/varieties_cut_regression.json`: preserved Cut browser result.
- `evidence/varieties_preservation.json`: exact baseline comparison and source-pixel verification.
- `POKEMON_VARIETY_ASSET_AUDIT.json`: exhaustive supplied/native/missing front coverage by stable species ID.
- `Server/data/varieties.json`: checked-in policy, aliases and source/output art hashes.

Published content pack: **`76fad1c40143e106528d0c53`**. The complete source release includes `SOURCE_SHA256SUMS.txt`. Four ordinary ZIPs contain disjoint subsets under one shared project folder; their combined entries reconstruct the complete source. The external `Pokemon_NXT_v0.3.5_Download_Verification.json` records the final ZIP hashes and verifies every source entry across all four. Build executables and generated dist/cache folders are not included in the source-only download.
