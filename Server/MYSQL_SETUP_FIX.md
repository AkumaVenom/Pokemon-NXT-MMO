# MySQL password-entry hotfix 1.1.0

Pokemon NXT MMO gameplay/protocol/database schema remain **0.1.0-alpha**.

## Open the corrected setup

Close the old setup window. Start your existing MySQL service (or XAMPP Control Panel > MySQL > Start), then double-click **`2 - Configure MySQL.cmd`** in this Server folder. No client/server EXE rebuild is needed for the hotfix.

The setup now has editable password boxes that show `*` while you type, normal paste/selection, and a **Show passwords** checkbox. Turn that checkbox off before taking a screenshot or sharing your screen. No passwords are printed by the program, passed through CMD variables, or included in diagnostic exception text.

**Existing administrator password** means the password already assigned to your MySQL account, usually `root`. This is NOT a prompt to create a new root password, a Windows administrator login, or an in-game administrator account. This utility does not reset MySQL root.

An empty administrator field is sent as an actual empty password. It can authenticate ONLY if the existing MySQL account permits an empty password. A blank field is not an authentication bypass. A protected database needs its existing password. Do not reuse the NXT application field as a substitute.

Click **Test administrator login (no changes)**. The test only connects and runs `SELECT 1`. On failure you can edit the fields and retry without restarting the form. The error distinguishes refused credentials from an unreachable server, permissions, certificate problems and password-policy failures.

Leave these defaults for a separate local NXT database unless your own server settings differ:

```text
MySQL host / IP:           127.0.0.1
MySQL port:                3306
Existing admin username:   root
NXT database:              pokemon_nxt_mmo
NXT application username:  pokemon_nxt
World host as MySQL sees:  localhost
```

For **NXT application password** and **Confirm custom password**, leave BOTH blank to reuse an already configured matching account password or generate a strong new password. Alternatively type the same new password, 12-256 characters, in both boxes. This is separate from MySQL root and from player login passwords.

Click **Configure NXT database and save**. A successful setup verifies the application login and atomically saves its credentials in **Server/config.ini only**. Then run **`3 - Start World Server.cmd`**.

## Existing or partially configured accounts

The setup never silently changes an existing user's password. If an older setup created `pokemon_nxt` with a password you no longer have, supply that existing application password or choose a new dedicated username, such as `pokemon_nxt2`. Keep the existing NXT database name to keep the same database. Do not drop the database to repair a login.

The setup now checks a reused application's login before attempting any database/account creation or grants. MySQL DDL is not one all-or-nothing transaction: an operation later in provisioning can fail after a new account/database was created. A failed verification leaves config.ini unchanged; it does not claim to undo already committed DDL.

A conflicting `POKEMON_NXT_DB_PASSWORD` environment override is reported before provisioning. Remove a stale override or provide its matching application password. The tool does not silently modify persistent Windows environment settings.

Configuration edits detected while setup is running are not overwritten. Other world settings/comments remain intact. Existing root passwords, unrelated tables, saves, client assets and gameplay code are not reset by this patch. Give players only the Client folder, never a configured Server folder.

## Console fallback

The official Windows Python installer normally includes Tcl/Tk. If Tk is unavailable, setup falls back to interactive console entry with `*` feedback. It supports the project's Python 3.11+ floor without relying on the Python 3.14-only `getpass(echo_char=...)` option.

Manual console mode, from the Server folder:

```bat
.venv\Scripts\python.exe setup_mysql.py --console
```

For an explicitly visible console input fallback:

```bat
.venv\Scripts\python.exe setup_mysql.py --console --visible-passwords
```

The last command intentionally displays passwords; do not screen-share or record that terminal. Masking is the default. Do not pipe setup input/output through another tool. The graphical form is recommended for clipboard shortcuts and normal cursor editing.

## Verification boundary

Core setup tests use an injected fake MySQL connector. Real Tk form/widget/clipboard/worker tests run on Linux under Xvfb. These tests check entry, validation, error handling, config writes and safe failure paths; they do not establish Windows-native or live MySQL/MariaDB acceptance. The existing gameplay/network suite uses disposable SQLite fixtures. No production credentials or live user database were accessed.

Official API references reviewed for this fix:

- Python password input and default no-echo behavior: https://docs.python.org/3/library/getpass.html
- Tkinter event loop and worker-thread considerations: https://docs.python.org/3/library/tkinter.html
- PyMySQL connection/password/timeouts/TLS arguments: https://pymysql.readthedocs.io/en/latest/modules/connections.html
- MySQL login troubleshooting and account/password matching: https://dev.mysql.com/doc/refman/8.4/en/problems-connecting.html
