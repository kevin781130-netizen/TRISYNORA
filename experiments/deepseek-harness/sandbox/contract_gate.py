"""Fail-closed checked Docker launch: no mount/credential/network flag drift.

Audits an exact allowlist for the test deployment only. A static invocation
gate is NOT a kernel audit; actual confinement is exercised in Docker E2E.
"""
from __future__ import annotations

from pathlib import Path


class SandboxPolicyError(ValueError):
    pass


def validate_docker_invocation(argv: list[str], *,
                               runtime: Path, stage: Path) -> None:
    if not isinstance(argv, list) or any(type(x) is not str for x in argv):
        raise SandboxPolicyError("invalid launcher tokens")
    required = {
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=96",
        "--memory=1024m", "--cpus=1.5", "--user=10001:10001",
        "--tmpfs=/tmp:rw,nosuid,nodev,mode=1777,size=256m",
    }
    if (argv[:4] != ["docker", "run", "--rm", "--pull=never"]
            or any(argv.count(x) != 1 for x in required)
            or "--workdir=/tmp" not in argv and
            not (argv.count("--workdir") == 1 and
                 argv[argv.index("--workdir") + 1] == "/tmp")):
        raise SandboxPolicyError("required isolation options missing")
    if (not runtime.is_absolute() or not stage.is_absolute()
            or runtime == stage):
        raise SandboxPolicyError("isolated absolute mount roots required")
    for mount in (runtime, stage):
        if not mount.is_dir() or mount.is_symlink():
            raise SandboxPolicyError("unsafe source for read-only mount")
        if any((p / ".git").exists() for p in (mount, *mount.parents)):
            raise SandboxPolicyError("git worktree may not enter container")
    expected_mounts = {
        f"type=bind,src={stage},dst=/opt/trisynora,readonly",
    }
    mounts = [argv[i + 1] for i, x in enumerate(argv[:-1])
              if x == "--mount"]
    if len(mounts) != 1 or set(mounts) != expected_mounts:
        raise SandboxPolicyError("only image-baked DSH and exact staged readonly driver permitted")
    # No -v bind, docker socket, host pid/net/IPC, privileged, device,
    # extra mount, or environment borrowed from host runner.
    forbidden_prefixes = (
        "--privileged", "--device", "--cap-add", "--pid", "--ipc",
        "--uts", "--net=", "--network=host", "--volume", "-v",
        "--security-opt=seccomp=unconfined", "--env-file", "--entrypoint",
    )
    if any(any(a == k or a.startswith(k + "=")
               for k in forbidden_prefixes) for a in argv):
        raise SandboxPolicyError("forbidden docker escape switch")
    if any(x in ("--mount", "--workdir", "docker", "run") for x in mounts):
        raise SandboxPolicyError("malformed mount values")
    expected_env = {
        "--env=DSH_CLI=/opt/dsh/node_modules/.bin/dsh",
        "--env=RUNNER_TEMP=/tmp",
        "--env=DSH_TELEMETRY_DISABLED=1",
        "--env=PYTHONDONTWRITEBYTECODE=1",
    }
    envs = [x for x in argv if x.startswith("--env=")]
    if (set(envs) - expected_env - {
            e for e in envs
            if e.startswith("--env=TRISYNORA_HOST_TEST_PORT=")
            and e[len("--env=TRISYNORA_HOST_TEST_PORT="):].isdigit()
            and 1 <= int(e.split("=")[-1]) <= 65535
        } or not expected_env <= set(envs) or len(envs) != 5):
        raise SandboxPolicyError("unexpected environment or host credential")
    if (argv[-3:] != [
        "trisynora-dsh-os-boundary:local", "python3",
        "/opt/trisynora/container_sandbox_probe.py",
    ]):
        raise SandboxPolicyError("unexpected image or executable")
    permitted = (
        required
        | expected_env
        | expected_mounts
        | set(envs)
        | {
            "docker", "run", "--rm", "--pull=never", "--mount",
            "--workdir", "/tmp", "trisynora-dsh-os-boundary:local",
            "python3", "/opt/trisynora/container_sandbox_probe.py",
        }
    )
    if any(token not in permitted for token in argv):
        raise SandboxPolicyError("unknown Docker switch or extra parameter")
    if any("docker.sock" in x for x in argv):
        raise SandboxPolicyError("host Docker control socket forbidden")
