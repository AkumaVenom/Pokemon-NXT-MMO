#!/usr/bin/env python3
"""Build and package Pokemon NXT MMO without modifying a live installation.

The Windows entry point is BUILD_ALL.bat. This driver also supports Linux-to-
Windows cross-build verification. BUILD_ALL.bat automatically provisions missing
Windows Python/Go toolchains before invoking this driver.
Only the build virtual environment receives pip packages. No database is opened
except disposable SQLite fixtures owned by the regression suite.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import contextlib
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from typing import Iterator, Mapping, Sequence, TextIO

BUILD_TOOL_VERSION = "1.3.4"
ROOT = Path(__file__).resolve().parents[1]
TOP_FILES = {
    "README.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", ".gitignore",
    "BUILD_ALL.bat", "START_HERE_BUILD.md",
}
TREE_EXTENSIONS = {
    "Client": {".go", ".mod", ".sum", ".js", ".mjs", ".css", ".html", ".json", ".png", ".ogg", ".wav", ".md", ".txt"},
    "Server": {".py", ".go", ".mod", ".sum", ".json", ".md", ".txt", ".cmd", ".bat"},
    "Tools": {".py", ".json", ".md", ".txt"},
    "Tests": {".py", ".ps1", ".mjs", ".md", ".txt"},
    "Docs": {".md", ".txt", ".json", ".png"},
    "Build": {".py", ".ps1", ".md", ".txt", ".json", ".ini"},
}
NATIVE_AUDIO_SOURCE_EXTENSIONS = {".cpp", ".cc", ".c", ".h", ".hpp", ".hxx", ".inc", ".cmake", ".sh", ".in", ".rst"}
NATIVE_AUDIO_LICENSE_NAMES = {"license", "copying", "notice", "authors", "copyright", "copying.lesser"}
NATIVE_AUDIO_IGNORED_DIRS = {"build", "_build", "obj", "cmakefiles", "cmake-build-debug", "cmake-build-release"}
IGNORED_DIRS = {
    ".git", ".venv", "venv", ".build", "dist", "__pycache__", "node_modules",
    ".idea", ".vscode", "ui_artifacts", "packages", "backups", "backup",
}
FORBIDDEN_EXTENSIONS = {
    ".gba", ".gb", ".gbc", ".nds", ".rom", ".exe", ".dll", ".pyd",
    ".pyc", ".pyo", ".sqlite", ".sqlite3", ".db", ".sql", ".dump",
    ".key", ".pem", ".pfx", ".p12", ".crt", ".cer", ".env", ".log", ".zip",
}
SOURCE_DATA_FILES = {
    "world.json", "adventure.json", "adventure_rom.json", "centers.json",
    "interior_repairs.json", "interior_maps.json",
    "interior_navigation.json", "learnsets.json",
    "encounters_firered.json", "encounters_crystal.json", "encounter_bindings.json", "species_additions.json", "varieties.json",
}
REQUIRED_SOURCE = (
    "Server/nxt/varieties.py", "Server/data/varieties.json", "Tools/publish_varieties.py",
    "Tools/import_variety_assets.py", "Client/app/varieties.js", "Tests/test_varieties.py", "Tests/check_varieties.mjs",
    "Server/nxt/encounters.py", "Server/nxt/field_moves.py",
    "Server/data/encounters_firered.json", "Server/data/encounters_crystal.json",
    "Server/data/encounter_bindings.json", "Server/data/species_additions.json",
    "Tools/publish_encounters.py", "Tools/crystal_encounter_catalog.py", "Tests/test_regional_encounters_cut.py",
    "Client/launcher/go.mod", "Client/launcher/main.go", "Client/launcher/platform_windows.go",
    "Client/app/index.html", "Client/app/app.js", "Client/app/renderer.js", "Client/app/styles.css",
    "Client/app/audio.js", "Client/app/battle_fx.js", "Client/app/battle_timing.js", "Tests/check_battle_fx.mjs", "Client/app/audio_controls.js", "Client/app/assets/audio/catalog.json",
    "Client/launcher/audio_settings.go",
    "Client/app/assets/world/client.json", "Server/launcher/go.mod", "Server/launcher/main.go",
    "Server/server.py", "Server/nxt/store.py", "Server/data/world.json", "Server/requirements.txt",
    "Server/nxt/tls.py", "Server/setup_online.py", "Server/setup_online_gui.py",
    "Server/2b - Configure Online Hosting.cmd", "Tests/test_online_setup.py", "Tests/test_tls_network.py",
    "Tools/repack_content.py", "Tools/verify_audio.py", "Tests/test_core.py", "Tests/test_network.py",
    "Server/nxt/async_tasks.py", "Server/nxt/world.py",
    "Server/nxt/adventure.py", "Server/nxt/growth.py", "Server/nxt/portals.py",
    "Server/data/adventure.json", "Server/data/adventure_rom.json", "Server/data/centers.json",
    "Server/data/interior_repairs.json", "Server/data/interior_maps.json",
    "Server/data/interior_navigation.json",
    "Tools/publish_adventure.py", "Tools/prepare_centers.py", "Tools/repair_interiors.py",
    "Tools/extract_adventure_data.py", "Tools/extract_learnsets.py", "Tools/publish_learnsets.py",
    "Server/data/learnsets.json", "Tests/test_learnset_rom.py", "Tests/test_learnset_runtime.py",
    "Tests/test_learnset_network.py", "Tests/test_learnset_publish.py", "Tests/test_sigma_moves.py", "Tests/check_learnsets.mjs",
    "Tests/test_adventure.py", "Tests/test_growth.py", "Tests/test_adventure_combat.py",
    "Tests/test_adventure_network.py", "Tests/check_adventure_ui.mjs",
    "Tests/test_centers.py", "Tests/test_interior_access.py", "Tests/test_adventure_rom.py",
    "Tests/test_async_tasks.py", "Tests/test_replication_state.py", "Tests/test_replication_network.py",
    "Tests/test_login_lifecycle.py", "Tests/test_progress_persistence.py",
    "Tests/check_registration.mjs", "Tests/check_renderer_replication.mjs",
    "Build/smoke_launcher.py", "Build/config_templates/Client/config.ini",
    "Build/config_templates/Server/config.ini", "BUILD_ALL.bat",
    "Build/bootstrap_windows.ps1", "Build/bootstrap_lib.ps1", "Build/toolchains.json",
)


class BuildError(RuntimeError):
    """An actionable, expected failure of a build step."""


class Log:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.file: TextIO = path.open("w", encoding="utf-8", newline="\n")

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        self.file.write(text + "\n")
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def is_source_file(relative: Path | PurePosixPath) -> bool:
    """Explicit source-tree allowlist; never copy a deployed configuration."""
    path = PurePosixPath(relative.as_posix())
    parts = path.parts
    if not parts or path.is_absolute() or ".." in parts:
        return False
    if any(part.casefold() in IGNORED_DIRS for part in parts):
        return False
    name = path.name.casefold()
    if name.startswith(".env") or ".sqlite" in name or name.startswith("sha256sums"):
        return False
    if path.suffix.casefold() in FORBIDDEN_EXTENSIONS:
        return False
    if len(parts) == 1:
        return path.name in TOP_FILES
    top = parts[0]
    if top not in TREE_EXTENSIONS:
        return False
    native_audio = top == "Tools" and len(parts) > 2 and parts[1] == "native_audio"
    if native_audio and any(part.casefold() in NATIVE_AUDIO_IGNORED_DIRS for part in parts[2:-1]):
        return False
    native_source = native_audio and (path.suffix.casefold() in NATIVE_AUDIO_SOURCE_EXTENSIONS or name in NATIVE_AUDIO_LICENSE_NAMES)
    if path.suffix.casefold() not in TREE_EXTENSIONS[top] and not native_source:
        return False
    if top == "Server":
        if len(parts) > 2 and parts[1].casefold().startswith(("online-client-kit-", "online-setup-")):
            return False
        if len(parts) > 2 and parts[1] in {"logs", "certificates"}:
            return path.name in {"README.md", "README.txt"} and len(parts) == 3
        if len(parts) > 2 and parts[1] == "data":
            return len(parts) == 3 and parts[2] in SOURCE_DATA_FILES
    if top == "Build" and path.suffix.casefold() == ".ini":
        return path.as_posix() in {
            "Build/config_templates/Client/config.ini", "Build/config_templates/Server/config.ini"
        }
    return True


def iter_source_files(root: Path) -> Iterator[Path]:
    """Reject links/reparse points instead of leaking content outside the source."""
    for current, directories, filenames in os.walk(root, followlinks=False):
        here = Path(current)
        kept = []
        for name in sorted(directories):
            path = here / name
            if name.casefold() in IGNORED_DIRS:
                continue
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise BuildError(f"Source contains a linked directory: {path.relative_to(root)}")
            if here == root and name not in TREE_EXTENSIONS:
                continue
            kept.append(name)
        directories[:] = kept
        for name in sorted(filenames):
            path = here / name
            if not is_source_file(path.relative_to(root)):
                continue
            if path.is_symlink():
                raise BuildError(f"Source contains a linked file: {path.relative_to(root)}")
            yield path


def validate_templates(root: Path) -> None:
    server = configparser.ConfigParser(interpolation=None)
    path = root / "Build/config_templates/Server/config.ini"
    if not server.read(path, encoding="utf-8"):
        raise BuildError("The clean server configuration template is missing.")
    if server.get("database", "password", fallback="") != "CHANGE_ME_WITH_SETUP":
        raise BuildError("Build/config_templates/Server/config.ini must keep password = CHANGE_ME_WITH_SETUP; never put a real credential in a release template.")
    if server.get("database", "backend", fallback="") != "mysql":
        raise BuildError("The release configuration must default to MySQL, not a developer database.")
    client = configparser.ConfigParser(interpolation=None)
    if not client.read(root / "Build/config_templates/Client/config.ini", encoding="utf-8"):
        raise BuildError("The clean client configuration template is missing.")
    if any(section.casefold() in {"database", "credentials", "passwords"} for section in client.sections()):
        raise BuildError("The client template must not contain database/credential sections.")
    if client.get("launcher", "edge_path", fallback=""):
        raise BuildError("Keep edge_path empty in the release template; configure private installations separately.")


def snapshot_source(root: Path, destination: Path) -> int:
    validate_templates(root)
    for relative in REQUIRED_SOURCE:
        if not (root / relative).is_file():
            raise BuildError(f"Incomplete source package: {relative} is missing. Extract the entire ZIP first.")
    count = 0
    for path in iter_source_files(root):
        relative = path.relative_to(root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        count += 1
    for component in ("Client", "Server"):
        shutil.copy2(root / "Build/config_templates" / component / "config.ini", destination / component / "config.ini")
    return count + 2


@contextlib.contextmanager
def build_lock(path: Path) -> Iterator[None]:
    """OS-owned lock releases even after a crash; the small lock file may remain."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise BuildError("Another build is already using this source folder. Close the other build before retrying.") from exc
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def run(command: Sequence[str | Path], *, cwd: Path, log: Log,
        env: Mapping[str, str] | None = None, timeout: int = 600,
        stdin: str | None = None) -> str:
    """No shell interpretation. Stream output and stop a hung step with an error."""
    cmd = [str(value) for value in command]
    log.say("\n> " + subprocess.list2cmdline(cmd))
    process = subprocess.Popen(
        cmd, cwd=cwd, env=dict(env) if env is not None else None,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    timed_out = threading.Event()

    def stop() -> None:
        if process.poll() is None:
            timed_out.set()
            process.kill()

    timer = threading.Timer(timeout, stop)
    timer.daemon = True
    timer.start()
    output: list[str] = []
    try:
        if stdin is not None and process.stdin is not None:
            process.stdin.write(stdin)
            process.stdin.close()
        assert process.stdout is not None
        for line in process.stdout:
            output.append(line)
            log.say(line.rstrip("\r\n"))
        code = process.wait()
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        timer.cancel()
        if process.stdout:
            process.stdout.close()
    if timed_out.is_set():
        raise BuildError(f"Build step exceeded its {timeout}-second execution limit. See {log.path}")
    if code:
        raise BuildError(f"Build step exited with code {code}: {Path(cmd[0]).name}. See the preceding error and {log.path}")
    return "".join(output)


def find_go() -> Path:
    override = os.environ.get("NXT_GO")
    candidates: list[str | Path | None] = [override, shutil.which("go")]
    if os.name == "nt":
        for key in ("ProgramFiles", "LOCALAPPDATA"):
            value = os.environ.get(key)
            if value:
                candidates.extend([Path(value) / "Go/bin/go.exe", Path(value) / "Programs/Go/bin/go.exe"])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
        if override:
            raise BuildError("NXT_GO must contain the full path to an existing go.exe, without surrounding quotes.")
    raise BuildError("Go was not found. On Windows, double-click the root BUILD_ALL.bat: it downloads and installs missing Go and Python automatically. Direct build.py invocation on a development host requires a local compiler or NXT_GO.")


def go_environment(cache: Path, target: str | None = None, arch: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("GOOS", "GOARCH", "GOFLAGS", "GOWORK", "GOROOT", "GOEXPERIMENT"):
        env.pop(key, None)
    env.update({"GOENV": "off", "GOTOOLCHAIN": "local", "CGO_ENABLED": "0",
                "GOWORK": "off", "GOCACHE": str(cache / "go-cache"),
                "GOPATH": str(cache / "go-path"), "GOFLAGS": ""})
    if target:
        env["GOOS"] = target
    if arch:
        env["GOARCH"] = arch
    return env


def build_venv_healthy(executable: Path, root: Path) -> bool:
    """Probe an old/moved build venv before reusing it; never touch Server/.venv."""
    if not executable.is_file():
        return False
    expected = list(sys.version_info[:2])
    code = ("import json,sys,struct,pip,ssl; "
            "print(json.dumps({'version':list(sys.version_info[:2]),"
            "'bits':struct.calcsize('P')*8}))")
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    try:
        result = subprocess.run([str(executable), "-I", "-c", code], cwd=root,
                                env=env, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False
        details = json.loads(result.stdout.strip())
        return details.get("version") == expected and details.get("bits") == 64
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def ensure_python(args: argparse.Namespace, root: Path, cache: Path, log: Log) -> Path:
    if args.existing_environment:
        log.say("DEVELOPMENT OVERRIDE: using current Python packages, not installing or asserting production dependency pins. This is recorded in BUILD_INFO.json.")
        return Path(sys.executable)
    environment = cache / "venv"
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if environment.is_symlink() or getattr(environment, "is_junction", lambda: False)():
        raise BuildError("The build venv must not be a linked directory; refusing to alter an external environment.")
    if not build_venv_healthy(executable, root):
        if args.no_install:
            raise BuildError("The build virtual environment is missing or unusable. Run BUILD_ALL.bat normally online to create/repair it automatically.")
        if environment.exists():
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
            backup = cache / ("venv.previous-" + stamp)
            environment.rename(backup)
            log.say(f"Preserved an unusable/outdated build environment at {backup.name}; creating a clean one. Server/.venv is not changed.")
        run([sys.executable, "-m", "venv", environment], cwd=root, log=log)
        if not build_venv_healthy(executable, root):
            raise BuildError("The new isolated build environment could not start with pip/SSL. See the venv error above.")
    if not args.no_install:
        try:
            run([executable, "-m", "pip", "--isolated", "--disable-pip-version-check", "install",
                 "--index-url", "https://pypi.org/simple", "--only-binary=:all:",
                 "--retries", "3", "--timeout", "60", "-r", root / "Server/requirements.txt"],
                cwd=root, log=log, timeout=900)
        except BuildError as exc:
            raise BuildError("Dependency installation failed; no release was published. Check the visible pip error and access to pypi.org/files.pythonhosted.org, then rerun BUILD_ALL.bat. It retries verified tool downloads and repairs a broken build venv automatically. Exact project dependency pins are never silently downgraded.") from exc
    run([executable, "-m", "pip", "--isolated", "--disable-pip-version-check", "check"], cwd=root, log=log)
    check = (
        "import importlib.metadata as m,re,pathlib; "
        "lines=pathlib.Path('Server/requirements.txt').read_text().splitlines(); "
        "pins=[re.fullmatch(r'([A-Za-z0-9_.-]+)(?:\\[[^\\]]+\\])?==([^ ;]+)',v.strip()) "
        "for v in lines if v.strip() and not v.lstrip().startswith('#')]; "
        "assert all(pins),'Only exact top-level requirement pins are supported'; "
        "assert all(m.version(p[1])==p[2] for p in pins),'Installed packages do not match requirements.txt'; "
        "import aiohttp,pymysql,cryptography; print('Pinned server dependencies verified')"
    )
    run([executable, "-c", check], cwd=root, log=log)
    return executable


def inspect_pe(path: Path, subsystem: int) -> dict[str, object]:
    """Inspect the generated file, never mistake a host binary for Windows x64."""
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise BuildError(f"Not a Windows executable: {path.name}")
        offset = struct.unpack_from("<I", header, 60)[0]
        stream.seek(offset)
        pe = stream.read(24 + 70)
    if len(pe) < 94 or pe[:4] != b"PE\0\0":
        raise BuildError(f"Invalid PE header: {path.name}")
    machine = struct.unpack_from("<H", pe, 4)[0]
    magic = struct.unpack_from("<H", pe, 24)[0]
    actual = struct.unpack_from("<H", pe, 24 + 68)[0]
    if machine != 0x8664 or magic != 0x20B or actual != subsystem:
        raise BuildError(f"Wrong executable architecture/subsystem: {path.name}")
    return {"file": path.name, "architecture": "Windows x64", "subsystem": actual,
            "bytes": path.stat().st_size, "sha256": sha256(path)}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def remove_test_outputs(package: Path) -> None:
    for path in list(package.rglob("__pycache__")):
        if path.is_dir():
            shutil.rmtree(path)
    for path in package.rglob("*.pyc"):
        path.unlink()
    (package / "Tests/launcher_results.json").unlink(missing_ok=True)


def write_manifest(root: Path, filename: str = "SHA256SUMS.txt") -> None:
    paths = sorted(p for p in root.rglob("*") if p.is_file() and p != root / filename)
    (root / filename).write_text("".join(f"{sha256(path)}  {path.relative_to(root).as_posix()}\n" for path in paths), encoding="utf-8", newline="\n")


def archive_tree(source: Path, destination: Path, prefix: str) -> int:
    paths = sorted(path for path in source.rglob("*") if path.is_file())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in paths:
            archive.write(path, (PurePosixPath(prefix) / path.relative_to(source).as_posix()).as_posix())
    with zipfile.ZipFile(destination) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise BuildError(f"ZIP integrity failed: {destination.name}: {corrupt}")
        if len(archive.infolist()) != len(paths):
            raise BuildError("ZIP entry count mismatch")
    return len(paths)


def atomic_text(path: Path, value: str) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def build(args: argparse.Namespace, root: Path, cache: Path, log: Log, build_id: str) -> Path:
    if sys.version_info < (3, 11) or struct.calcsize("P") != 8:
        raise BuildError("Use 64-bit Python 3.11 or newer; Python 3.13 x64 is recommended.")
    if sys.platform not in {"win32", "linux"}:
        raise BuildError("This build workflow supports Windows x64 and Linux cross-build verification only.")
    log.say(f"Pokemon NXT MMO | source build tools {BUILD_TOOL_VERSION}")
    log.say(f"Host: {platform.system()} {platform.machine()} | Python {platform.python_version()}")
    log.say("The source and existing deployments will not be overwritten. MySQL setup is NOT run by this build.")
    go = find_go()
    host_env = go_environment(cache)
    go_version = run([go, "version"], cwd=root, log=log, env=host_env).strip()
    match = re.search(r"\bgo(\d+)\.(\d+)", go_version)
    if not match or tuple(map(int, match.groups())) < (1, 23):
        raise BuildError("Go 1.23 or newer is required; install a current supported stable toolchain.")
    if shutil.disk_usage(root).free < 1024 ** 3:
        raise BuildError("Less than 1 GiB of free space is available. Free disk space before building.")
    python = ensure_python(args, root, cache, log)
    dependencies = run([python, "-c", "import importlib.metadata as m,json,sys; names=['aiohttp','PyMySQL','cryptography']; d={};\nfor n in names:\n try:d[n]=m.version(n)\n except m.PackageNotFoundError:d[n]=None\nprint(json.dumps({'python':sys.version,'packages':d}))"], cwd=root, log=log)
    package_info = json.loads(dependencies.strip())
    env = os.environ.copy()
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
    env.pop("PYTHONPATH", None)
    # Tests use the staged clean config, never a configured live password override.
    env.pop("POKEMON_NXT_DB_PASSWORD", None)
    workspace = Path(tempfile.mkdtemp(prefix="work-", dir=cache))
    stage = workspace / "source"
    stage.mkdir()
    started = time.monotonic()
    try:
        log.say("\n[1/7] Snapshot editable source with clean release configs")
        count = snapshot_source(root, stage)
        log.say(f"Staged {count:,} source/content files. Live configs, saves, TLS files and logs excluded.")
        log.say("\n[2/7] Verify extracted audio and publish a matching native content pack")
        log.say("Audio is supplied ready to play; this build needs no ROM, native audio compiler or FFmpeg.")
        run([python, stage / "Tools/repack_content.py", "--root", stage], cwd=stage, log=log, env=env)
        world = json.loads((stage / "Server/data/world.json").read_text(encoding="utf-8"))
        version = str(world["version"])
        if not re.fullmatch(r"[0-9A-Za-z._-]+", version):
            raise BuildError("Unsafe content version for release filenames")
        log.say("\n[3/7] Python syntax and regression / real-network tests")
        syntax_count = 0
        for path in stage.rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            syntax_count += 1
        log.say(f"Python syntax passed for {syntax_count} files.")
        tests = run([python, "-m", "unittest", "discover", "-s", "Tests", "-v"], cwd=stage, log=log, env=env, timeout=600)
        test_count_match = re.search(r"Ran (\d+) tests?", tests)
        test_count = int(test_count_match[1]) if test_count_match else None
        skipped_match = re.search(r"OK \(skipped=(\d+)\)", tests)
        skipped_count = int(skipped_match[1]) if skipped_match else 0
        passed_count = test_count - skipped_count if test_count is not None else None
        log.say("\n[4/7] Go tests, Windows static checks, and Windows x64 compilation")
        target_env = go_environment(cache, "windows", "amd64")
        for name in ("Client", "Server"):
            directory = stage / name / "launcher"
            run([go, "test", "-count=1", "-v", "./..."], cwd=directory, log=log, env=host_env)
            run([go, "vet", "./..."], cwd=directory, log=log, env=target_env)
        for name, executable, linker in (
            ("Client", "Pokemon NXT MMO.exe", "-s -w -H=windowsgui"),
            ("Server", "Pokemon NXT World Server.exe", "-s -w"),
        ):
            run([go, "build", "-trimpath", "-buildvcs=false", "-mod=readonly", f"-ldflags={linker}",
                 "-o", stage / name / executable, "."], cwd=stage / name / "launcher", log=log, env=target_env)
        binaries = [inspect_pe(stage / "Client/Pokemon NXT MMO.exe", 2), inspect_pe(stage / "Server/Pokemon NXT World Server.exe", 3)]
        log.say("Both outputs verified: Windows x64; client GUI subsystem; server console subsystem.")
        log.say("\n[5/7] Headless launcher HTTP smoke test and optional JavaScript syntax")
        if os.name == "nt":
            native_launcher = stage / "Client/Pokemon NXT MMO.exe"
            launcher_platform = "native Windows headless shell (not an Edge UI launch)"
        else:
            native_launcher = workspace / "client-shell-linux"
            run([go, "build", "-trimpath", "-buildvcs=false", "-o", native_launcher, "."], cwd=stage / "Client/launcher", log=log, env=host_env)
            launcher_platform = "Linux headless shell; Windows outputs cross-compiled, not executed"
        smoke_path = workspace / "launcher-smoke.json"
        run([python, "Build/smoke_launcher.py", "--exe", native_launcher, "--client-root", stage / "Client", "--output", smoke_path], cwd=stage, log=log, env=env, timeout=90)
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        node = shutil.which("node")
        if node:
            for js in sorted(path for path in (stage / "Client/app").rglob("*") if path.suffix in {".js", ".mjs"}):
                run([node, "--check", "--input-type=module"], cwd=stage, log=log, stdin=js.read_text(encoding="utf-8"))
            audio_test = stage / "Tests/check_audio_engine.mjs"
            if audio_test.is_file():
                run([node, audio_test], cwd=stage, log=log)
                audio_engine = "passed with installed Node.js"
            else:
                audio_engine = "not run: optional audio engine test is absent"
            audio_app_test = stage / "Tests/check_audio_app_integration.mjs"
            if audio_app_test.is_file():
                run([node, "--test", audio_app_test], cwd=stage, log=log)
                audio_app_integration = "passed with installed Node.js"
            else:
                audio_app_integration = "not run: optional audio app integration test is absent"
            run([node, "--test", stage / "Tests/check_registration.mjs", stage / "Tests/check_renderer_replication.mjs", stage / "Tests/check_adventure_ui.mjs", stage / "Tests/check_learnsets.mjs", stage / "Tests/check_battle_fx.mjs", stage / "Tests/check_varieties.mjs"], cwd=stage, log=log)
            replication_client = "passed with installed Node.js"
            javascript = "passed with installed Node.js"
        else:
            replication_client = "not run: optional Node.js is not installed"
            javascript = "not run: optional Node.js is not installed"
            audio_engine = "not run: optional Node.js is not installed"
            audio_app_integration = "not run: optional Node.js is not installed"
            log.say("Node.js is optional and was not found. JavaScript syntax check explicitly skipped; UI files are copied unchanged.")
        remove_test_outputs(stage)
        info = {
            "game": "Pokemon NXT MMO", "version": version, "build_tools": BUILD_TOOL_VERSION,
            "build_id": build_id, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "target": "windows/amd64", "build_host": {"system": platform.system(), "machine": platform.machine()},
            "go": go_version, "python_environment": package_info,
            "production_dependency_pins_enforced": not args.existing_environment,
            "content_pack": world["pack"], "asset_digest": world["assetDigest"],
            "audio": world["audio"], "world_startup_fix": "1.1.2",
            "checks": {"python_tests_run": test_count, "python_tests_passed": passed_count, "python_tests_skipped": skipped_count, "go_tests": "passed", "windows_go_vet": "passed",
                       "launcher_platform": launcher_platform, "http_smoke": smoke, "javascript_syntax": javascript,
                       "extracted_audio": "verified before content publication", "audio_engine": audio_engine, "audio_app_integration": audio_app_integration, "registration_and_replication_client": replication_client},
            "executables": binaries,
            "not_verified_by_this_build": ["Native Edge app UI", "MySQL/MariaDB runtime and persistence", "TLS deployment", "1,000 concurrent network sessions"],
            "configuration_policy": "Release templates only. Deployed Client/config.ini and Server/config.ini are not copied.",
        }
        write_json(stage / "BUILD_INFO.json", info)
        log.say("\n[6/7] Checksums and client / server / complete release ZIPs")
        write_manifest(stage)
        packages = workspace / "Packages"
        base = f"Pokemon_NXT_MMO_v{version}"
        for subtree, filename, prefix in (
            (stage / "Client", base + "_Client_Windows_x64.zip", "Client"),
            (stage / "Server", base + "_Server_Windows_x64.zip", "Server"),
            (stage, base + "_Complete.zip", f"Pokemon_NXT_MMO_{version}"),
        ):
            zip_count = archive_tree(subtree, packages / filename, prefix)
            log.say(f"Verified {filename}: {zip_count:,} files, {(packages/filename).stat().st_size/1024**2:.1f} MiB")
        write_manifest(packages)
        shutil.move(str(packages), str(stage / "Packages"))
        log.say("\n[7/7] Publish a new output folder without overwriting earlier builds")
        distribution = root / "dist"
        distribution.mkdir(exist_ok=True)
        final = distribution / build_id
        if final.exists():
            raise BuildError("The output path already exists; nothing was overwritten. Run the build again.")
        # Rename on the same volume publishes only a completed, verified package.
        stage.rename(final)
        atomic_text(distribution / "LATEST_BUILD.txt", build_id + "\n")
        log.say(f"\nBUILD SUCCEEDED ({time.monotonic()-started:.1f}s after staging began)")
        log.say(f"Client:   {final / 'Client'}")
        log.say(f"Server:   {final / 'Server'}")
        log.say(f"ZIPs:     {final / 'Packages'}")
        log.say(f"Evidence: {final / 'BUILD_INFO.json'}")
        log.say(f"Log:      {log.path}")
        log.say("Building does not configure or start MySQL. Follow Docs/QUICK_START.md inside the new output folder.")
        if os.name == "nt" and not args.no_open:
            try:
                os.startfile(final)
            except OSError as exc:
                log.say(f"Could not open Explorer automatically: {exc}")
        return final
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Source folder; normally auto-detected")
    parser.add_argument("--no-install", action="store_true", help="Reuse the build venv offline; exact dependency pins must already be installed")
    parser.add_argument("--existing-environment", action="store_true", help="Developer verification only: use current Python packages without asserting production pins; records this limitation")
    parser.add_argument("--no-open", action="store_true", help="Do not open Explorer on success")
    args = parser.parse_args(argv)
    if args.no_install and args.existing_environment:
        parser.error("--no-install and --existing-environment are mutually exclusive")
    root = args.root.resolve()
    cache = root / ".build"
    log: Log | None = None
    try:
        cache.mkdir(exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
        build_id = "build-" + stamp
        log = Log(cache / "logs" / (build_id + ".log"))
        with build_lock(cache / "build.lock"):
            build(args, root, cache, log, build_id)
        return 0
    except KeyboardInterrupt:
        if log:
            log.say("\nBUILD CANCELLED. No incomplete release was published.")
        return 130
    except (BuildError, OSError, ValueError, SyntaxError) as exc:
        message = "\nBUILD FAILED: " + str(exc)
        if log:
            log.say(message)
        else:
            print(message, file=sys.stderr)
        return 1
    except Exception:
        if log:
            log.say("\nUnexpected build failure:\n" + traceback.format_exc())
        else:
            traceback.print_exc()
        return 1
    finally:
        if log:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
