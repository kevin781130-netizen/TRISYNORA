"""TRISYNORA P1 local source-copy proof, without real H3/PointFlux imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from p1_video_handoff import pack, inspect, HandoffError


class P1VideoHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.origin = self.work / "source"
        self.origin.mkdir()
        (self.origin / "render").mkdir()
        (self.origin / "project").mkdir()
        self.video = self.origin / "render" / "take.mp4"
        self.native = self.origin / "project" / "snapshot.json"
        self.video.write_bytes(b"synthetic bytes only, not a real video file")
        self.native.write_text('{"synthetic": true}', encoding="utf-8")
        self.dest = self.work / "exchange"
        self.kwargs = {
            "source_root": self.origin, "video": "render/take.mp4",
            "native_file": "project/snapshot.json", "destination": self.dest,
            "project_id": "H3demo", "revision": "fixture-r1",
            "shot_id": "H3Shot001", "artifact_id": "asset_H3demo_001",
            "native_format": "minimax-h3/fixture-r1",
            "fps_num": 30000, "fps_den": 1001, "frames": 1800,
        }

    def test_package_copy_and_readonly_source(self):
        old_video = self.video.read_bytes()
        old_native = self.native.read_bytes()
        result = pack(**self.kwargs)
        self.assertEqual(result["status"], "handoff-package-verified")
        self.assertEqual(result["assetBytesChecked"], 1)
        self.assertTrue(result["sourceUnchangedAtPackaging"])
        self.assertFalse(result["pointfluxImported"])
        self.assertFalse(result["receiverAuthorized"])
        self.assertFalse(result["videoCodecVerified"])
        self.assertEqual(self.video.read_bytes(), old_video)
        self.assertEqual(self.native.read_bytes(), old_native)
        self.assertEqual((self.dest / "assets" / "asset_H3demo_001.mp4").read_bytes(), old_video)
        self.assertEqual(inspect(self.dest)["sha256"], hashlib.sha256(old_video).hexdigest())

    def test_no_overwrite_existing_output(self):
        self.dest.mkdir()
        (self.dest / "KEEP").write_text("unchanged")
        with self.assertRaisesRegex(HandoffError, "NEW folder"):
            pack(**self.kwargs)
        self.assertEqual((self.dest / "KEEP").read_text(), "unchanged")

    def test_destination_under_source_rejected(self):
        output = self.origin / "illegal"
        with self.assertRaisesRegex(HandoffError, "inside source"):
            pack(**dict(self.kwargs, destination=output))
        self.assertFalse(output.exists())

    def test_symlinked_source_rejected(self):
        alias = self.origin / "render" / "linked.mp4"
        try:
            alias.symlink_to(self.video)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic link creation unavailable")
        with self.assertRaisesRegex(HandoffError, "unsafe"):
            pack(**dict(self.kwargs, video="render/linked.mp4"))
        self.assertFalse(self.dest.exists())

    def test_invalid_metadata_fail_closed(self):
        for k,v in (("project_id", "../escape"), ("shot_id", "bad.path"),
                    ("artifact_id", "wrong:scheme"), ("revision", "invalid space"),
                    ("fps_num", 0), ("native_format", "https://unsafe")):
            with self.subTest(key=k):
                with self.assertRaises(HandoffError):
                    pack(**dict(self.kwargs, **{k:v}))
                self.assertFalse(self.dest.exists())

    def test_requires_native_file_and_mp4(self):
        with self.assertRaises(HandoffError):
            pack(**dict(self.kwargs, native_file="project/missing.json"))
        with self.assertRaisesRegex(HandoffError, "mp4"):
            pack(**dict(self.kwargs, video="render/movie.mov"))
        self.assertFalse(self.dest.exists())

    def test_tampered_video_fails_receiver(self):
        pack(**self.kwargs)
        (self.dest / "assets" / "asset_H3demo_001.mp4").write_bytes(b"BAD")
        with self.assertRaises(HandoffError):
            inspect(self.dest)

    def test_tampered_shot_manifest_fails_receiver(self):
        pack(**self.kwargs)
        p = self.dest / "manifests" / "shot.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["shotId"] = "WrongShot"
        p.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(HandoffError, "manifest changed"):
            inspect(self.dest)

    def test_missing_ready_marker_fails_receiver(self):
        pack(**self.kwargs)
        (self.dest / ".ready.json").unlink()
        with self.assertRaisesRegex(HandoffError, "readiness"):
            inspect(self.dest)

    def test_foreign_origin_fails_receiver_even_if_marker_updated(self):
        pack(**self.kwargs)
        p = self.dest / "manifests" / "asset.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["origin"]["product"] = "pointflux"
        p.write_text(json.dumps(data), encoding="utf-8")
        m = self.dest / ".ready.json"
        ready = json.loads(m.read_text(encoding="utf-8"))
        ready["assetManifestSha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        m.write_text(json.dumps(ready), encoding="utf-8")
        with self.assertRaisesRegex(HandoffError, "origin mismatch"):
            inspect(self.dest)

    def test_media_symlink_rejected(self):
        pack(**self.kwargs)
        media = self.dest / "assets" / "asset_H3demo_001.mp4"
        media.unlink()
        try:
            media.symlink_to(self.video)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic link creation unavailable")
        with self.assertRaises(HandoffError):
            inspect(self.dest)

    def test_second_attempt_does_not_replace_first(self):
        pack(**self.kwargs)
        previous = inspect(self.dest)
        with self.assertRaises(HandoffError):
            pack(**self.kwargs)
        self.assertEqual(inspect(self.dest), previous)

    def test_manifest_is_reference_only_and_approval_required(self):
        pack(**self.kwargs)
        a = json.loads((self.dest / "manifests" / "asset.json").read_text(encoding="utf-8"))
        s = json.loads((self.dest / "manifests" / "shot.json").read_text(encoding="utf-8"))
        self.assertEqual(a["publication"]["mode"], "reference-only")
        self.assertTrue(a["publication"]["requiresReceiverApproval"])
        self.assertEqual(s["handoff"]["mode"], "reference-only")
        self.assertTrue(s["handoff"]["requiresExplicitBind"])
        self.assertEqual(s["native"]["sha256"], hashlib.sha256(self.native.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
