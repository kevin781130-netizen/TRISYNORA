#!/usr/bin/env python3
"""Cold DSH Host restart -> persisted Session -> resumed MCP history on wire.

Keyless, loopback-only, CI sandbox. No real model credentials or native repos.
Do not print process stdout/stderr, profile contents or bearer URLs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer

from smoke_agent_loop import _tool_result_received, TARGET_TOOL
from smoke_browser_chat import (
    BrowserProvider, HERE, _authenticated_url, _free_port,
)

FIRST_PROMPT = (
    "Use the TRISYNORA read-only capability list tool once. "
    "Report its catalog status."
)
SECOND_PROMPT = "TRISYNORA_HOST_RESTART_SECOND"
MODEL_ID = "deepseek-v4-pro"
START_TIMEOUT = 110


def _start_host(dsh: str, env: dict, root: Path, patch: Path, stage: int, port: int):
    private_log = root / f"private-host-{stage}.log"
    with private_log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            [dsh, "--profile", "web", "--patch", str(patch),
             "--no-open", "--host", "127.0.0.1", "--port", str(port)],
            cwd=root / "work", env=env, stdin=subprocess.DEVNULL,
            stdout=stream, stderr=subprocess.STDOUT,
        )
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return process, None
        url = _authenticated_url(private_log, port)
        if url:
            return process, url
        time.sleep(0.3)
    return process, None


def _stop_host(process: subprocess.Popen) -> bool:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    return process.poll() is not None


def _port_closed(port: int) -> bool:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        with socket.socket() as s:
            s.settimeout(0.4)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.2)
    return False


def _browser_run(path: str, env: dict, root: Path) -> dict:
    try:
        process = subprocess.run(
            ["node", path], cwd=root / "work", env=env,
            capture_output=True, text=True, timeout=165, check=False,
        )
        payload = json.loads(process.stdout.strip().splitlines()[-1])
        if not isinstance(payload, dict):
            return {"ok": False, "stage": "invalid-browser-report"}
        payload["ok"] = process.returncode == 0 and payload.get("ok") is True
        return payload
    except (subprocess.TimeoutExpired, ValueError, OSError, IndexError):
        return {"ok": False, "stage": "browser-execution-or-report"}


def _wire_model_is_correct(requests: list[dict]) -> bool:
    return bool(requests) and all(r.get("model") == MODEL_ID for r in requests)


def _old_session_on_wire(requests: list[dict]) -> bool:
    # One actual post-restart request must contain the user's ORIGINAL
    # message, SECOND message and the historical MCP tool result. Neither
    # a screenshot nor a browser-only cached transcript is sufficient.
    for r in requests:
        messages = json.dumps(r.get("messages", []), ensure_ascii=False)
        if all(marker in messages for marker in (
            FIRST_PROMPT, SECOND_PROMPT, TARGET_TOOL, "catalog-only",
            "nativeWriteToolsExposed",
        )):
            return True
    return False


def run() -> dict:
    dsh = os.environ.get("DSH_CLI", "")
    scratch = os.environ.get("RUNNER_TEMP", "")
    seed_script = os.environ.get("TRISYNORA_BROWSER_SCRIPT", "")
    resume_script = os.environ.get("TRISYNORA_BROWSER_RESTART_SCRIPT", "")
    for p in (dsh, seed_script, resume_script):
        if not p or not Path(p).is_file():
            raise RuntimeError("pinned isolated runtime scripts required")
    if not scratch or not Path(scratch).is_dir():
        raise RuntimeError("runner disposable directory required")

    BrowserProvider.requests = []
    BrowserProvider.error = None
    with tempfile.TemporaryDirectory(
        prefix="trisynora-host-cold-restart-", dir=scratch,
    ) as tmp:
        root = Path(tmp)
        for name in ("work", "home", "dsh-home", "exchange"):
            (root / name).mkdir()
        (root / "exchange" / ".trisynora-exchange-root.json").write_text(
            json.dumps({
                "format": "trisynora.external-exchange-root/v1",
                "kind": "read-only-staging",
            }), encoding="utf-8",
        )
        overlay = root / "web.patch.yml"
        overlay.write_text(
            (HERE / "dsh.patch.yml").read_text(encoding="utf-8")
            .replace("/opt/trisynora/readonly_mcp.py",
                     str(HERE / "readonly_mcp.py"))
            .replace("/exchange", str(root / "exchange")),
            encoding="utf-8",
        )
        provider = ThreadingHTTPServer(("127.0.0.1", 0), BrowserProvider)
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(root / "home"),
            "DSH_HOME": str(root / "dsh-home"),
            "DEEPSEEK_BASE_URL": (
                f"http://127.0.0.1:{provider.server_port}/v1"
            ),
            "DEEPSEEK_API_KEY": "mock-local-no-real-key",
            "DSH_PERMISSION_MODE": "read-only",
            "DSH_TELEMETRY_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "CI": "true",
            "LANG": "C.UTF-8",
            "PLAYWRIGHT_BROWSERS_PATH": os.environ.get(
                "PLAYWRIGHT_BROWSERS_PATH", ""),
        }
        first = None
        second = None
        try:
            first_port = _free_port()
            first, first_url = _start_host(
                dsh, env, root, overlay, 1, first_port,
            )
            if not first_url:
                return {"status": "not-verified", "stage": "first-host-start"}
            first_env = dict(env)
            first_env.update({
                "DSH_AUTH_URL": first_url,
                "TRISYNORA_BROWSER_WORKSPACE": str(root / "work"),
                "TRISYNORA_MODEL_SWITCH_EXPECT": MODEL_ID,
            })
            first_report = _browser_run(seed_script, first_env, root)
            before = list(BrowserProvider.requests)
            seed_valid = (
                first_report.get("ok") is True
                and first_report.get("browserModelPickerSelected") is True
                and first_report.get("submitted") is True
                and _tool_result_received([{}] + before)
                and _wire_model_is_correct(before)
                and BrowserProvider.error is None
            )
            if not seed_valid:
                return {
                    "status": "not-verified",
                    "stage": "original-session-and-mcp",
                    "browserStage": first_report.get("stage", "unknown"),
                    "firstProviderRequests": len(before),
                }

            old_pid = first.pid
            host_stopped = _stop_host(first)
            old_port_released = _port_closed(first_port)
            first = None
            if not host_stopped or not old_port_released:
                return {
                    "status": "not-verified",
                    "stage": "first-host-process-not-released",
                }

            next_port = _free_port()
            while next_port == first_port:
                next_port = _free_port()
            second, second_url = _start_host(
                dsh, env, root, overlay, 2, next_port,
            )
            if not second_url:
                return {"status": "not-verified", "stage": "second-host-start"}
            new_process = (
                second.pid != old_pid and second.poll() is None
                and next_port != first_port
            )
            second_env = dict(env)
            second_env.update({
                "DSH_AUTH_URL": second_url,
                "TRISYNORA_BROWSER_WORKSPACE": str(root / "work"),
            })
            resume_report = _browser_run(resume_script, second_env, root)
            after = list(BrowserProvider.requests[len(before):])
            restored = _old_session_on_wire(after)
            model_ok = _wire_model_is_correct(before + after)
            valid = all((
                host_stopped, old_port_released, new_process,
                resume_report.get("ok") is True,
                resume_report.get("authenticatedAfterHostRestart") is True,
                resume_report.get("originalMcpTranscriptRecovered") is True,
                resume_report.get("continuationSubmitted") is True,
                resume_report.get("continuationRendered") is True,
                restored, model_ok, BrowserProvider.error is None,
            ))
            return {
                "status": "host-cold-restart-session-mcp-pass"
                    if valid else "not-verified",
                "stage": "complete" if valid else resume_report.get(
                    "stage", "unknown"),
                "browserDiagnostics": resume_report.get("diagnostics", {}),
                "firstHostFullyStopped": host_stopped,
                "oldHostPortReleased": old_port_released,
                "newHostProcessVerified": new_process,
                "freshBrowserAuthenticatedAfterHostRestart":
                    resume_report.get("authenticatedAfterHostRestart", False),
                "historicMcpTranscriptRecovered":
                    resume_report.get("originalMcpTranscriptRecovered", False),
                "continuationSubmitted":
                    resume_report.get("continuationSubmitted", False),
                "continuationRendered":
                    resume_report.get("continuationRendered", False),
                "historicMcpContextOnNewHostWire": restored,
                "selectedModelPreservedOnNewHostWire": model_ok,
                "firstProviderRequests": len(before),
                "secondProviderRequests": len(after),
                "providerError": BrowserProvider.error,
                "nativeProductsMounted": False,
                "nativeProductsConnected": False,
                "nativeWriteAuthorized": False,
                "realModelCalled": False,
            }
        finally:
            if first is not None:
                _stop_host(first)
            if second is not None:
                _stop_host(second)
            provider.shutdown()
            provider.server_close()
            thread.join(timeout=5)


def main() -> int:
    try:
        report = run()
    except (RuntimeError, OSError, ValueError, TypeError):
        report = {
            "status": "not-verified", "stage": "runner-exception",
        }
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") == "host-cold-restart-session-mcp-pass" else 2


if __name__ == "__main__":
    sys.exit(main())
