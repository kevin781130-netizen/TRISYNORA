"""No-network read-only MCP integration and security tests (Python stdlib)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parent / "readonly_mcp.py"
spec = importlib.util.spec_from_file_location("trisynora_readonly_mcp", SCRIPT)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


def json_bytes(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False) + "\n").encode()


class StandaloneHarnessMCPTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trisynora-mcp-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.exchange = self.root / "external-exchange"
        self.exchange.mkdir()
        (self.exchange / ".trisynora-exchange-root.json").write_bytes(json_bytes({
            "format": "trisynora.external-exchange-root/v1",
            "kind": "read-only-staging",
        }))
        self.pkg = self.exchange / "take_001"
        self.pkg.mkdir()
        (self.pkg / "manifests").mkdir()
        (self.pkg / "assets").mkdir()
        self.video = self.pkg / "assets" / "ApprovedAsset001.mp4"
        self.video.write_bytes(b"synthetic media ONLY - codec not checked")
        self.asset = {
            "contract": "trisynora.asset/v1", "artifactId": "ApprovedAsset001",
            "origin": {"product": "minimax-h3", "projectId": "H3demo", "revision": "sample-r1"},
            "media": {
                "kind": "video", "mimeType": "video/mp4", "path": "assets/ApprovedAsset001.mp4",
                "sizeBytes": len(self.video.read_bytes()),
                "sha256": hashlib.sha256(self.video.read_bytes()).hexdigest(),
            },
            "publication": {"mode": "reference-only", "requiresReceiverApproval": True},
        }
        self.shot = {
            "contract": "trisynora.shot/v1", "shotId": "TakeShot001",
            "origin": self.asset["origin"],
            "native": {"format": "minimax-h3/mock-native", "sha256": "0"*64},
            "timebase": {"fpsNumerator": 30, "fpsDenominator": 1, "durationFrames": 30},
            "assetIds": ["ApprovedAsset001"],
            "handoff": {"mode": "reference-only", "requiresExplicitBind": True},
        }
        self.rebuild()
        self.env = patch.dict(os.environ, {"TRISYNORA_EXCHANGE_ROOT": str(self.exchange)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def rebuild(self):
        a, s = json_bytes(self.asset), json_bytes(self.shot)
        (self.pkg / "manifests" / "asset.json").write_bytes(a)
        (self.pkg / "manifests" / "shot.json").write_bytes(s)
        (self.pkg / "ready.json").write_bytes(json_bytes({
            "format": "trisynora.h3-video-package/v1",
            "assetManifestSha256": hashlib.sha256(a).hexdigest(),
            "shotManifestSha256": hashlib.sha256(s).hexdigest(),
        }))

    def test_declared_capabilities_are_always_unconnected(self):
        catalog = m.dispatch("trisynora_list_capabilities", {})
        self.assertEqual(len(catalog["products"]), 3)
        self.assertEqual({x["id"] for x in catalog["products"]}, set(m.PRODUCTS))
        self.assertFalse(catalog["nativeWriteToolsExposed"])
        for product in catalog["products"]:
            self.assertFalse(product["connected"])
            self.assertTrue(all(not x["callable"] for x in product["declaredCapabilities"]))

    def test_capability_dispatch_only_returns_unavailable(self):
        result = m.dispatch("trisynora_check_capability", {
            "product": "pointflux", "capability": "video-layer-import"})
        self.assertEqual(result["status"], "not-connected")
        self.assertFalse(result["authorized"])

    def test_unknown_mutating_command_rejected(self):
        for cmd in ("native_write", "run_shell", "call_native", "execute", "modify_pointflux"):
            with self.subTest(cmd=cmd):
                with self.assertRaisesRegex(m.Rejected, "unsupported/mutating"):
                    m.dispatch(cmd, {})

    def test_all_tools_declared_read_only(self):
        self.assertEqual(len(m.TOOLS), 3)
        for tool in m.TOOLS:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])
            self.assertFalse(tool["annotations"]["openWorldHint"])
            self.assertFalse(tool["inputSchema"]["additionalProperties"])

    def test_real_digest_locked_reference_only_inspection(self):
        report = m.inspect("take_001")
        self.assertEqual(report["status"], "verified-reference-only")
        self.assertEqual(report["producer"], "minimax-h3")
        self.assertEqual(report["mediaSizeBytes"], self.video.stat().st_size)
        self.assertFalse(report["mediaCodecVerified"])
        self.assertFalse(report["nativeReceiverAuthorized"])
        self.assertFalse(report["nativeProductsConnected"])
        self.assertFalse(report["pointfluxImported"])
        self.assertFalse(report["threeProductE2EVerified"])

    def test_no_file_writes_on_inspect(self):
        before = {
            p.relative_to(self.root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in self.root.rglob("*") if p.is_file()
        }
        m.inspect("take_001")
        after = {
            p.relative_to(self.root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in self.root.rglob("*") if p.is_file()
        }
        self.assertEqual(before, after)

    def test_tampered_asset_media_rejected(self):
        self.video.write_bytes(b"tampered different bytes")
        with self.assertRaisesRegex(m.Rejected, "media bytes"):
            m.inspect("take_001")

    def test_forged_ready_marker_rejected(self):
        (self.pkg / "ready.json").write_text('{"format":"trisynora.h3-video-package/v1","assetManifestSha256":"0"}')
        with self.assertRaises(m.Rejected):
            m.inspect("take_001")

    def test_altered_shot_digest_rejected(self):
        path = self.pkg / "manifests" / "shot.json"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(m.Rejected, "receipt mismatch"):
            m.inspect("take_001")

    def test_mismatched_origin_and_non_reference_only_rejected(self):
        self.shot["origin"] = dict(self.shot["origin"], product="pointflux")
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "producer identity"):
            m.inspect("take_001")
        self.shot["origin"] = self.asset["origin"]
        self.asset["publication"]["mode"] = "write-to-native"
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "approval flags"):
            m.inspect("take_001")

    def test_false_boolean_approval_flag_rejected(self):
        self.asset["publication"]["requiresReceiverApproval"] = 1
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "approval"):
            m.inspect("take_001")

    def test_invalid_media_path_and_dos_declared_size(self):
        self.asset["media"]["path"] = "../outside.mp4"
        self.rebuild()
        with self.assertRaises(m.Rejected):
            m.inspect("take_001")
        self.asset["media"]["path"] = "assets/ApprovedAsset001.mp4"
        self.asset["media"]["sizeBytes"] = m.MAX_MEDIA_BYTES + 1
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "pilot limit"):
            m.inspect("take_001")

    def test_path_traversal_rejected_before_file_read(self):
        for candidate in ("../pointflux", "/etc/passwd", "drive:C", "a.b", "", "..", "take_001/.."):
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(m.Rejected, "package identifier"):
                    m.inspect(candidate)

    def test_staging_inside_git_root_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(m.Rejected, "within any Git checkout"):
            m.inspect("take_001")

    def test_missing_explicit_marker_rejected(self):
        (self.exchange / ".trisynora-exchange-root.json").unlink()
        with self.assertRaises(m.Rejected):
            m.inspect("take_001")

    def test_symlinked_media_or_package_rejected(self):
        src = self.video
        link = self.pkg / "assets" / "linked.mp4"
        try:
            link.symlink_to(src)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unsupported")
        self.asset["media"]["path"] = "assets/linked.mp4"
        self.rebuild()
        with self.assertRaises(m.Rejected):
            m.inspect("take_001")
        self.pkg.rename(self.exchange / "renamed")
        (self.exchange / "take_001").symlink_to(self.exchange / "renamed", target_is_directory=True)
        with self.assertRaises(m.Rejected):
            m.inspect("take_001")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(m.Rejected, "duplicate"):
            m.decode(b'{"hello":1,"hello":2}')

    def test_config_missing_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(m.Rejected, "not configured"):
                m.inspect("take_001")

    def test_mcp_wire_initialize_and_read_only_tools(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion":"2025-06-18", "capabilities": {},
                        "clientInfo":{"name":"pytest","version":"0"}}},
            {"jsonrpc":"2.0", "method":"notifications/initialized"},
            {"jsonrpc":"2.0", "id":2, "method":"tools/list"},
            {"jsonrpc":"2.0", "id":3, "method":"tools/call",
             "params":{"name":"trisynora_inspect_package","arguments":{"packageId":"take_001"}}},
            {"jsonrpc":"2.0", "id":4, "method":"tools/call",
             "params":{"name":"execute","arguments":{"command":"rm -rf ."}}},
        ]
        p = subprocess.run(
            [sys.executable, "-B", str(SCRIPT)], input="\n".join(map(json.dumps, messages))+"\n",
            capture_output=True, text=True, check=False, timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        results = [json.loads(s) for s in p.stdout.splitlines()]
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(len(results[1]["result"]["tools"]), 3)
        good = json.loads(results[2]["result"]["content"][0]["text"])
        self.assertEqual(good["status"], "verified-reference-only")
        self.assertTrue(results[3]["result"]["isError"])

    def test_mcp_bad_message_not_native_execution(self):
        bad = m.handle({"jsonrpc":"2.0","id":1,"method":"tools/call",
                        "params":{"name":"trisynora_inspect_package",
                        "arguments":{"packageId":"../../../escape"}}})
        self.assertTrue(bad["result"]["isError"])
        self.assertEqual(json.loads(bad["result"]["content"][0]["text"])["status"], "rejected")

    def test_mcp_oversized_input_fails_before_processing(self):
        p = subprocess.run([sys.executable, "-B", str(SCRIPT)],
            input="X"*(m.MAX_LINE + 5)+"\n", capture_output=True,
            text=True, check=False, timeout=10)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, "")

    def test_tool_args_unknown_fields_rejected(self):
        with self.assertRaises(m.Rejected):
            m.dispatch("trisynora_inspect_package", {"packageId":"take_001","execute": True})

    def test_can_reject_any_mcp_tool_without_native_approval(self):
        response = m.handle({"jsonrpc":"2.0","id":7,"method":"tools/call",
                             "params":{"name":"mcp__pointflux__create_project",
                                       "arguments":{"path":"/native"}}})
        self.assertTrue(response["result"]["isError"])


    def test_contract_schema_extra_manifest_field_rejected(self):
        self.asset["permission"] = "allow"
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "Asset contract fields"):
            m.inspect("take_001")

    def test_bad_declared_h3_revision_rejected(self):
        self.asset["origin"]["revision"] = "../../untrusted"
        self.shot["origin"] = self.asset["origin"]
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "provenance syntax"):
            m.inspect("take_001")

    def test_bad_declared_native_snapshot_hash_rejected(self):
        self.shot["native"]["sha256"] = "FAKE_SHA"
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "declared SHA"):
            m.inspect("take_001")

    def test_timebase_true_boolean_rejected(self):
        self.shot["timebase"]["durationFrames"] = True
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "timebase integer"):
            m.inspect("take_001")

    def test_timebase_zero_fps_denominator_rejected(self):
        self.shot["timebase"]["fpsDenominator"] = 0
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "timebase integer"):
            m.inspect("take_001")

    def test_timebase_above_fps_bound_rejected(self):
        self.shot["timebase"]["fpsNumerator"] = 240
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "timebase outside pilot"):
            m.inspect("take_001")

    def test_timebase_above_duration_bound_rejected(self):
        self.shot["timebase"]["durationFrames"] = 1801
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "timebase outside pilot"):
            m.inspect("take_001")

    def test_forged_receiver_approval_field_rejected(self):
        self.shot["handoff"]["receiverAuthorized"] = True
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "handoff contract fields"):
            m.inspect("take_001")

    def test_extra_media_key_rejected(self):
        self.asset["media"]["nativeWriteEnabled"] = True
        self.rebuild()
        with self.assertRaisesRegex(m.Rejected, "media contract fields"):
            m.inspect("take_001")



if __name__ == "__main__":
    unittest.main()
