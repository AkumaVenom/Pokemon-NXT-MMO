# Third-party notices and technical references

The extracted Pokemon game/ROM-hack graphics, data, names and trademarks remain the material of their respective rights holders. The project does not claim endorsement, public redistribution rights or a commercial license to them. No source ROM, original ARM executable code, proprietary operating-system runtime or font files are included. See Docs/ASSET_SOURCES.md for exact source hashes and extraction limitations.

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
