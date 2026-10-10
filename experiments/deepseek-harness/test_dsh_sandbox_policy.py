"""Adversarial tests of the exact Docker sandbox policy before real E2E.

These tests do not need Docker; the CI end-to-end job proves runtime behavior.
"""
from pathlib import Path
import tempfile
import unittest

from sandbox.contract_gate import SandboxPolicyError, validate_docker_invocation


class DockerSandboxBoundaryContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="trisynora-docker-policy-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.stage = self.root / "stage"
        self.runtime.mkdir()
        self.stage.mkdir()
        self.args = [
            "docker", "run", "--rm", "--pull=never",
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=96", "--memory=1024m", "--cpus=1.5",
            "--user=10001:10001",
            "--tmpfs=/tmp:rw,nosuid,nodev,mode=1777,size=256m",
            "--mount", f"type=bind,src={self.stage},dst=/opt/trisynora,readonly",
            "--env=DSH_CLI=/opt/dsh/node_modules/.bin/dsh",
            "--env=RUNNER_TEMP=/tmp",
            "--env=DSH_TELEMETRY_DISABLED=1",
            "--env=PYTHONDONTWRITEBYTECODE=1",
            "--env=TRISYNORA_HOST_TEST_PORT=40321",
            "--workdir", "/tmp",
            "trisynora-dsh-os-boundary:local", "python3",
            "/opt/trisynora/container_sandbox_probe.py",
        ]

    def accept(self, args=None, runtime=None, stage=None):
        validate_docker_invocation(
            self.args if args is None else args,
            runtime=self.runtime if runtime is None else runtime,
            stage=self.stage if stage is None else stage,
        )

    def denied(self, args, **kw):
        with self.assertRaises(SandboxPolicyError):
            self.accept(args, **kw)

    def test_pinned_minimal_launch_accepts(self):
        self.accept()

    def test_no_network_namespace_removal(self):
        self.denied([v for v in self.args if v != "--network=none"])

    def test_host_network_override_denied(self):
        self.denied(self.args[:5] + ["--network=host"] + self.args[5:])
        self.denied(self.args[:5] + ["--network=bridge"] + self.args[5:])

    def test_writable_root_denied(self):
        self.denied([x for x in self.args if x != "--read-only"])

    def test_privileged_denied(self):
        self.denied(self.args[:5] + ["--privileged"] + self.args[5:])

    def test_unconfined_process_namespace_denied(self):
        self.denied(self.args[:5] + ["--pid=host"] + self.args[5:])

    def test_docker_socket_or_extra_mount_denied(self):
        self.denied(self.args[:5] + [
            "--mount",
            "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
        ] + self.args[5:])

    def test_host_runtime_mount_denied_even_when_readonly(self):
        self.denied(self.args[:5] + [
            "--mount",
            f"type=bind,src={self.runtime},dst=/opt/dsh,readonly",
        ] + self.args[5:])

    def test_writable_source_mount_denied(self):
        self.denied([
            x.replace("/opt/trisynora,readonly", "/opt/trisynora")
            for x in self.args
        ])

    def test_native_repository_mount_denied(self):
        self.denied(self.args[:5] + [
            "--mount", "type=bind,src=/workspace/Vera,dst=/Vera,readonly"
        ] + self.args[5:])

    def test_extra_credentials_denied(self):
        self.denied(self.args[:5] + [
            "--env=GITHUB_TOKEN=do-not-use"
        ] + self.args[5:])

    def test_inherited_host_environment_denied(self):
        self.denied(self.args[:5] + [
            "--env-file=/home/runner/secret.env"
        ] + self.args[5:])

    def test_root_identity_denied(self):
        self.denied([
            "--user=0:0" if x == "--user=10001:10001" else x
            for x in self.args
        ])

    def test_writeable_tmp_is_bounded_and_flags_pinned(self):
        self.denied([
            "--tmpfs=/tmp:rw,size=1g" if x.startswith("--tmpfs=") else x
            for x in self.args
        ])

    def test_source_with_git_parent_is_denied(self):
        (self.root / ".git").mkdir()
        self.denied(self.args)

    def test_symlinked_stage_denied(self):
        target = self.root / "other"
        target.mkdir()
        link = self.root / "linked"
        link.symlink_to(target, target_is_directory=True)
        args = [x.replace(f"src={self.stage}", f"src={link}")
                for x in self.args]
        self.denied(args, stage=link)

    def test_unexpected_executable_denied(self):
        self.denied(self.args[:-1] + ["/opt/trisynora/other_script.py"])

    def test_bad_or_missing_test_port_denied(self):
        self.denied([
            "--env=TRISYNORA_HOST_TEST_PORT=0"
            if x.startswith("--env=TRISYNORA_HOST_TEST_PORT=") else x
            for x in self.args
        ])


if __name__ == "__main__":
    unittest.main()
