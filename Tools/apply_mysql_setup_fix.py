#!/usr/bin/env python3
"""Apply only the NXT MySQL setup UI hotfix. Standard library; no DB access.

Copied into the standalone hotfix archive as apply_fix.py alongside Payload/.
Source form is retained here for audit/tests. Configuration/saves are never copied.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

FILES = ('setup_mysql.py', 'setup_mysql_gui.py', 'setup_password_input.py',
         '2 - Configure MySQL.cmd', 'MYSQL_SETUP_FIX.md')


class PatchError(RuntimeError):
    pass


def resolve_server(selected: Path) -> Path:
    selected = selected.expanduser().resolve()
    for server in (selected / 'Server', selected):
        if all((server / name).is_file() for name in ('server.py', 'setup_mysql.py', 'config.ini', 'nxt/store.py')):
            if 'Pokemon NXT MMO' in (server / 'server.py').read_text(encoding='utf-8'):
                if server.is_symlink() or any((server / name).is_symlink() for name in FILES):
                    raise PatchError('Refusing linked setup files. Select a normal extracted NXT folder.')
                return server.resolve()
    raise PatchError('Select the Pokemon NXT project folder containing Server, or its Server folder. '
                     'This updater will not patch an unrelated program or a Client-only folder.')


def validated_payload(payload: Path) -> dict[str, bytes]:
    try:
        manifest = json.loads((payload / 'SHA256.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise PatchError('The patch payload manifest is missing or invalid. Extract the entire hotfix ZIP.') from None
    if set(manifest) != set(FILES):
        raise PatchError('Unexpected patch file list. No project files were changed.')
    content = {}
    for name in FILES:
        path = payload / name
        if path.is_symlink() or not path.is_file():
            raise PatchError('The patch payload is incomplete or linked. Extract the entire ZIP.')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest[name]:
            raise PatchError('The patch integrity check failed. No project files were changed.')
        content[name] = data
    return content


def atomic_write(path: Path, data: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=path.parent, delete=False, suffix='.tmp') as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply_patch(selected: Path, payload: Path) -> tuple[Path, Path | None]:
    server = resolve_server(selected)
    content = validated_payload(payload)
    original = {name: (server / name).read_bytes() if (server / name).is_file() else None for name in FILES}
    changes = [name for name in FILES if original[name] != content[name]]
    if not changes:
        return server, None
    backup = server / 'backups' / ('mysql_setup_fix_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:6])
    backup.mkdir(parents=True, exist_ok=False)
    # Backup contains only scripts/docs, never config.ini, databases, or secrets.
    for name in changes:
        if original[name] is not None:
            (backup / name).write_bytes(original[name])
    (backup / 'PATCH_INFO.json').write_text(json.dumps({'setup_version': '1.1.0', 'files': changes,
        'new_files': [n for n in changes if original[n] is None], 'config_or_database_touched': False}, indent=2), encoding='utf-8')
    applied = []
    try:
        for name in changes:
            current = (server / name).read_bytes() if (server / name).is_file() else None
            if current != original[name]:
                raise PatchError('A setup file was edited while applying the patch. Close editors and rerun.')
            atomic_write(server / name, content[name])
            applied.append(name)
    except Exception:
        failed_restores = []
        for name in reversed(applied):
            try:
                if original[name] is None:
                    (server / name).unlink(missing_ok=True)
                else:
                    atomic_write(server / name, original[name])
            except OSError:
                failed_restores.append(name)
        if failed_restores:
            raise PatchError('Patch interrupted and some setup files could not be restored. Restore the backed-up scripts from: ' + str(backup)) from None
        raise PatchError('Patch could not complete; replaced scripts were restored. Your config/database was not edited. Check folder permissions.') from None
    return server, backup


def choose_folder(start: Path) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            folder = filedialog.askdirectory(title='Select Pokemon NXT project folder (contains Server), or the Server folder',
                                            initialdir=str(start), mustexist=True, parent=root)
        finally:
            root.destroy()
        return Path(folder) if folder else None
    except (ImportError, RuntimeError):
        pass
    except Exception:
        pass
    value = input('Paste the path to your Pokemon NXT project folder (contains Server), or its Server folder: ').strip().strip('"')
    return Path(value) if value else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Patch only Pokemon NXT MySQL setup. Never changes config, passwords or saves.')
    parser.add_argument('--target', type=Path, help='Project/Server folder. Otherwise a folder picker opens.')
    parser.add_argument('--no-open', action='store_true', help='Do not open the Server folder after patching.')
    args = parser.parse_args(argv)
    here = Path(__file__).resolve().parent
    print('Pokemon NXT MMO - MySQL password-entry hotfix 1.1.0\n')
    print('Close the OLD database setup window first. This changes only setup scripts and their guide.')
    print('It does not read, replace or reset your database passwords, config.ini, game saves or assets.\n')
    try:
        target = args.target or choose_folder(here.parent)
        if target is None:
            print('Cancelled. No project changes.')
            return 1
        server, backup = apply_patch(target, here / 'Payload')
        print('\nPatch installed.' if backup else '\nThis setup fix is already installed.')
        print('Server folder: ' + str(server))
        if backup:
            print('Previous setup scripts backed up in: ' + str(backup))
        print('\nNOW run: 2 - Configure MySQL.cmd inside that Server folder.')
        print('Use your EXISTING MySQL root password. Leave it blank only when none is set.')
        print('Leave both NXT application password fields blank to generate/reuse automatically.')
        print('No EXE rebuild or database reset is needed.')
        if os.name == 'nt' and not args.no_open:
            os.startfile(server)
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
        return 1
    except PatchError as exc:
        print('\nPATCH NOT COMPLETED: ' + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'\nPATCH NOT COMPLETED [{type(exc).__name__}]. Check the selected folder and write permissions.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
