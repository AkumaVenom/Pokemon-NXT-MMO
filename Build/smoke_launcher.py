#!/usr/bin/env python3
"""Bounded headless HTTP checks for the actual compiled client launcher.

Does not open Edge, connect to a world, or claim Windows UI acceptance.
Every subprocess is owned and terminated by this fixture.
"""
from __future__ import annotations

import argparse
from collections import deque
import http.client
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request


class LauncherSmokeError(RuntimeError):
    """A failed launcher check; transport errors never count as HTTP denial."""


def request_http(opener, base: str, path: str, method: str = "GET",
                 headers: dict[str, str] | None = None, data: dict | None = None):
    request_headers = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data, allow_nan=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    # urllib sends Connection: close. Keep that real Windows regression case:
    # handlers must consume bounded request bodies before their error response.
    req = urllib.request.Request(base + path, method=method, headers=request_headers, data=body)
    try:
        try:
            response = opener.open(req, timeout=4)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, dict(response.headers), response.read()
    except (OSError, http.client.HTTPException) as exc:
        route = path.partition("?")[0]
        raise LauncherSmokeError(
            f"No complete HTTP response for {method} {route}: {type(exc).__name__}: {exc}. "
            "A connection reset or timeout is a failed check, not an authorization result."
        ) from exc


def check(executable: Path, client: Path) -> dict[str, bool]:
    if not executable.is_file() or not (client / "config.ini").is_file():
        raise RuntimeError("Missing launcher or clean client config")
    # The build must neither read nor overwrite the builder's own audio choices.
    # Go's os.UserConfigDir uses APPDATA on Windows and XDG_CONFIG_HOME on Linux.
    with tempfile.TemporaryDirectory(prefix="NXT launcher audio smoke ") as directory:
        return _check(executable, client, Path(directory))


def _check(executable: Path, client: Path, settings_directory: Path) -> dict[str, bool]:
    environment = os.environ.copy()
    for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME"):
        environment[name] = str(settings_directory.resolve())
    process = subprocess.Popen(
        [str(executable.resolve()), "--root", str(client.resolve()), "--headless"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
        env=environment,
    )
    lines: queue.Queue[str | None] = queue.Queue()
    recent_output: deque[str] = deque(maxlen=20)
    output_lock = threading.Lock()

    def read() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                with output_lock:
                    recent_output.append(line.rstrip())
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 15
        startup = deque(maxlen=8)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Launcher did not announce its loopback endpoint within 15 seconds: " + "".join(startup))
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise RuntimeError("Launcher did not announce its loopback endpoint within 15 seconds: " + "".join(startup)) from exc
            if line is None:
                raise RuntimeError("Launcher exited before announcing its endpoint: " + "".join(startup))
            startup.append(line)
            match = re.search(r"app: (http://127\.0\.0\.1:\d+)\s*$", line)
            if match:
                base = match.group(1)
                break
        # Ignore host proxy configuration for these exclusively loopback checks.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path: str, method: str = "GET", headers: dict[str, str] | None = None,
                    data: dict | None = None):
            return request_http(opener, base, path, method, headers, data)

        results: dict[str, bool] = {}
        status, headers, body = request("/")
        results["index_served"] = status == 200 and b"Pokemon NXT" in body
        results["content_policy"] = headers.get("Content-Security-Policy", "").startswith("default-src 'self'")
        results["no_sniff"] = headers.get("X-Content-Type-Options") == "nosniff"
        results["frame_denial"] = headers.get("X-Frame-Options") == "DENY"
        status, _, body = request("/bootstrap")
        cfg = json.loads(body)
        results["bootstrap_no_secrets"] = status == 200 and cfg["endpoint"].startswith(("ws://", "wss://")) and not any(word in str(cfg).lower() for word in ("password", "mysql", "database"))
        results["unexpected_host_blocked"] = request("/", headers={"Host": "untrusted.example"})[0] == 403
        results["server_config_inaccessible"] = request("/Server/config.ini")[0] == 404
        results["directory_listing_disabled"] = request("/assets/maps")[0] == 404
        results["traversal_blocked"] = request("/%2e%2e/Server/config.ini")[0] == 404
        results["heartbeat_requires_origin_and_token"] = request("/heartbeat", method="POST")[0] == 403
        results["heartbeat_accepted"] = request("/heartbeat?token=" + cfg["nonce"], method="POST", headers={"Origin": base})[0] == 204
        results["js_served_as_module"] = request("/app.js")[0] == 200
        results["extracted_map_served"] = request("/assets/maps/kanto/3_0.png")[0] == 200
        status, headers, _ = request("/audio.js")
        results["audio_module_mime"] = status == 200 and headers.get("Content-Type", "").split(";", 1)[0] in {"text/javascript", "application/javascript"}
        status, headers, body = request("/assets/audio/catalog.json")
        catalog = json.loads(body)
        results["audio_catalog_served"] = status == 200 and headers.get("Content-Type", "").startswith("application/json") and catalog.get("format") == 1 and bool(catalog.get("clips"))
        for extension, expected_mime, result_name in ((".ogg", "audio/ogg", "ogg_audio_mime"), (".wav", "audio/wav", "wav_audio_mime")):
            clip = next((clip for clip in catalog["clips"].values() if clip["path"].endswith(extension)), None)
            if clip is None:
                results[result_name] = False
                continue
            status, headers, body = request("/assets/" + clip["path"])
            actual_mime = headers.get("Content-Type", "").split(";", 1)[0]
            permitted_mimes = {expected_mime} if extension == ".ogg" else {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}
            results[result_name] = status == 200 and actual_mime in permitted_mimes and body.startswith(b"OggS" if extension == ".ogg" else b"RIFF")
        expected_fields = {"master", "music", "effects", "cries", "muted", "muteUnfocused", "lowHp", "chat"}
        initial = cfg.get("audio", {})
        results["audio_bootstrap_preferences"] = set(initial) == expected_fields
        values = {"master": .27, "music": .31, "effects": .42, "cries": .53,
                  "muted": True, "muteUnfocused": False, "lowHp": False, "chat": False}
        endpoint = "/audio-settings?token=" + cfg["nonce"]
        results["audio_wrong_origin_blocked"] = request(endpoint, "POST", {"Origin": "https://untrusted.example"}, values)[0] == 403
        results["audio_missing_origin_blocked"] = request(endpoint, "POST", data=values)[0] == 403
        results["audio_wrong_nonce_blocked"] = request("/audio-settings?token=wrong", "POST", {"Origin": base}, values)[0] == 403
        results["audio_partial_settings_rejected"] = request(endpoint, "POST", {"Origin": base}, {"master": .5})[0] == 400
        results["audio_rejected_requests_leave_settings_unchanged"] = json.loads(request("/bootstrap")[2]).get("audio") == initial
        status, headers, body = request(endpoint, "POST", {"Origin": base}, values)
        saved = json.loads(body)
        results["audio_preferences_saved"] = status == 200 and saved.get("persisted") is True and saved.get("audio") == values and headers.get("Cache-Control") == "no-store"
        results["audio_bootstrap_readback"] = json.loads(request("/bootstrap")[2]).get("audio") == values
        preference_path = settings_directory / "PokemonNXT/audio_settings.json"
        results["audio_preferences_isolated_on_disk"] = preference_path.is_file() and json.loads(preference_path.read_text(encoding="utf-8")) == values
        return results
    except Exception as exc:
        with output_lock:
            output = "\n".join(recent_output)
        # The ephemeral launcher nonce is never needed for build diagnostics.
        output = re.sub(r"token=[^\s&]+", "token=<redacted>", output)
        state = process.poll()
        status = "still running" if state is None else f"exited with code {state}"
        raise LauncherSmokeError(
            f"{exc}\nLauncher was {status}. Recent launcher output:\n{output or '(no output)'}"
        ) from exc
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        reader.join(timeout=2)
        if process.stdout:
            process.stdout.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--client-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        results = check(args.exe, args.client_root)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        args.output.write_text(json.dumps({"passed": False, "error": str(exc)}, indent=2) + "\n", encoding="utf-8")
        raise SystemExit("Launcher checks failed: " + str(exc)) from exc
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    failed = [name for name, passed in results.items() if not passed]
    if failed:
        raise SystemExit("Launcher checks failed: " + ", ".join(failed))
    print(f"{len(results)} headless HTTP checks passed.")


if __name__ == "__main__":
    main()
