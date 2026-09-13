# All-in-one build fix 1.2.1

This fixes the reported `ConnectionResetError: [WinError 10054]` at step 5/7, while the launcher smoke test checks `audio_missing_origin_blocked`.

## Build the complete updated source

1. Download both **1.2.1** source ZIPs, Part 1 and Part 2.
2. Extract both into the **same fresh destination**. Both archives contain the project folder `Pokemon_NXT_MMO_v0.2.0-alpha_Source_Audio_1.2.1`; allow those folders to merge.
3. Open that project folder and run `BUILD_ALL.bat`. The banner must show **1.2.1**. Both parts must be extracted before starting.
4. A successful run prints the new Client/Server output folders and updates `dist/LATEST_BUILD.txt`.

This is the full source delivery, including the complete audio bank and the build fix. Part 1 contains source, templates, the audio catalog and cry WAVs; Part 2 contains all music/effect OGGs. Existing compatible Python and Go installations are detected automatically.

The build does not run MySQL setup or change passwords. When deploying the newly built output, preserve your working client/server configurations and database as described in `AUDIO_GUIDE.md`.

## What caused the failure

The supplied Windows logs show that Python/Go detection, dependency installation, audio verification, Python tests, Go tests/vet and both Windows executable builds succeeded. The build then stopped during the launcher HTTP checks.

The failing request intentionally omits its Origin header to verify that settings remain protected. Python's HTTP client sends `Connection: close`; the launcher previously returned HTTP 403 before consuming the accompanying JSON body. Go's automatic body cleanup skips that closing-connection case. Unread request bytes can cause a TCP reset on Windows, losing the error response before Python can read it.

The launcher now discards a bounded small body before sending its original rejection status. The helper reads at most 4,096 bytes plus one overflow probe and sets a one-second read deadline. It does not parse or save rejected data. Large or incomplete rejected uploads close the connection without being drained indefinitely; the HTTP server retains its own cleanup responsibilities.

Authorization checks remain enforced. A reset or timeout still fails the smoke test; it is never counted as HTTP 403 and the build does not skip validation. Smoke errors now include the request route, launcher exit/running state and recent launcher output.

Primary implementation references: [Go HTTP server](https://go.dev/src/net/http/server.go) and [Go request-body cleanup](https://go.dev/src/net/http/transfer.go).

## Validation scope

`BUILD_FIX_1.2.1_TEST_REPORT.md` records checks run for this correction separately from the successful stages in the supplied Windows log. New Go tests use real TCP connections and split headers/body data to exercise the failure condition even on platforms that happen to preserve a premature response. They also check unchanged settings, byte limits and a stalled upload deadline.

Gameplay remains **0.2.0-alpha**, content pack **e05cb982d1fd4137629f86b0**, with all **2,366 audio clips** and world startup fix **1.1.2** preserved.
