#!/usr/bin/env python3
"""Bounded headless HTTP checks for the actual compiled client launcher.

Does not open Edge, connect to a world, or claim Windows UI acceptance.
Every subprocess is owned and terminated by this fixture.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import queue
import subprocess
import threading
import urllib.error
import urllib.request


def check(executable: Path, client: Path) -> dict[str, bool]:
    if not executable.is_file() or not (client / "config.ini").is_file():
        raise RuntimeError("Missing launcher or clean client config")
    process = subprocess.Popen(
        [str(executable.resolve()), "--root", str(client.resolve()), "--headless"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def read() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        try:
            first = lines.get(timeout=15)
        except queue.Empty as exc:
            raise RuntimeError("Launcher did not announce its loopback endpoint within 15 seconds") from exc
        if first is None or "app: http://127.0.0.1:" not in first:
            raise RuntimeError(f"Unexpected launcher startup: {first!r}")
        base = first.strip().split("app: ", 1)[1]
        # Ignore host proxy configuration for these exclusively loopback checks.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path: str, method: str = "GET", headers: dict[str, str] | None = None):
            req = urllib.request.Request(base + path, method=method, headers=headers or {})
            try:
                with opener.open(req, timeout=4) as response:
                    return response.status, dict(response.headers), response.read()
            except urllib.error.HTTPError as exc:
                with exc:
                    return exc.code, dict(exc.headers), exc.read()

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
        return results
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
    results = check(args.exe, args.client_root)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    failed = [name for name, passed in results.items() if not passed]
    if failed:
        raise SystemExit("Launcher checks failed: " + ", ".join(failed))
    print(f"{len(results)} headless HTTP checks passed.")


if __name__ == "__main__":
    main()
