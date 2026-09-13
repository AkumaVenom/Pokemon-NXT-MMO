# Third-party notices and technical references

The extracted Pokemon game/ROM-hack graphics, music, sound effects, cries, data, names and trademarks remain the material of their respective rights holders. The project does not claim endorsement, public redistribution rights or a commercial license to them. No source ROM, original ARM executable code, proprietary operating-system runtime or font files are included. See Docs/ASSET_SOURCES.md for the original asset audit and Docs/AUDIO_GUIDE.md for audio coverage and limitations.

The launcher executables include the Go standard library/runtime. Its license is reproduced in Client/GO_LICENSE.txt and Server/GO_LICENSE.txt. No third-party Go modules were added. Edge is an external installed application, not bundled in this archive. Python and its server dependencies are installed separately under their own licenses; those packages are not embedded in the ZIP.

Primary project/package references checked for the server dependency pins:

```text
https://docs.aiohttp.org/en/stable/
https://docs.aiohttp.org/en/stable/changes.html
https://pypi.org/project/PyMySQL/1.2.0/
https://github.com/PyMySQL/PyMySQL
https://go.dev/LICENSE
https://github.com/pret/pokefirered
```

Server install pins are aiohttp 3.14.3 and PyMySQL[rsa] 1.2.0. Recorded local runtime tests used aiohttp 3.13.3; they do not establish that the latest pinned combination or MySQL was run here. See TEST_REPORT.md.

## Native audio extraction tools

The optional renderer under `Tools/native_audio` uses the MP2K engine from [ipatix/agbplay](https://github.com/ipatix/agbplay), distributed under the **GNU Lesser General Public License, version 3**. The bundled `core/` directory contains the selected upstream modules and the NXT-modified modules needed to build this renderer. The NXT changes are dated **2026-09-12** and include the plain-ROM file adapter, resampling helper substitution, bounded sequence validation, explicit error reporting and loop diagnostics. Those modifications remain under the same LGPL version 3 terms. `SOURCE_PROVENANCE.json` records the source snapshot, upstream and bundled file hashes, and changed modules; the renderer adapter and build scripts are supplied alongside the engine source.

The complete LGPL and incorporated GPL license texts are provided in `Tools/native_audio/COPYING-LGPL-3.txt` and `Tools/native_audio/COPYING-GPL-3.txt`. The upstream LGPL license copy is also retained as `Tools/native_audio/LICENSE-LGPL-3.0.txt`. The source and rebuild instructions in `Tools/native_audio/README.md` permit rebuilding the optional renderer with modified engine code. The game plays the rendered audio files; it does not link or load the agbplay engine during gameplay.

The renderer's **fmt 10.2.1** dependency is from [fmtlib/fmt](https://github.com/fmtlib/fmt), copyright **2012–present Victor Zverovich and {fmt} contributors**, under the **MIT license**. Its copyright, permission notice, warranty disclaimer and optional compiled-object exception are reproduced in `Tools/native_audio/vendor/fmt/LICENSE`. The dependency source is supplied in that directory.

## Rendered ROM audio

The audio bank was extracted from the user's supplied **Pokemon - FireRed Version (USA, Europe) (Rev 1)** and **Pokemon Ultra Shiny Gold Sigma Completo 1.5.0** ROM files. It retains their native musical sequences, instruments, effects and species-voice assignments, subject to the documented extraction repairs and unavailable unused cry slots. The rendered music/effects and decoded cry assets remain third-party game/ROM-hack material; the renderer's open-source license does not assign ownership of that source material.

`Tools/audio_provenance/render_manifest.json` records the exact ROM SHA-256 values, audio hashes, loop data and the two documented Sigma recoveries. `Docs/AUDIO_GUIDE.md` explains the preserved Sigma cry aliases and the alpha gameplay presentation limits. The original ROM files are not packaged.
