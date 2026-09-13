# Native ROM music and sound-effect extraction

This optional developer tool reproduces the packaged music and sound effects from the two supplied local ROM revisions. Normal `BUILD_ALL.bat` uses the extracted OGG files already in the project. It requires neither a ROM nor this C++ toolchain to build or run the game.

## Audio implementation

The bundled agbplay engine reads the original MP2K/Sappy sequence commands, instrument banks, PCM and GameFreak differential PCM samples, square/wave/noise channels, envelopes, modulation, pan, pitch bends, and native reverb settings. The NXT adapter renders stereo audio at 44,100 Hz with windowed-sinc resampling. It measures peak level and only attenuates material that would exceed 0.95 full scale. Original note and instrument balance remains intact.

Looping songs contain their original introduction followed by two complete sequence cycles. The manifest identifies the warmed second cycle using PCM frame indices and seconds for Web Audio `loopStart` / `loopEnd`. One-shot effects retain their release tail. Song-table null slots and the explicit silence entry are documented separately. This is software synthesis with higher-quality resampling; it is not a claim of bit-exact GBA analogue output.

## Rebuild the optional renderer

Use an existing GCC 13+ compiler (or compatible C++23 compiler) and Python 3. All engine and fmt source dependencies are bundled. No network is used.

```text
python build_renderer.py --jobs 2
```

The compiler output is `nxt_audio_render` on Linux or `nxt_audio_render.exe` on Windows with a suitable GCC environment. This optional workflow was compiled and used on Linux. The normal Windows installer does not compile this tool.

## Re-extract from the supplied revisions

Install local `ffmpeg` and `ffprobe` executables, then run:

```text
python extract_music.py --kanto-rom "FireRed Rev 1.gba" --johto-rom "Ultra Shiny Gold Sigma 1.5.0.gba" --output extracted_audio --jobs 4
```

The script verifies the exact input SHA-256 values before reading version-specific offsets. It writes `songs/kanto/0001.ogg` and corresponding entries, plus `render_manifest.json`. It never modifies the input files. Temporary extraction copies and WAV intermediates are removed automatically. Unsupported commands, damaged pointers, silent nonempty tracks, duration caps, and encoding mismatches fail the extraction visibly. Both original source hashes remain in the manifest even when a documented recovery is needed.

For a native table inspection:

```text
nxt_audio_render "FireRed Rev 1.gba" scan
```

## Two documented recoveries in the supplied Sigma file

- One erased base-instrument sample at `0x4A3DA8` affects 16 songs/effects. All ten instrument descriptors referencing it match the corresponding FireRed descriptors at a `+0x60` relocation. The tool copies the exact surviving sample from supplied FireRed `0x4A3E08`, appends it to a temporary copy, and redirects those descriptors. It preserves the original source ROM and records source and sample hashes.
- Song 408's first 16 track-0 bytes were overwritten by the end of song 407's header. The surviving version of the same composition at Sigma song 320 supplies the existing 16-byte tempo/voice/volume/pan/wait prefix. All five accompanying track prefixes match, both loop destinations point to prefix offset 11, and the recovered six tracks have identical loop tick and sample boundaries. The tool relocates recovered track 0 and its 13 internal pattern/loop pointers, preserving every note in song 408 and leaving song 407 intact. The manifest explicitly labels this as a structurally validated same-ROM reconstruction.

No replacement notes or recordings are downloaded. Recovery bytes come solely from the supplied ROMs.

## Verification and licenses

The release extraction rendered all 818 nonempty song-table entries: 346 Kanto and 472 Johto. It produced 280 looping entries and 538 one-shot entries with no render errors, remaining caps, silent nonempty entries, or engine warnings. All 3,124 track entrypoints were checked. Each encoded file was inspected for 44.1 kHz stereo format and duration agreement within 2 ms. Windows playback remains a separate runtime check.

The engine is from [ipatix/agbplay](https://github.com/ipatix/agbplay), under GNU LGPL version 3. Complete corresponding source for the selected engine modules is bundled in `core/`, with the NXT modifications described and pinned by SHA-256 in `SOURCE_PROVENANCE.json`. `COPYING-GPL-3.txt` and `COPYING-LGPL-3.txt` contain the license texts. The optional adapter can be rebuilt and modified independently of the game. The fmt 10.2.1 dependency is under the MIT license in `vendor/fmt/LICENSE`.
