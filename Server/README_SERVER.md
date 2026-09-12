# Pokemon NXT MMO · Private world server

This folder is administrator-only. It contains the MySQL configuration, world logic and private save data after setup. Do not distribute it to players.

Install 64-bit Python 3.11+ and start your MySQL service, then run these scripts in order:

```text
1 - Install Server Dependencies.cmd
2 - Configure MySQL.cmd
3 - Start World Server.cmd
```

Defaults create an independent `pokemon_nxt_mmo` database and `pokemon_nxt` application user. Supply your existing administrator credentials; no root password is changed. The executable is a console launcher for the local Python environment, not a bundled database/Python installer. Read `../Docs/QUICK_START.md` in the complete or server distribution for the full instructions.

Type `help`, `status`, `players`, `save` or `shutdown` in the world console. The default listener is private-LAN testing on TCP 7777 with a 1,000-account hard cap, not a verified load rating. Internet exposure requires correct direct TLS and further testing. Never expose MySQL to player clients.

`Start Developer SQLite World.cmd` selects a deliberately separate developer backend. A MySQL failure never falls back automatically. SQLite tests do not prove MySQL deployment. Windows launch and MySQL runtime acceptance are still required on your system; shared server/network/UI tests were executed on Linux.

## Password-entry hotfix 1.1.0

`2 - Configure MySQL.cmd` opens editable password fields and a read-only login test. The administrator field needs the **existing MySQL password**, not a new one. Blank is accepted as input but works only for a genuinely passwordless MySQL account. Leave both NXT application password fields blank to generate/reuse automatically. Read `MYSQL_SETUP_FIX.md`. No root-password reset, database deletion or EXE rebuild is part of this fix.
