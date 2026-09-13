# Battle feedback · 0.3.2-alpha

Both Pokémon now make a short lunge when attacking. The defender reacts to a
hit, with floating damage and server-reported effectiveness beside its sprite.
Critical hits, resisted attacks, immunity, misses, protection, recovery and
fainting have distinct readable feedback. The native sprites remain unchanged.

The client presents accepted battle events in order. It never calculates
damage or type matchups, spends PP or advances the world locally. A normal
two-attack exchange takes roughly 2.4 seconds to present. Battle choices are
temporarily disabled during playback and while submitting an action, so fast
clicks do not submit another move before the visible exchange completes.
The server's own waiting and turn validation remain authoritative.

Move sounds use the same short presentation beats as the visual feedback.
Long native script delays are compressed into the move's window. A newer move
or turn retires earlier transient sounds and delayed loads; background battle
music and the low-HP loop remain independent. This is a compact MMO presentation,
not emulation of every original GBA battle-animation script.

Repeated waiting snapshots do not replay animations or sound. A newer revision,
different battle, logout or disconnect invalidates obsolete callbacks. System
reduced-motion preferences disable movement while retaining the text feedback.

## Install the complete corrected source

Version 0.3.3 corrects the battle screen regression described in
`BATTLE_SCREEN_FIX.md`. Extract both Full_Source_Part1 and Full_Source_Part2 ZIPs
into the same destination, then run `BUILD_ALL.bat` in the merged project folder.
Both parts are required; no earlier package is needed.

Stop the deployed world cleanly before upgrading. Preserve its database,
`config.ini`, certificates and private deployment files, along with the client's
working connection settings. Deploy matching updated Client and Server files.
This update does not require account resets, MySQL setup or audio re-extraction.
All prior learnset, Move Reminder, progression, Nurse Joy, replication and
online-hosting features remain included.

## Historical 0.3.2 validation scope (before the screen correction)

Focused regressions exercise the actual presentation/audio modules with fake
clocks, DOM and Web Audio adapters: attack direction, event text, duplicate and
stale snapshots, revision cancellation, delayed decode cancellation and cleanup.
Existing registration, learnset, replication and audio integration checks are
run alongside them. The build includes the new modules and regression gates.
Content publication still verifies every bundled audio clip and matching
Client/Server pack metadata.

No combat or persistence rules change in this update. Native browser rendering
and listening on Windows still require a playtest; automated adapters do not
prove the final appearance or device-specific audio. The previous release's
full build results are recorded separately in `LEARNSET_TEST_REPORT.md`.

Executed for 0.3.2 (these adapter tests missed the native timer receiver bug): **78 client integration/presentation tests passed**,
**34 audio engine checks passed**, and **69 Python audio/build/bootstrap tests
passed**, with one explicit native-Windows PowerShell skip (70 run). JavaScript
module syntax and Python syntax passed. The published content pack is
`187edcf8a65511058395a99b`, with all 2,366 audio clips verified.
The complete native compilation pipeline was not repeated for this presentation
update; launcher Go code and gameplay logic remain unchanged.
