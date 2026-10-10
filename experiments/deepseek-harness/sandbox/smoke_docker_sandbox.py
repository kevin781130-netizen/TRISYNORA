#!/usr/bin/env python3
"""Host launcher for an ACTUAL Docker-contained official DeepSeek Harness.

No checkout is copied into the image. Only 4 audited experiment source files
and one synthetic canary are staged OUTSIDE the Git checkout, mounted RO.
No Vera, H3, PointFlux, real API key, host HOME or Docker socket is mounted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile

from contract_gate import validate_docker_invocation

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
STAGED = (
    "readonly_mcp.py",
    "dsh.patch.yml",
    "smoke_agent_loop.py",
)
SANDBOX_STAGED = (
    "container_sandbox_probe.py",
    "readonly-canary.txt",
)
IMAGE = "trisynora-dsh-os-boundary:local"


def _run(argv: list[str], *, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(argv, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True,
                          timeout=timeout, check=False)


def main() -> int:
    runner = os.environ.get("RUNNER_TEMP", "")
    dsh = os.environ.get("DSH_CLI", "")
    if not runner or not Path(runner).is_dir() or not dsh:
        raise RuntimeError("disposable runner and pinned DSH runtime required")
    dsh_link = Path(dsh)
    if not dsh_link.is_file():
        raise RuntimeError("DSH CLI missing")
    # Existing pinned package root is in runner temp. Never mount /home/runner
    # or the complete runner directory.
    runtime = dsh_link.parent.parent.parent
    if not (runtime / "node_modules" / ".bin" / "dsh").is_file():
        raise RuntimeError("expected isolated DSH npm runtime missing")
    if not shutil.which("docker"):
        raise RuntimeError("Docker isolation unavailable: cannot claim sandbox")

    with tempfile.TemporaryDirectory(
        dir=runner, prefix="trisynora-dsh-docker-",
    ) as root_name:
        root = Path(root_name)
        stage = root / "staged-plugin"
        stage.mkdir()
        for filename in STAGED:
            shutil.copy2(SOURCE / filename, stage / filename)
        for filename in SANDBOX_STAGED:
            shutil.copy2(HERE / filename, stage / filename)
        # Synthetic protected data exist on runner but NOT in Docker mounts.
        # No real credentials, source tree or product IDs are accessed.
        protected = root / "host-native"
        for product in ("Vera", "minimax-H3", "PointFlux"):
            product_dir = protected / product
            product_dir.mkdir(parents=True)
            (product_dir / "HOST_ONLY_SENTINEL.txt").write_text(
                "SYNTHETIC_HOST_ONLY_NEVER_ACCESSIBLE_TO_DSH\n",
                encoding="utf-8",
            )
        context = root / "empty-docker-context"
        context.mkdir()
        # image is assembled only from public Node base + apt packages,
        # with an EMPTY build context. No Docker COPY/ADD of workspace.
        built = _run([
            "docker", "build", "--pull",
            "-f", str(HERE / "Dockerfile"),
            "-t", IMAGE, str(context),
        ], timeout=240)
        if built.returncode:
            print(json.dumps({
                "status": "not-verified",
                "stage": "build-minimal-dsh-isolation-container",
                "imageBuilt": False,
                "nativeProductsMounted": False,
            }, sort_keys=True))
            return 2

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as host:
            host.bind(("127.0.0.1", 0))
            host.listen(4)
            host_port = host.getsockname()[1]
            args = [
                "docker", "run", "--rm", "--pull=never",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=96",
                "--memory=1024m",
                "--cpus=1.5",
                "--user=10001:10001",
                "--tmpfs=/tmp:rw,nosuid,nodev,mode=1777,size=256m",
                "--mount", f"type=bind,src={runtime},dst=/opt/dsh,readonly",
                "--mount", f"type=bind,src={stage},dst=/opt/trisynora,readonly",
                "--env=DSH_CLI=/opt/dsh/node_modules/.bin/dsh",
                "--env=RUNNER_TEMP=/tmp",
                "--env=DSH_TELEMETRY_DISABLED=1",
                "--env=PYTHONDONTWRITEBYTECODE=1",
                f"--env=TRISYNORA_HOST_TEST_PORT={host_port}",
                "--workdir", "/tmp",
                IMAGE,
                "python3", "/opt/trisynora/container_sandbox_probe.py",
            ]
            validate_docker_invocation(args, runtime=runtime, stage=stage)
            try:
                check = _run(args, timeout=185)
                lines = [line.strip() for line in check.stdout.splitlines()
                         if line.strip().startswith("{")]
                proof = json.loads(lines[-1]) if lines else {}
            except (ValueError, json.JSONDecodeError, IndexError,
                    subprocess.TimeoutExpired):
                proof = {}
                check = None

        host_untouched = all(
            (protected / product / "HOST_ONLY_SENTINEL.txt").read_text(
                encoding="utf-8"
            ) == "SYNTHETIC_HOST_ONLY_NEVER_ACCESSIBLE_TO_DSH\n"
            for product in ("Vera", "minimax-H3", "PointFlux")
        )
        mount_untouched = (
            (stage / "readonly-canary.txt").read_text(
                encoding="utf-8") == "TRISYNORA_SANDBOX_READONLY_CANARY\n"
        )
        success = (
            check is not None
            and check.returncode == 0
            and proof.get("status") == "harness-container-os-boundary-pass"
            and all(proof.get("checks", {}).values())
            and proof.get("officialDshMcpSuccess") is True
            and host_untouched and mount_untouched
        )
        report = {
            "status": "official-harness-container-escape-tests-pass"
            if success else "not-verified",
            "stage": "complete" if success
            else "container-execution-or-boundary-check",
            "containerImageBuilt": True,
            "dockerNetworkNone": True,
            "dockerReadOnlyRoot": True,
            "dockerDropAllCaps": True,
            "dockerNoNewPrivileges": True,
            "dockerNonRootUid": True,
            "dockerOnlyStagedPluginsMountedReadOnly": True,
            "officialHeadlessAgentMcpInContainer":
                proof.get("officialDshMcpSuccess") is True,
            "boundaryChecks": proof.get("checks", {}),
            "agentDiagnostics": proof.get("agentDiagnostics", {}),
            "failedChecks": proof.get("failedChecks", []),
            "syntheticHostSecretsIntact": host_untouched,
            "readOnlyFixtureIntact": mount_untouched,
            "modelCalledExternally": False,
            "actualBashFsToolCallsExercised": False,
            "nativeProductSourceMounted": False,
            "nativeRuntimeConnected": False,
        }
        print(json.dumps(report, sort_keys=True))
        return 0 if success else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError) as exc:
        print(json.dumps({
            "status": "not-verified",
            "stage": "sandbox-runner-prerequisite",
            "errorType": type(exc).__name__,
        }, sort_keys=True))
        sys.exit(2)
