#!/usr/bin/env python3
"""One-shot isolated smoke of the REAL pinned DeepSeek Harness Web launcher.

Run ONLY on an ephemeral runner with no Vera/H3/PointFlux projects mounted.
No LLM API key; never sends a model request or grants native permissions.
Proof: actual profile parses MCP patch and Web listener starts, not a UI tool call.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
PORT_TIMEOUT = 65


def main() -> int:
    cli = Path(os.environ["DSH_CLI"]).resolve(strict=True)
    if not cli.is_file():
        raise RuntimeError("pinned DSH executable missing")
    runner = os.environ.get("RUNNER_TEMP")
    if not runner:
        raise RuntimeError("refuse running outside disposable CI runner")
    with tempfile.TemporaryDirectory(dir=runner, prefix="trisynora-dsh-web-") as dirname:
        isolated = Path(dirname)
        work = isolated / "empty-cwd"
        home = isolated / "dsh-home"
        stage = isolated / "exchange"
        for p in (work, home, stage):
            p.mkdir()
        (stage / ".trisynora-exchange-root.json").write_text(json.dumps({
            "format": "trisynora.external-exchange-root/v1",
            "kind": "read-only-staging",
        }), encoding="utf-8")
        patch = (ROOT / "dsh.patch.yml").read_text(encoding="utf-8")
        patch = patch.replace("/opt/trisynora/readonly_mcp.py", str(ROOT / "readonly_mcp.py"))
        patch = patch.replace("/exchange", str(stage))
        overlay = isolated / "dsh.patch.yml"
        overlay.write_text(patch, encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(isolated),
            "DSH_HOME": str(home),
            "DSH_PERMISSION_MODE": "read-only",
            "DSH_TELEMETRY_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "CI": "true",
            "LANG": "C.UTF-8",
        }
        command = [str(cli), "--profile", "web", "--patch", str(overlay)]
        config = subprocess.run(
            command + ["--dump-config"], cwd=work, env=env,
            capture_output=True, text=True, timeout=35, check=False,
        )
        if config.returncode or "trisynora-readonly-mcp" not in config.stdout:
            print(json.dumps({
                "status": "rejected",
                "stage": "actual-dsh-config-assembly",
                "exit": config.returncode,
                "patchMounted": "trisynora-readonly-mcp" in config.stdout,
            }))
            return 2

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        log = isolated / "web-start.log"
        with log.open("w+", encoding="utf-8") as stream:
            process = subprocess.Popen(
                command + ["--no-open", "--host", "127.0.0.1", "--port", str(port)],
                cwd=work, env=env, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                end = time.monotonic() + PORT_TIMEOUT
                started = False
                while time.monotonic() < end:
                    if process.poll() is not None:
                        break
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                            started = True
                            break
                    except OSError:
                        time.sleep(0.4)
                # Confirm an actual HTTP response from Web (auth is expected).
                http_ok = False
                if started:
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                            http_ok = 200 <= response.status < 500
                    except HTTPError as exc:
                        http_ok = exc.code in (301, 302, 401, 403, 404)
                    except (OSError, ValueError):
                        pass
                if not started or not http_ok:
                    stream.flush()
                    # Do not echo token-bearing startup logs into public CI.
                    print(json.dumps({
                        "status": "rejected",
                        "stage": "actual-dsh-web-listener",
                        "processExited": process.poll() is not None,
                        "tcpStarted": started,
                        "httpResponded": http_ok,
                    }))
                    return 2
                stream.flush()
                raw_log = log.read_text(encoding="utf-8", errors="replace")
                if re.search(r"mcp-client.*(?:failed|error)|trisynora-readonly-mcp.*failed", raw_log, re.I):
                    print(json.dumps({"status": "rejected", "stage": "mcp-plugin-runtime-error"}))
                    return 2
                print(json.dumps({
                    "status": "real-harness-web-startup-pass",
                    "profilePatchIncluded": True,
                    "webHttpResponded": True,
                    "nativeProductSourcesMounted": False,
                    "nativeProductsConnected": False,
                    "nativeWriteAuthorized": False,
                    "modelCallExecuted": False,
                    "inBrowserToolInvocationVerified": False,
                }, sort_keys=True))
                return 0
            finally:
                process.terminate()
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(json.dumps({"status": "not-verified", "stage": "startup", "errorType": type(exc).__name__}))
        sys.exit(2)
