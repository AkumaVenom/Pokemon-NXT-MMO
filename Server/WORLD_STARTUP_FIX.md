# Pokemon NXT MMO — World startup fix 1.1.2

This update corrects startup cleanup and missing failure logs. A failed startup previously could keep its database lease until expiry; the next attempt then reported another world owner while the original error was absent from world.log. An actual running second NXT world can also cause that message.

## Apply to an already configured server

1. Stop any running Pokemon NXT world cleanly with `shutdown` or Ctrl+C. Close failed startup windows.
2. Extract the complete `Pokemon_NXT_MMO_World_Startup_Fix_1.1.2.zip` to a writable folder.
3. Double-click `APPLY_WORLD_STARTUP_FIX.cmd` and paste the existing Server folder path (the folder containing config.ini and `3 - Start World Server.cmd`). Alternatively, drag that Server folder onto the CMD.
4. Run `3 - Start World Server.cmd` in your existing Server folder.

The updater verifies payload hashes and backs up the previous scripts under Server/backups. It updates only server.py, nxt/store.py and the startup CMD. No EXE rebuild, dependency reinstall, MySQL setup rerun or database reset is needed. Configurations, credentials, .venv, accounts and game assets are preserved.

## What startup now reports

The console prints the actual absolute log path before reading settings, content or the database. Startup and failure details go to that log; if the normal logs folder cannot be written, the console names the fallback location. Bind/port, TLS, extension and configuration stages are identified without dumping credentials.

Startup retries a recent database lease for up to 65 seconds. A lease that stops refreshing can expire normally, after which startup continues automatically. A lease that is being refreshed belongs to another active NXT world and is not overridden. Stop that world before starting this one. Future timestamps prompt a clock check.

Any newly failed startup cleans up its listener/resources and releases only its own database lease, so the next attempt can immediately reach and diagnose the original problem.

## Source releases

The full source with build tools 1.1.2 includes the same corrected server scripts and retains the Go prerequisite fix from 1.1.1. Gameplay remains 0.1.0-alpha, database schema 1, and MySQL setup version 1.1.0. See `Docs/WORLD_STARTUP_FIX_TEST_REPORT.md` for executed validation.
