#!/usr/bin/env python3
"""Actual DSH Web + browser composer + Agent Loop + read-only TRISYNORA MCP.

CI-only, keyless loopback model. Never expose launch URLs/tokens in logs.
This is a browser test, not a native three-product integration test.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse

from smoke_agent_loop import _event, _tool_result_received, TARGET_TOOL, MAX_BODY

HERE = Path(__file__).resolve().parent
MARKER = "TRISYNORA_BROWSER_MCP_DONE"
TIMEOUT = 100


def _stream_response(body: dict, sequence: int) -> bytes:
    # Only claim completion when the incoming model request actually carries
    # the correct MCP tool_result AND the catalog-only payload.
    receipt = _tool_result_received([{}, body])
    tool_offered = TARGET_TOOL in json.dumps(body.get("tools", []))
    use_tool = not receipt and tool_offered
    if receipt:
        reply = MARKER + " catalog-only nativeWriteToolsExposed=false"
    else:
        reply = "TRISYNORA mock title" if not use_tool else ""
    blocks = [
        {"type": "message_start", "message": {
            "id": "web-mock-" + str(sequence), "type": "message",
            "role": "assistant", "model": "mock-model", "content": [],
            "usage": {"input_tokens": 5, "output_tokens": 0}}},
    ]
    if use_tool:
        blocks += [
            {"type": "content_block_start", "index": 0, "content_block": {
                "type": "tool_use", "id": "web-mcp-call-" + str(sequence),
                "name": TARGET_TOOL, "input": {}}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "input_json_delta", "partial_json": "{}"}},
        ]
    else:
        blocks += [
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": reply}},
        ]
    blocks += [
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {
            "stop_reason": "tool_use" if use_tool else "end_turn",
            "stop_sequence": None}, "usage": {"output_tokens": 12}},
        {"type": "message_stop"},
    ]
    return b"".join(_event(item) for item in blocks) + b"data: [DONE]\n\n"


class BrowserProvider(BaseHTTPRequestHandler):
    requests: list[dict] = []
    error: str | None = None

    def do_POST(self) -> None:
        if self.path not in ("/v1/messages", "/messages"):
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= MAX_BODY:
                self.send_error(413)
                return
            request = json.loads(self.rfile.read(n))
            if not isinstance(request, dict):
                self.send_error(400)
                return
            self.__class__.requests.append(request)
            payload = _stream_response(request, len(self.__class__.requests))
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
        except (ValueError, OSError) as exc:
            self.__class__.error = type(exc).__name__
            try:
                self.send_error(500)
            except OSError:
                pass

    def log_message(self, *_args) -> None:
        pass


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _authenticated_url(log: Path, port: int) -> str | None:
    # DSH logs may contain a process bearer credential. Never print the log
    # or the URL; only consume it in the disposable local browser.
    content = log.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"dsh web:\s*(https?://[^\s]+)", content)
    if not match:
        return None
    url = match.group(1).rstrip(".,")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port != port:
        raise RuntimeError("invalid authenticated loopback web authority")
    if not parsed.query and not parsed.fragment and not parsed.path.strip("/"):
        raise RuntimeError("web URL missing credential handoff path")
    return url


def run() -> dict:
    dsh = os.environ.get("DSH_CLI", "")
    scratch = os.environ.get("RUNNER_TEMP", "")
    playwright_script = os.environ.get("TRISYNORA_BROWSER_SCRIPT", "")
    if not dsh or not Path(dsh).is_file() or not scratch or not playwright_script:
        raise RuntimeError("disposable CI runtime is required")
    BrowserProvider.requests = []
    BrowserProvider.error = None
    with tempfile.TemporaryDirectory(prefix="trisynora-web-e2e-", dir=scratch) as tmp:
        root = Path(tmp)
        for name in ("work", "home", "dsh-home", "exchange"):
            (root / name).mkdir()
        (root / "exchange" / ".trisynora-exchange-root.json").write_text(
            json.dumps({"format": "trisynora.external-exchange-root/v1",
                        "kind": "read-only-staging"}), encoding="utf-8")
        patch = (HERE / "dsh.patch.yml").read_text(encoding="utf-8")
        patch = patch.replace("/opt/trisynora/readonly_mcp.py", str(HERE / "readonly_mcp.py"))
        patch = patch.replace("/exchange", str(root / "exchange"))
        overlay = root / "web.patch.yml"
        overlay.write_text(patch, encoding="utf-8")
        mock = ThreadingHTTPServer(("127.0.0.1", 0), BrowserProvider)
        thread = threading.Thread(target=mock.serve_forever, daemon=True)
        thread.start()
        port = _free_port()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(root / "home"),
            "DSH_HOME": str(root / "dsh-home"),
            "DEEPSEEK_BASE_URL": "http://127.0.0.1:" + str(mock.server_port) + "/v1",
            "DEEPSEEK_API_KEY": "mock-local-no-real-key",
            "DSH_PERMISSION_MODE": "read-only",
            "DSH_TELEMETRY_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "CI": "true",
            "LANG": "C.UTF-8",
            "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
        }
        log = root / "private-web.log"
        try:
            with log.open("w", encoding="utf-8") as out:
                process = subprocess.Popen(
                    [dsh, "--profile", "web", "--patch", str(overlay),
                     "--no-open", "--host", "127.0.0.1", "--port", str(port)],
                    cwd=root / "work", env=env, stdin=subprocess.DEVNULL,
                    stdout=out, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + TIMEOUT
                    url = None
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            break
                        url = _authenticated_url(log, port)
                        if url:
                            break
                        time.sleep(0.4)
                    if not url:
                        return {"status": "not-verified", "stage": "web-authenticated-startup"}
                    resume_mode = os.environ.get("TRISYNORA_SESSION_RESUME_EXPECT", "")
                    if resume_mode not in ("", "1"):
                        raise RuntimeError("session-resume mode must be explicitly allowlisted")
                    expected_model = os.environ.get("TRISYNORA_MODEL_SWITCH_EXPECT", "")
                    if expected_model not in ("", "deepseek-v4-pro"):
                        raise RuntimeError("model-switch allowlist violated")
                    browser_env = dict(env)
                    browser_env.update({
                        "DSH_AUTH_URL": url,
                        "TRISYNORA_BROWSER_WORKSPACE": str(root / "work"),
                        "TRISYNORA_MODEL_SWITCH_EXPECT": expected_model,
                        "TRISYNORA_SESSION_RESUME_EXPECT": resume_mode,
                    })
                    try:
                        browser = subprocess.run(
                            ["node", playwright_script], cwd=root / "work",
                            env=browser_env, text=True, capture_output=True,
                            timeout=135, check=False)
                        browser_report = json.loads(browser.stdout.strip().splitlines()[-1])
                    except (subprocess.TimeoutExpired, IndexError, json.JSONDecodeError):
                        browser_report = {"ok": False, "stage": "browser-timeout-or-report"}
                    evidence = _tool_result_received([{}] + BrowserProvider.requests)
                    offered = any(
                        TARGET_TOOL in json.dumps(req.get("tools", []))
                        for req in BrowserProvider.requests)
                    displayed = (browser.returncode == 0 if "browser" in locals() else False) and (
                        browser_report.get("ok") is True)
                    # Backend audit: the genuine provider requests, not the UI
                    # display or mock-model response, must use the selected ID.
                    wire_models = {
                        request.get("model", "")
                        for request in BrowserProvider.requests
                        if isinstance(request.get("model"), str)
                    }
                    model_ok = (
                        wire_models == {expected_model}
                        and browser_report.get("modelSwitchSelected") is True
                        if expected_model else True
                    )
                    # Continuation must contain both distinct user turns and
                    # the original MCP result in ONE later wire request;
                    # otherwise a fresh session or UI-only replay is a FAIL.
                    replay_receipt = any(
                        all(marker in json.dumps(req.get("messages", []))
                            for marker in (
                                "TRISYNORA_SESSION_HISTORY_FIRST",
                                "TRISYNORA_SESSION_HISTORY_SECOND",
                                "catalog-only",
                                TARGET_TOOL,
                            ))
                        for req in BrowserProvider.requests[3:]
                    )
                    resumed = (
                        browser_report.get("browserProcessExited") is True
                        and browser_report.get("historyRestoredInFreshBrowser") is True
                        and browser_report.get("continuationSubmitted") is True
                        and browser_report.get("continuationRendered") is True
                        and replay_receipt
                    ) if resume_mode else True
                    passed = (
                        displayed and evidence and offered
                        and not BrowserProvider.error and model_ok and resumed
                    )
                    return {
                        "status": (
                            "browser-session-resume-mcp-pass" if resume_mode
                            else "browser-model-switch-mcp-pass" if expected_model
                            else "browser-agent-mcp-pass"
                        ) if passed else "not-verified",
                        "stage": browser_report.get("stage", "unknown") if not passed else "complete",
                        "browserProcessExited": browser_report.get("browserProcessExited", False),
                        "historyRestoredInFreshBrowser": browser_report.get(
                            "historyRestoredInFreshBrowser", False),
                        "continuationSubmitted": browser_report.get(
                            "continuationSubmitted", False),
                        "continuationRendered": browser_report.get(
                            "continuationRendered", False),
                        "historicMcpContextPresentOnWire": replay_receipt if resume_mode else None,
                        "selectedModelVerified": model_ok if expected_model else None,
                        "selectedModelOnWire": expected_model if model_ok and expected_model else None,
                        "browserModelPickerSelected": browser_report.get("modelSwitchSelected", False),
                        "browserAuthenticatedChat": browser_report.get("authenticated", False),
                        "browserDiagnostics": browser_report.get("diagnostics", {}),
                        "browserSubmittedUserPrompt": browser_report.get("submitted", False),
                        "browserRenderedMcpResult": displayed,
                        "modelRequestedMcpTool": offered,
                        "toolResultObservedInLaterModelRequest": evidence,
                        "providerRequests": len(BrowserProvider.requests),
                        "providerError": BrowserProvider.error,
                        "nativeProductsMounted": False,
                        "nativeProductsConnected": False,
                        "nativeWriteAuthorized": False,
                        "realModelCalled": False,
                    }
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=12)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        finally:
            mock.shutdown()
            mock.server_close()
            thread.join(timeout=5)


def main() -> int:
    try:
        result = run()
    except (RuntimeError, OSError, ValueError) as exc:
        result = {"status": "not-verified", "stage": "runner",
                  "errorType": type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in (
        "browser-agent-mcp-pass", "browser-model-switch-mcp-pass",
        "browser-session-resume-mcp-pass",
    ) else 2


if __name__ == "__main__":
    sys.exit(main())
