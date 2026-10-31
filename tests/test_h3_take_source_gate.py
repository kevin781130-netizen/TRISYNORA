"""Read-only H3 export-copy preflight; fixtures are NOT H3 render evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.h3_take_source_gate import GateError, check


class H3TakeSourceGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "render").mkdir()
        (self.root / "project").mkdir()
        self.video = self.root / "render" / "take.mp4"
        self.video.write_bytes(b"synthetic-not-valid-mp4")
        digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.snapshot = {
            "id": "project1",
            "production_v1": {
                "takes": [{"id": "take1", "h3_prompt_id": "job1",
                           "source_media_sha256": digest,
                           "asset": {"type": "output", "filename": "take.mp4"}}],
                "workflow_runtime_v1": {"runs": [
                    {"pack_id": "h3-native-shot", "prompt_id": "job1"}]},
                "generation_history": [{"prompt_id": "job1", "status": "complete"}],
            },
        }
        self.project = self.root / "project" / "snapshot.json"
        self.save()

    def save(self):
        self.project.write_text(json.dumps(self.snapshot), encoding="utf-8")

    def gate(self):
        return check(self.root, "project/snapshot.json", "render/take.mp4",
                     "project1", "take1")

    def test_bytes_and_receipts_ready_only_for_further_probe(self):
        before = {p: p.read_bytes() for p in (self.project, self.video)}
        result = self.gate()
        self.assertEqual(result["status"], "ready_for_native_media_probe")
        self.assertFalse(result["videoCodecVerified"])
        self.assertFalse(result["nativeExportAuthenticated"])
        self.assertFalse(result["h3RealRenderVerified"])
        self.assertFalse(result["receiverAuthorized"])
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_video_tampering_blocks(self):
        self.video.write_bytes(b"changed")
        with self.assertRaisesRegex(GateError, "DIGEST_MISMATCH"):
            self.gate()

    def test_missing_take_output_binding_blocks(self):
        del self.snapshot["production_v1"]["takes"][0]["asset"]
        self.save()
        with self.assertRaisesRegex(GateError, "FILENAME_NOT_BOUND"):
            self.gate()

    def test_duplicate_runtime_receipt_blocks(self):
        runs = self.snapshot["production_v1"]["workflow_runtime_v1"]["runs"]
        runs.append(dict(runs[0]))
        self.save()
        with self.assertRaisesRegex(GateError, "AMBIGUOUS"):
            self.gate()

    def test_incomplete_render_blocks(self):
        self.snapshot["production_v1"]["generation_history"][0]["status"] = "running"
        self.save()
        with self.assertRaisesRegex(GateError, "NOT_COMPLETE"):
            self.gate()

    def test_traversal_blocks(self):
        with self.assertRaisesRegex(GateError, "UNSAFE_RELATIVE_PATH"):
            check(self.root, "../outside.json", "render/take.mp4",
                  "project1", "take1")

    def test_duplicate_json_key_blocks(self):
        self.project.write_text('{"id":"project1","id":"project1"}')
        with self.assertRaisesRegex(GateError, "DUPLICATE_JSON_KEY"):
            self.gate()

    def test_symlinked_video_blocks(self):
        self.video.unlink()
        external = self.root / "outside.mp4"
        external.write_bytes(b"outside")
        try:
            self.video.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this OS")
        with self.assertRaisesRegex(GateError, "SYMLINK_SOURCE_REJECTED"):
            self.gate()


if __name__ == "__main__":
    unittest.main()
