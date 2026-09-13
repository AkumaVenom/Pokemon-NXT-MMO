# Battle screen correction · 0.3.3-alpha

## What went wrong

The 0.3.2 effect controller stored native `setTimeout` and `clearTimeout` as
object properties, then invoked them with the controller as their receiver.
Browser timer functions require their Window context. The first real battle
snapshot includes sendout events, so it schedules timers immediately.

The client previously started those effects before calling `showModal()`.
A timer exception could therefore stop the dialog from opening after battle
audio had already started. The controller could remain busy and suppress
subsequent rendering. Earlier fake-clock tests missed the receiver requirement
and their application entry fixture had no sendout events.

## What changed

- Default effect timers call the global timer functions with the correct context.
- The populated battle dialog opens before optional effects start.
- An effect startup or scheduled animation failure cancels pending effects,
  restores the authoritative sprites and releases the presentation lock.
  Effect playback is suppressed for the rest of that battle so failures cannot
  create an automatic replay loop. Returning to the world or reconnecting resets it.
- Fallback mode remembers the presented snapshot revision. Repeated or stale
  snapshots cannot clear an outstanding action submission or replay feedback.
- Server waiting, move availability and submission checks still apply. Effects
  never generate damage, spend PP, change battle results or write saves.

The attack movements, damage/effectiveness labels, reduced-motion support and
previous sound cancellation remain included. No combat, save schema or account
migration is introduced by this correction. All previously supplied art and
audio bytes are preserved.

## Install the full source

1. Download `Pokemon_NXT_v0.3.3_Full_Source_Part1.zip` and
   `Pokemon_NXT_v0.3.3_Full_Source_Part2.zip`.
2. Extract both into the same new destination. Merge the identically named
   `Pokemon_NXT_MMO_v0.3.3-alpha_Source_BattleScreenFix` folders.
3. Run the merged folder's `BUILD_ALL.bat`. Its build banner is **1.3.3** and
   the game version is **0.3.3-alpha**. Both ZIPs are required; no older pack,
   ROM conversion or separate audio downloads are needed.
4. Close the old clients, stop the deployed world cleanly, and back up the
   configured server. Deploy the matching newly built Client and Server.
   Preserve the server's working `config.ini`, database and certificates, and
   the client's working connection settings. Do not overwrite those with clean
   configuration templates or rerun MySQL setup just to install this update.
5. Launch the newly built client and enter an encounter. The battle dialog
   should appear immediately, then finish its short sendout before enabling moves.

This source update does not erase existing accounts or progression.

## Verification

The strengthened Node regression reproduces `TypeError: Illegal invocation`
against the old controller with a receiver-sensitive browser-timer adapter.
The corrected controller passes the same test, including actual initial
`battle_start` and both `sendout` event shapes.

All **17 battle presentation/application tests pass**, covering both attack
directions, authoritative damage and effectiveness text, entry visibility,
default timer cancellation, repeat turns, partial timer-start failure,
asynchronous animation failure, stale callbacks and duplicate submission guards.
These are automated adapter tests, not a claim that a real browser was run.

The optional `Tests/check_battle_browser.mjs` harness uses actual client modules
and DOM with controlled snapshots. It is syntax-checked and supplied for native
browser acceptance. **Browser execution was unavailable here:** Playwright was
installed but Chromium was absent, and its download timed out. Native
Windows/Edge rendering and listening still need a playtest.

The full **1.3.3 build pipeline succeeded** on Linux with the exact production
Python dependency pins enforced and cached toolchains reused (`--no-install`).
Executed results:

| Check | Result |
| --- | --- |
| Python server/content/build regressions | 469 run; 468 passed; one Windows PowerShell check explicitly skipped |
| JavaScript integration/presentation regressions | 84 passed, including the 17 battle tests |
| Audio engine regressions | 34 passed |
| Headless compiled launcher HTTP checks | 26 passed |
| Launcher Go tests and Windows-target static checks | Passed for Client and Server |
| Windows x64 executables | Both cross-compiled and PE headers/subsystems verified |
| Extracted content publication | 959 maps, 876 catalog entries, 11,110 PNGs and all 2,366 audio clips verified |
| Complete build/package pipeline | Succeeded; release ZIPs decompressed and verified |

Published matching Client/Server content pack: `f3fb73c50be4b6b77359cd73`.
The build used cached compilers and pinned Python packages; this does not claim
that fresh Windows prerequisite downloads, native Edge UI, live MySQL hosting
or a production TLS deployment were exercised. No live world was modified.

The full-source delivery is independent of older archives. Its Part 1 contains
`SOURCE_SHA256SUMS.txt` for all files across both parts. Each archived file was
decompressed and compared against that manifest; every previous PNG, OGG and
WAV is retained byte-for-byte.
