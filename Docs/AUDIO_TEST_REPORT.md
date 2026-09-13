# Audio release validation

Gameplay **0.2.0-alpha**, build tools **1.2.0**, incorporating world startup fix **1.1.2**. This report describes this audio update; older reports in this folder remain historical evidence for their named releases.

## Executed checks

| Check | Result |
| --- | --- |
| Python regression suite | 225 discovered: **224 passed**, one native-Windows-only bootstrap check skipped. Includes startup/lease cleanup, persistence, network sessions, server audio events, ROM decoding and release validation. |
| JavaScript audio engine | **29 passed**, including real catalog coverage, native move timing/repeats, cry modes, loop metadata, race cancellation, fanfare ducking, and bounded decoding/voice resources. |
| JavaScript app integration | **8 passed**, covering late map loads, authoritative Surf changes, logout/disconnection, modal sound access and durable preference requests. |
| Audio bundle verification | **2,366 clips** have matching SHA-256 values, valid container metadata and duration/loop bounds. All 859 map bindings, 876 normal/reverse species bindings and 708 regional move profiles resolve. |
| Native sequence rendering | **818 nonempty entries**: 346 FireRed and 472 Sigma; 280 loops and 538 one-shots. All 3,124 track entrypoints validated; no remaining renderer errors, warnings, duration caps or silent nonempty exports. |
| Native cry import | **1,548 WAVs** checked against decoded PCM hashes and sample counts. Twelve focused importer tests include differential-decoder nibble order, predictor reset, signed wrapping, truncated input, ROM fingerprint rejection and animation commands. |
| Encoded playback data | Every packaged OGG is decoded in full by FFmpeg; the count, failures and exact decoder version are recorded in `evidence/audio_full_decode.json`. This checks encoded data, not speakers or Windows device playback. |
| Existing content preservation | All **10,908 existing PNG files** are byte-identical, including 10,902 client PNG assets. The startup lifecycle is identical to accepted 1.1.2 except the version string; `Server/nxt/store.py` is byte-identical. |
| Matching content publication | Repack publishes pack **e05cb982d1fd4137629f86b0** to both client and server. The existing PNG digest algorithm is preserved; audio catalog metadata participates in the pack hash. Invalid audio blocks publication. |
| Build integration | Bundled OGG/WAVs, JavaScript modules, authoring sources and licenses are included by the source allowlist. Normal builds validate existing audio without loading a ROM or requiring the optional C++/FFmpeg authoring toolchain. |

The independent final size/hash audit of all 818 OGG exports is retained in `evidence/audio_extraction_verification.json`. The final archive also includes `SOURCE_SHA256SUMS.txt` for its source files. Logs for the Python and JavaScript checks are in `evidence/audio_1.2.0_*_tests.txt`; source preservation is in `evidence/audio_1.2.0_preservation.json`.

## Source recovery and interpretation

The supplied Sigma file contains damaged source data. The optional importer repairs only temporary extraction copies, using the supplied sources:

- A missing base-instrument sample affecting 16 entries is restored from its exact matching FireRed counterpart, including the native header and 1,682 PCM frames. All ten referring instrument descriptors match at the known relocation.
- Song 408 has an overwritten 16-byte track setup. The surviving same-ROM composition at song 320 supplies that setup. The importer preserves song 408's note stream, relocates its internal pointers, and verifies that all six tracks share identical loop boundaries. This is explicitly recorded as a structurally validated reconstruction.

The original ROM hashes, individual clip hashes, recovery evidence and sequence metadata are included in `Tools/audio_provenance/`. Input ROMs and temporary repair copies are excluded from the source delivery.

Sigma's original species lookup assigns 486 catalog entries to Bulbasaur's cry and five to Unown's cry. These original aliases are retained. Four unused damaged cry records are reported: normal 251/287 and reverse 119/287. No gameplay species references those unavailable records.

The move importer retains the selected native script path, explicit delays, repetitions and applicable cry modes. Original asynchronous graphics-task timing is adapted to this client's existing battle presentation; the game does not emulate the original GBA battle renderer. Original story scenes and unsupported game systems are not added merely by including their sound assets.

## Platform boundaries

These checks ran on Linux with Python 3.12, Node.js and the native C++/FFmpeg authoring tools. This environment has no Go compiler, PowerShell, installed Edge/Chromium executable, Windows audio device or live MySQL daemon. Consequently:

- The new Go preference-store tests and compiled headless launcher smoke checks were added but **not executed here**. The normal Windows build runs those checks on the build PC.
- The all-in-one BAT and automatic prerequisite downloads were checked through source and regression contracts, **not run in native Windows** for this release. No prebuilt EXE is supplied in this source archive.
- Native Edge decoding, focus behavior, device output and subjective listening quality still require runtime acceptance on the user's PC. Full-file FFmpeg decoding and simulated Web Audio tests do not establish audible Windows acceptance.
- SQLite transaction/network fixtures do not establish live MySQL acceptance. The previously accepted startup fix remains preserved; no database schema, existing save data or credentials were changed by this source edit.

For upgrade and local playback checks, follow `AUDIO_GUIDE.md`. A successful build writes its own current build log and `BUILD_INFO.json`.
