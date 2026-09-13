# ROM audio guide · 0.2.0-alpha

This release adds the supplied FireRed and Ultra Shiny Gold Sigma sound banks to the existing networked game. The audio files are included in the source and client package. Playing or running the normal all-in-one build does not require either ROM, an emulator, FFmpeg or a separate audio renderer.

## Sound controls

Click **Sound settings** on the login screen or **Sound** in the game header. The mixer remains available during a battle. Edge starts sound after a click or key press; use **Enable sound** if the mixer says it is waiting for an interaction.

| Control | Default | Effect |
| --- | --- | --- |
| Master volume | 80% | Controls the whole mix. |
| Music | 65% | Controls title, area, surfing and battle music. |
| Sound effects | 80% | Controls action effects, interface sounds and event jingles. |
| Pokemon cries | 85% | Controls species voices. |
| Mute all sound | Off | Silences all channels. |
| Mute while the game is unfocused | On | Silences the mix while another window is active or the game is hidden. |
| Low HP warning | On | Enables the repeating warning for the active Pokemon at 20% HP or less. |
| Chat notifications | On | Enables a cue for incoming live chat; loading chat history stays quiet. |

Changes take effect immediately. The launcher saves the mix for the current Windows user in `%APPDATA%\PokemonNXT\audio_settings.json`, so it survives closing the game and launching a new client build. These are PC preferences, not account settings synchronized by the world server. If saving fails, the mixer says that the settings apply only to the current session.

## What plays in the game

The title and region selection use the appropriate source bank. Area music follows each imported map's original music ID. Surfing, battles and battle results select their own music; returning to exploration restores the area's music. Crossfades and the extracted loop boundaries retain a track's introduction before repeating its loop.

Battles have send-out and species cries, move effects, hit effectiveness, status/stat changes, fainting, capture, experience, level-up and result cues. The original move scripts supply explicit delays, repeats, stereo positions and applicable voice callbacks. The client avoids replaying effects when the same battle state arrives again.

Exploration and interface cues include blocked movement, ledges, travel/warps, dialogs, menus, party changes, healing, shopping, item use, saving, completed trades and invitations. Persistent success cues come from the world server after the corresponding action commits. Clicking a button can make a local interface sound; a rejected purchase or failed save does not play its success cue.

## Extracted coverage

| Source data | Coverage |
| --- | --- |
| FireRed sound table | 346 nonempty music/effect entries. |
| Sigma sound table | 472 nonempty music/effect entries, including its expanded song IDs. |
| Map music | All 859 imported map headers: 849 explicit songs, 6 silence values and 4 inherit values. |
| Move sound scripts | Move IDs 1–354 from each ROM, with a primary presentation path and separately recorded reachable alternatives. |
| Cry files | 774 available native samples, supplied in normal and reversed forms: 1,548 lossless WAV files. |
| Species voices | Original normal/reverse cry bindings for all 876 catalog entries. |

All **818 nonempty music/effect entries** were rendered: **280 looping entries and 538 one-shot entries**. The extraction checked all 3,124 sequence-track entrypoints, and every encoded entry has 44.1 kHz stereo audio with duration matching its rendered PCM within 2 ms. This establishes file/render coverage; native Windows listening remains a separate acceptance check. The per-entry results, hashes and original source hashes are recorded in `Tools/audio_provenance/render_manifest.json`.

The complete nonempty song bank includes tracks for original scenes and systems that this alpha has not implemented. Retaining a track in the asset catalog does not make the corresponding story scene, evolution system or battle mechanic playable. Unused/null song slots are not fabricated into tracks.

Music and effects are rendered with the upstream **agbplay** MP2K engine using the ROM's instruments, PCM/PSG channels and Game Freak compressed samples. The delivery uses 44.1 kHz stereo Ogg Vorbis, quality 5, with explicit loop points. Cries remain lossless 16-bit mono PCM at their native 10,512 Hz rate. These are native instrument renders, rather than General MIDI instrument replacements.

### Sigma source limitations

The supplied Sigma ROM's actual species-to-cry lookup assigns **486 of its 491 catalog entries to cry 0 (Bulbasaur)** and **5 form entries to cry 200 (Unown)**. This release preserves that lookup. Those shared voices are present in the source ROM; they are not missing downloads or evidence that the volume mixer has failed. Distinct voices for every expanded species would require a separate, explicitly authored cry remap and additional suitable source material.

Four unused Sigma cry entries contain invalid sample data: **normal cries 251 and 287**, and **reverse cries 119 and 287**. They are recorded as unavailable rather than replaced with invented audio. The normal and reverse tables have different damaged entries; none of the 876 gameplay species bindings points to them.

Two repairs were needed to render damaged Sigma audio. Both operate on temporary extraction copies and leave the supplied input ROM files unchanged:

- An erased instrument sample at Sigma offset `0x4A3DA8` affected 16 songs/effects. All ten referring voice descriptors match their FireRed counterparts at a `+0x60` relocation, including type, key and envelope settings. The extractor restores the exact 1,698-byte sample block—16 header bytes and 1,682 sample bytes—from the supplied FireRed offset `0x4A3E08`, then redirects the matching descriptors in the temporary copy.
- Song **408 (Goldenrod City)** had its first 16 track-0 setup bytes overwritten by the preceding song 407's header. The intact version of the same composition at Sigma song **320** provides that setup prefix; all five accompanying track prefixes match. The extractor restores those existing 16 bytes, relocates song 408's surviving track stream and adjusts its 13 internal pointers, preserving the remaining note data and song 407. All six recovered tracks agree on loop boundaries at ticks **48 → 3120 → 6192**, at tempo **132 BPM**. This is recorded as a structurally validated reconstruction from the same ROM.

The exact affected IDs, offsets, replacement hashes and supporting evidence are in `Tools/audio_provenance/render_manifest.json`, under `sample_recoveries` and `sequence_recoveries`. `Tools/native_audio/README.md` explains the optional reproducible extraction workflow, and `Tools/native_audio/SOURCE_PROVENANCE.json` identifies the renderer source and modifications. No replacement notes or recordings were downloaded. Use `AUDIO_TEST_REPORT.md` for the release's final validation results.

### Presentation limits

The client plays the original move script's selected primary path. It does not play every mutually exclusive branch at once. Explicit script delays are retained, but waits for asynchronous visual tasks are approximated because this alpha does not emulate the GBA battle-animation renderer. Multi-turn, conditional and unsupported move mechanics retain the alpha combat engine's existing limits.

Extracting all available sound data does not turn the exploration alpha into a finished original-campaign remake. Original story scripts, complete battle visuals and other missing systems remain listed in `ALPHA_SCOPE.md`. `AUDIO_TEST_REPORT.md` distinguishes automated checks from listening, native Windows/Edge and live MySQL acceptance.

## Upgrade an existing working 1.1.2 installation

1. Extract this entire source ZIP into a **new folder** and run `BUILD_ALL.bat`. Extract both source parts into the same destination. Its banner must show build tools **1.2.1**. Use the new successful output named by `dist/LATEST_BUILD.txt`.
2. Stop the current world normally and back up its configured Server folder and database using your usual backup process. Keep the old release available for rollback.
3. Deploy the newly built Server program files and data as one matching set. Carry forward the existing server `config.ini`, certificates and any deployment-specific extension configuration you actually use. Keep the existing world database. Do not replace your working configuration with the fresh release template or run MySQL setup merely to add sound.
4. Deploy the complete matching Client folder, including `app/assets/audio`, and carry forward its existing connection settings. Players need this complete new client pack; the old client does not contain the mixer or audio catalog.
5. Start the new world and client, sign in, click to enable sound, and check both regions. Your existing account/save data remains in the configured database. If dependencies are needed on a different server PC, use the supplied server dependency installer.

World startup fix **1.1.2**, MySQL setup correction **1.1.0** and the PowerShell `$HOME` correction are incorporated. The old scripts-only `Pokemon_NXT_MMO_World_Startup_Fix_1.1.2` package is not an updater for this audio release; do not apply it over the newer audio server scripts.

## If something is silent

- Click **Sound**, then **Enable sound** if offered. Check Master and the relevant channel, Windows volume, and **Mute all sound**.
- Keep the game focused while testing, or turn off **Mute while the game is unfocused**. Its default is enabled.
- Use a known outdoor map for a music test. Six native map headers explicitly request silence, and four inherit the previous area's music.
- Check that the whole Client folder was copied, including `app/assets/audio`. Do not mix an older client with the new server/content pack. Restore missing or altered audio files from the complete source/build output.
- If the mix works until you close the launcher, check the preference-saving message in Sound settings and the current user's ability to write its application settings folder.
- A shared Sigma cry is expected for the bindings described above. It is unrelated to world-server startup or database ownership.

For an optional source-file integrity check, run `python Tools/verify_audio.py` from the source folder with a compatible Python runtime. The normal build runs the same validation automatically; neither path needs the ROMs.

## Optional: regenerate the audio from the supplied ROMs

This is an authoring workflow for reproducing or modifying the assets, not a setup step for players or ordinary builds. It requires Python, an existing GCC 13+ or compatible C++23 compiler, and local `ffmpeg`/`ffprobe` executables. The normal installer does not install that audio-authoring toolchain. The renderer source and its fmt dependency are bundled; no replacement instruments or music are downloaded.

Run the following commands **from the source project's root folder**, in order. Replace `FireRed.gba` and `Sigma.gba` with the local paths to the exact supplied ROM revisions. The extractors verify their SHA-256 hashes before using revision-specific offsets. Metadata `--out` names a directory; move-audio `--out` names a JSON file.

```text
python Tools/extract_rom_audio_metadata.py --firered "FireRed.gba" --sigma "Sigma.gba" --out audio_metadata
python Tools/extract_rom_move_audio.py --firered "FireRed.gba" --sigma "Sigma.gba" --out audio_metadata/move_audio.json
python Tools/native_audio/build_renderer.py
python Tools/native_audio/extract_music.py --kanto-rom "FireRed.gba" --johto-rom "Sigma.gba" --output audio_render
python Tools/assemble_audio_catalog.py --metadata-dir audio_metadata --render-dir audio_render
python Tools/repack_content.py
```

The first four commands create the metadata, cry WAV files, optional renderer and rendered OGG files. Assembly copies the extracted assets into `Client/app/assets/audio`, rebuilds the catalog, verifies its references and checksums, and updates the audio audit records. Repacking publishes matching client/server content metadata. Use a working copy of the source if you want to retain the delivered assets unchanged.

`BUILD_ALL.bat` uses the already assembled files and performs verification/repacking; it does not rerun ROM extraction or compile this optional renderer. After intentional audio changes, build and deploy matching complete Client and Server packs as described above. See `Tools/native_audio/README.md` for renderer-specific options and source/license details.
