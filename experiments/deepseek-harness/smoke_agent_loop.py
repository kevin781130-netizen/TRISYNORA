#!/usr/bin/env python3
"""Real DeepSeek Harness HEADLESS Agent Loop -> actual Cordis MCP plugin -> Python MCP.

A local scripted HTTP/SSE mock model forces a read-only capability call. The
second model request MUST contain the actual MCP tool result and thus proves
Agent Loop routing. No browser, real LLM credentials, native product, shared
database or writable mount of Vera/H3/PointFlux is involved.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

HERE = Path(__file__).resolve().parent
TARGET_TOOL = "mcp__trisynora__trisynora_list_capabilities"
MAX_BODY = 2 * 1024 * 1024


def _event(value: dict) -> bytes:
    text = json.dumps(value, separators=(",", ":"))
    return f"event: {value['type']}\ndata: {text}\n\n".encode("utf-8")


def _messages(seq: int) -> bytes:
    parts = [
        {"type": "message_start", "message": {
            "id": f"mock-msg-{seq}", "type": "message", "role": "assistant",
            "model": "mock-model", "content": [], "usage": {
                "input_tokens": 5, "output_tokens": 0}}},
    ]
    if seq == 1:
        parts.extend([
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "tool_use", "id": "mock-call-1",
                               "name": TARGET_TOOL, "input": {}}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "input_json_delta", "partial_json": "{}"}},
            {"type": "content_block_stop", "index": 0},
        ])
        reason = "tool_use"
    else:
        parts.extend([
            {"type": "content_block_start", "index": 0,
             "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "text_delta", "text": "TRISYNORA capability check done"}},
            {"type": "content_block_stop", "index": 0},
        ])
        reason = "end_turn"
    parts.extend([
        {"type": "message_delta",
         "delta": {"stop_reason": reason, "stop_sequence": None},
         "usage": {"output_tokens": 8}},
        {"type": "message_stop"},
    ])
    return b"".join(_event(x) for x in parts) + b"data: [DONE]\n\n"


class Handler(BaseHTTPRequestHandler):
    requests = []
    error = None

    def do_POST(self):
        if self.path not in ("/v1/messages", "/messages"):
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n < 1 or n > MAX_BODY:
                self.send_error(413)
                return
            body = json.loads(self.rfile.read(n))
            if not isinstance(body, dict):
                self.send_error(400)
                return
            self.__class__.requests.append(body)
            payload = _messages(len(self.__class__.requests))
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("cache-control", "no-cache")
            self.send_header("connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self.__class__.error = type(exc).__name__
            self.send_error(500)

    def log_message(self, *_args):
        return


def _tool_result_received(requests: list[dict]) -> bool:
    if len(requests) < 2:
        return False
    second = requests[1]
    # The real Messages format may use structured role=tool or user tool_result.
    def crawl(node):
        if isinstance(node, dict):
            if node.get("status") == "catalog-only" and node.get("nativeWriteToolsExposed") is False:
                return True
            return any(crawl(value) for value in node.values())
        if isinstance(node, list):
            return any(crawl(x) for x in node)
        if isinstance(node, str) and "catalog-only" in node and "nativeWriteToolsExposed" in node:
            return True
        return False
    return crawl(second.get("messages", []))


def run() -> dict:
    dsh = os.environ.get("DSH_CLI", "")
    if not dsh or not Path(dsh).is_file():
        raise RuntimeError("pinned official DSH launcher missing")
    scratch = os.environ.get("RUNNER_TEMP")
    if not scratch:
        raise RuntimeError("refuse execution outside disposable CI")
    Handler.requests = []
    Handler.error = None
    with tempfile.TemporaryDirectory(prefix="trisynora-agent-mock-", dir=scratch) as tmp:
        root = Path(tmp)
        for folder in ("work", "home", "dsh-home", "exchange"):
            (root / folder).mkdir()
        (root / "exchange" / ".trisynora-exchange-root.json").write_text(
            json.dumps({"format": "trisynora.external-exchange-root/v1",
                        "kind": "read-only-staging"}), encoding="utf-8")
        yml = (HERE / "dsh.patch.yml").read_text(encoding="utf-8")
        yml = yml.replace("/opt/trisynora/readonly_mcp.py", str(HERE / "readonly_mcp.py"))
        yml = yml.replace("/exchange", str(root / "exchange"))
        overlay = root / "agent.patch.yml"
        overlay.write_text(yml, encoding="utf-8")
        mock = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        mock.timeout = 15
        serving = threading.Thread(target=mock.serve_forever, daemon=True)
        serving.start()
        try:
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": str(root / "home"),
                "DSH_HOME": str(root / "dsh-home"),
                "DEEPSEEK_BASE_URL": f"http://127.0.0.1:{mock.server_port}/v1",
                "DEEPSEEK_API_KEY": "mock-local-key-no-real-auth",
                "DSH_PERMISSION_MODE": "read-only",
                "DSH_TELEMETRY_DISABLED": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "CI": "true",
                "LANG": "C.UTF-8",
            }
            command = [
                dsh, "--profile", "headless", "--patch", str(overlay),
                "Use the TRISYNORA read-only list capabilities tool once.",
            ]
            try:
                process = subprocess.run(command, capture_output=True, text=True,
                                         env=env, cwd=root / "work", timeout=75,
                                         check=False)
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                exit_code = -1
            return {
                "status": "headless-agent-mcp-pass"
                if exit_code == 0 and _tool_result_received(Handler.requests) else "not-verified",
                "headlessExitZero": exit_code == 0,
                "providerRequests": len(Handler.requests),
                "modelRequestedMcpTool": bool(Handler.requests) and
                    TARGET_TOOL in json.dumps(Handler.requests[0].get("tools", [])),
                "toolResultObservedInSecondModelRequest": _tool_result_received(Handler.requests),
                "mockProviderError": Handler.error,
                "nativeProductsConnected": False,
                "nativeWriteAuthorized": False,
                "realModelCalled": False,
                "browserSessionVerified": False,
            }
        finally:
            mock.shutdown()
            mock.server_close()
            serving.join(timeout=4)


def main() -> int:
    try:
        result = run()
    except (RuntimeError, OSError, ValueError) as exc:
        print(json.dumps({"status": "not-verified", "errorType": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "headless-agent-mcp-pass" else 2


if __name__ == "__main__":
    sys.exit(main())
