#!/usr/bin/env python3
"""Inside locked-down Docker, probe real OS boundaries then run OFFICIAL DSH.

Host-only file/port are synthetic canaries. Never probe real credentials.
This does not prove adversarial Bash/FS tool invocation; it proves the exact
container security boundary that *would constrain* those built-in tools,
and executes genuine DSH Headless Agent→MCP inside the SAME container.
"""
from __future__ import annotations

import json
import re
import os
from pathlib import Path
import socket
import subprocess
import sys

sys.path.insert(0, "/opt/trisynora")
import smoke_agent_loop as agent

ABSENT_PATH = "/host-native/Vera/HOST_ONLY_SENTINEL.txt"
ABSENT_H3 = "/host-native/minimax-H3/HOST_ONLY_SENTINEL.txt"
ABSENT_PF = "/host-native/PointFlux/HOST_ONLY_SENTINEL.txt"
RO_PROBE = "/opt/trisynora/readonly-canary.txt"


def main() -> int:
    failures = []
    facts = {}
    def check(cond, name):
        facts[name] = bool(cond)
        if not cond:
            failures.append(name)

    check(os.geteuid() == 10001, "nonRootUid")
    check(os.path.isfile("/opt/dsh/node_modules/.bin/dsh"),
          "pinnedDshRuntimeVisible")
    check(os.path.isfile("/opt/trisynora/readonly_mcp.py"),
          "readOnlyBridgeVisible")
    check(os.environ.get("DSH_TELEMETRY_DISABLED") == "1",
          "telemetryDisabled")
    check(not any(k in os.environ for k in (
        "GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY", "AWS_SECRET_ACCESS_KEY",
    )), "noHostCredentialsInProcessEnv")

    check(all(not Path(p).exists() for p in (
        ABSENT_PATH, ABSENT_H3, ABSENT_PF,
    )), "nativeSyntheticHostFilesAbsent")
    check(not any(Path(p).exists() for p in (
        "/host-native", "/workspace/Vera", "/workspace/minimax-H3",
        "/workspace/PointFlux",
    )), "noNativeCheckoutMounts")
    check(Path(RO_PROBE).read_text(encoding="utf-8") ==
          "TRISYNORA_SANDBOX_READONLY_CANARY\n", "readOnlyFixturePresent")

    # Python FS API tries to read host-only canaries and modify a ro mount.
    fs_read_denied = True
    for p in (ABSENT_PATH, ABSENT_H3, ABSENT_PF):
        try:
            Path(p).read_bytes()
            fs_read_denied = False
        except (FileNotFoundError, PermissionError):
            pass
    check(fs_read_denied, "filesystemHostReadDenied")

    fs_write_denied = False
    try:
        with open(RO_PROBE, "a", encoding="utf-8") as f:
            f.write("FORBIDDEN_SANDBOX_WRITE\n")
    except (PermissionError, OSError):
        fs_write_denied = True
    check(fs_write_denied
          and Path(RO_PROBE).read_text(encoding="utf-8") ==
          "TRISYNORA_SANDBOX_READONLY_CANARY\n",
          "filesystemReadonlyMountWriteDenied")

    root_write_denied = False
    try:
        Path("/HOST_ESCAPE_SENTINEL").write_text("FORBIDDEN\n",
                                                 encoding="utf-8")
    except (PermissionError, OSError):
        root_write_denied = True
    check(root_write_denied and not Path("/HOST_ESCAPE_SENTINEL").exists(),
          "immutableRootFilesystem")

    # Real shell subprocess from same UID/ns: no host-only file, no ro writes.
    shell_cmd = (
        "test ! -e /host-native/Vera/HOST_ONLY_SENTINEL.txt && "
        "test ! -e /host-native/minimax-H3/HOST_ONLY_SENTINEL.txt && "
        "test ! -e /host-native/PointFlux/HOST_ONLY_SENTINEL.txt && "
        "test ! -w /opt/trisynora/readonly-canary.txt"
    )
    shell = subprocess.run(["bash", "-c", shell_cmd],
                           capture_output=True, timeout=8, check=False)
    check(shell.returncode == 0, "bashSubprocessHostAndWriteDenied")

    # /proc must show namespaced process 1 as the probe, not host runner PID 1.
    try:
        pid1 = Path("/proc/1/cmdline").read_bytes().lower()
        proc_ok = (b"container_sandbox_probe.py" in pid1
                   or b"python3" in pid1)
    except (OSError, ValueError):
        proc_ok = False
    check(proc_ok, "processNamespaceIsolated")

    host_service_port = int(os.environ.get("TRISYNORA_HOST_TEST_PORT", "0"))
    host_loopback_denied = False
    if 1 <= host_service_port <= 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.5)
            try:
                host_loopback_denied = sock.connect_ex(
                    ("127.0.0.1", host_service_port)) != 0
            except OSError:
                host_loopback_denied = True
    check(host_loopback_denied, "hostLoopbackServiceUnreachable")

    external_network_denied = False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.5)
        try:
            external_network_denied = sock.connect_ex(
                ("1.1.1.1", 443)) != 0
        except OSError:
            external_network_denied = True
    check(external_network_denied, "internetEgressDenied")

    # Same Docker process now launches the real installed upstream Agent
    # and Python stdio MCP. Its keyless SSE provider binds only loopback
    # WITHIN this isolated network namespace and is still allowed.
    command_probe = {}
    original_run = agent.subprocess.run
    def run_with_safe_diagnostics(*args, **kwargs):
        completed = original_run(*args, **kwargs)
        # Never disclose process stdout/stderr, model URLs or auth values.
        text_value = ((completed.stderr or "") + "\n" +
                      (completed.stdout or ""))
        categories = (
            "EACCES", "EROFS", "ENOENT", "EPERM", "ECONNREFUSED",
            "ERR_MODULE_NOT_FOUND", "MODULE_NOT_FOUND", "SQLITE_READONLY",
            "permission denied", "read-only file system",
            "Cannot find module", "unknown option", "not found",
            "fetch failed", "Error:", "error:",
        )
        missing_specifiers = re.findall(
            r"""Cannot find (?:module|package) ['"]([^'"]+)['"]""",
            text_value,
        )
        # Module identifiers only. Directory prefixes and other stderr
        # content must NOT be emitted even on a failed CI.
        missing_names = [
            name.rsplit("/", 1)[-1][:90]
            for name in missing_specifiers[:4]
        ]
        command_probe.update({
            "missingModuleNames": missing_names,
            "exit": completed.returncode,
            "stdoutCharacters": len(completed.stdout or ""),
            "stderrCharacters": len(completed.stderr or ""),
            "errorCategories": [name for name in categories
                                if name.lower() in text_value.lower()],
            "lastNonemptyLineCategory": (
                "javascript-stack" if "at " in text_value
                else "usage-or-error" if text_value.strip()
                else "no-output"
            ),
        })
        return completed
    agent.subprocess.run = run_with_safe_diagnostics
    try:
        result = agent.run()
        genuine = (
            result.get("status") == "headless-agent-mcp-pass"
            and result.get("toolResultObservedInLaterModelRequest") is True
            and result.get("headlessExitZero") is True
            and result.get("realModelCalled") is False
        )
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
        genuine = False
        result = {}
    finally:
        agent.subprocess.run = original_run
    check(genuine, "officialHarnessAgentMcpInSameContainer")

    report = {
        "status": "harness-container-os-boundary-pass"
        if not failures else "not-verified",
        "checks": facts,
        "failedChecks": failures,  # Static check names, no host paths or keys.
        "officialDshMcpSuccess": genuine,
        "agentDiagnostics": {
            "dshProcess": command_probe,
            "status": result.get("status"),
            "headlessExitZero": result.get("headlessExitZero"),
            "providerRequests": result.get("providerRequests"),
            "modelRequestedMcpTool": result.get("modelRequestedMcpTool"),
            "toolResultObservedInLaterModelRequest":
                result.get("toolResultObservedInLaterModelRequest"),
            "mockProviderError": result.get("mockProviderError"),
            "providerMessageSummaries": result.get("providerMessageSummaries", []),
        },
        "nativeProductsMounted": False if facts.get("noNativeCheckoutMounts") else None,
        "hostNetworkDisabled": facts.get("hostLoopbackServiceUnreachable")
        and facts.get("internetEgressDenied"),
        "stockBashFsToolInvocationsVerified": False,
        "nativeWriteAuthorized": False,
        "realModelCalled": False,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
