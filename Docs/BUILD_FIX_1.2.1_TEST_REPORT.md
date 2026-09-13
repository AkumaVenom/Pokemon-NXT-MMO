# Build fix 1.2.1 validation

This report separates evidence from the supplied Windows build from checks of the new correction. Gameplay and audio content remain at 0.2.0-alpha; build tools are 1.2.1.

## Evidence in the supplied Windows logs

The bootstrap transcript reports successful discovery of Python 3.14.7 and Go 1.27.1. The build log then confirms installed production Python dependency pins, a matching content pack, 225 discovered Python tests (215 passed, 10 skipped), client Go tests, vet for both launchers, both executable compilations, and correct Windows x64 PE subsystems.

The failure occurs afterward, in step 5/7: `audio_missing_origin_blocked` sends an intentionally unauthorized POST and receives `ConnectionResetError: [WinError 10054]` while waiting for an HTTP response. There is no compilation or missing-audio error in this log.

## Correction and regression coverage

`rejectLauncherRequest` consumes bounded rejected body data before writing the original HTTP rejection. The helper's limit is 4,096 bytes plus one overflow probe, with a one-second read deadline. It leaves request cleanup to the HTTP server, does not parse rejected JSON, and does not modify authorization decisions or saved settings.

Three new Go test functions cover nine cases:

- Seven real TCP cases separate the headers and body of a `Connection: close` request: missing/foreign Origin, missing/wrong/duplicate token, wrong method and wrong content type. They require the handler to wait for the complete small body, then deliver its exact HTTP error; settings and files must remain unchanged.
- Oversized rejected data must obey the helper's byte limit.
- A stalled incomplete body must finish within the explicit drain deadline.

The tests assert handler timing as well as response status so the old early-return behavior fails even on a TCP stack that happens to deliver its premature response. New Go APIs fit the project's existing Go 1.23 minimum. An independent source review found no concrete defects in the fix.

Four new Python smoke tests verify that actual HTTP denial remains visible, the original POST is preserved, connection resets/timeouts/EOF are never accepted or silently retried, truncated error responses fail, and the CLI writes failure evidence and exits unsuccessfully. Runtime smoke failures now include the request route and recent launcher output.

## Checks executed for 1.2.1

**229 Python tests discovered: 228 passed, one Windows-only test skipped.** The full result is recorded in `evidence/build_fix_1.2.1_python_tests.txt`. Tests run from a clean source snapshot created by the actual build helper, with only the shipped configuration templates. Audio verification/repack was also executed from that snapshot and published the unchanged pack **e05cb982d1fd4137629f86b0**, validating all **2,366 audio clips**.

Source preservation is recorded in `evidence/build_fix_1.2.1_preservation.json`: the game server code, world data, client application and all client assets remain unchanged. The earlier world startup fix 1.1.2 is retained. Source packaging includes the new Go helper and tests, Python smoke tests, documentation, and updated checksum manifest. Both complete source parts are CRC-checked and their combined file list is checked against the full source tree.

## Execution limits

This Linux environment has no Go compiler, PowerShell or Windows runtime, and ordinary toolchain downloads were unavailable. The **new Go/TCP tests and rebuilt launcher smoke check were not executed here**. The supplied Windows log proves the earlier compilation and tests succeeded, not that the new correction has already been run on Windows. The all-in-one builder still runs Go tests/vet, compiles both launchers, and requires its full HTTP smoke check before publishing output; no gate was removed.

No native Edge playback or live MySQL validation was performed for this build-only correction. Earlier audio validation remains historical evidence for the unchanged sound assets.
