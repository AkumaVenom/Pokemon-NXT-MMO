#!/usr/bin/env python3
"""Install the NXT world-startup scripts only; no database or process access.

Distributed as apply_fix.py beside Payload/SHA256.json in the small hotfix ZIP.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid

FILES = ('server.py', 'nxt/store.py', '3 - Start World Server.cmd')
VERSION = '1.1.2'


class PatchError(RuntimeError):
    pass


def reject_links(path: Path) -> None:
    """Check every component, including Windows junctions and directory links."""
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise PatchError('Linked files or folders are not supported. Select a normal extracted NXT folder.')


def checked_bytes(path: Path, *, optional: bool = False) -> bytes | None:
    reject_links(path)
    if optional and not path.exists():
        return None
    if not path.is_file():
        raise PatchError('A required script is missing or is not a normal file: ' + path.name)
    return path.read_bytes()


def resolve_server(selected: Path) -> Path:
    # Do not resolve symlinks before checking them.
    selected = Path(os.path.abspath(selected.expanduser()))
    reject_links(selected)
    for server in (selected / 'Server', selected):
        reject_links(server)
        if all((server / name).is_file() for name in ('server.py', 'config.ini', 'nxt/store.py')):
            for name in (*FILES, 'config.ini', 'backups'):
                reject_links(server / name)
            if b'Pokemon NXT MMO' in checked_bytes(server / 'server.py'):
                return server
    raise PatchError('Select your existing Pokemon NXT Server folder, or the project folder containing it.')


def validated_payload(payload: Path) -> dict[str, bytes]:
    payload = Path(os.path.abspath(payload))
    try:
        manifest = json.loads(checked_bytes(payload / 'SHA256.json'))
    except (OSError, ValueError, TypeError):
        raise PatchError('The payload manifest is missing or invalid. Extract the entire hotfix ZIP.') from None
    if not isinstance(manifest, dict) or set(manifest) != set(FILES):
        raise PatchError('Unexpected patch file list. No project files were changed.')
    content = {}
    for name in FILES:
        data = checked_bytes(payload / name)
        if hashlib.sha256(data).hexdigest() != manifest[name]:
            raise PatchError('The patch integrity check failed. Extract the entire hotfix ZIP again.')
        content[name] = data
    return content


def directory_id(path: Path) -> tuple[int, int]:
    reject_links(path)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise PatchError('An expected folder was replaced. Close editors and retry.')
    return info.st_dev, info.st_ino


def check_directories(identities: dict[Path, tuple[int, int]]) -> None:
    for directory, expected in identities.items():
        if directory_id(directory) != expected:
            raise PatchError('A selected folder changed during patching. No further scripts were replaced.')


def atomic_write(path: Path, data: bytes) -> None:
    reject_links(path)
    identity = directory_id(path.parent)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=path.parent, delete=False, suffix='.tmp') as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        reject_links(path)
        if directory_id(path.parent) != identity:
            raise PatchError('The destination folder changed during patching.')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            # Never follow a newly substituted parent while cleaning up.
            try:
                if directory_id(path.parent) == identity:
                    temporary.unlink(missing_ok=True)
            except (OSError, PatchError):
                pass


def apply_patch(selected: Path, payload: Path) -> tuple[Path, Path | None]:
    server = resolve_server(selected)
    identities = {path: directory_id(path) for path in (server, server / 'nxt')}
    content = validated_payload(payload)
    original = {name: checked_bytes(server / name, optional=True) for name in FILES}
    changes = [name for name in FILES if original[name] != content[name]]
    if not changes:
        return server, None
    check_directories(identities)
    backup = server / 'backups' / ('world_startup_fix_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:8])
    reject_links(backup)
    backup.mkdir(parents=True, exist_ok=False)
    for name in changes:
        if original[name] is not None:
            destination = backup / name
            reject_links(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(original[name])
    (backup / 'PATCH_INFO.json').write_text(json.dumps({
        'startup_fix_version': VERSION, 'files': changes,
        'new_files': [name for name in changes if original[name] is None],
        'config_or_database_touched': False,
    }, indent=2), encoding='utf-8')
    applied = []
    try:
        for name in changes:
            check_directories(identities)
            if checked_bytes(server / name, optional=True) != original[name]:
                raise PatchError('A script changed during patching. Close editors and retry.')
            atomic_write(server / name, content[name])
            applied.append(name)
        check_directories(identities)
        if any(checked_bytes(server / name) != content[name] for name in FILES):
            raise PatchError('A script changed before patching completed. Close editors and retry.')
    except Exception as exc:
        failed_restores = []
        for name in reversed(applied):
            try:
                check_directories({path: identities[path] for path in (server, (server / name).parent)})
                if checked_bytes(server / name, optional=True) != content[name]:
                    raise PatchError('A patched script was edited externally; preserving that edit.')
                if original[name] is None:
                    (server / name).unlink(missing_ok=True)
                else:
                    atomic_write(server / name, original[name])
            except Exception:
                failed_restores.append(name)
        if failed_restores:
            raise PatchError('Patch interrupted; some scripts could not be safely restored. '
                             'Previous scripts are in: ' + str(backup)) from None
        detail = str(exc) if isinstance(exc, PatchError) else 'Check folder permissions and retry.'
        raise PatchError('Patch did not complete; replaced scripts were restored. ' + detail) from None
    return server, backup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Apply the Pokemon NXT world startup fix to an existing Server folder.')
    parser.add_argument('--target', required=True, type=Path, help='Existing configured Server folder, or its project folder.')
    args = parser.parse_args(argv)
    print('Pokemon NXT MMO - World Startup Fix ' + VERSION, flush=True)
    print('Updating three startup scripts. No database connection or EXE build is performed.', flush=True)
    try:
        server, backup = apply_patch(args.target, Path(__file__).resolve().parent / 'Payload')
        print('\nFix installed.' if backup else '\nThis fix is already installed.')
        print('Server folder: ' + str(server))
        if backup:
            print('Previous scripts: ' + str(backup))
        print('\nNow double-click: 3 - Start World Server.cmd in that Server folder.')
        print('Your existing configuration, Python environment, accounts and saves were preserved.')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.', file=sys.stderr)
        return 1
    except PatchError as exc:
        print('\nPATCH NOT COMPLETED: ' + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print('\nPATCH NOT COMPLETED [' + type(exc).__name__ + ']. Check the target folder and write permissions.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
