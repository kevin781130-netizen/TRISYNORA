"""Read-only receiver contract tests. No import, media decode, or product write."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from p1_video_handoff import pack  # noqa: E402
from pointflux_receiver_dry_run import assess, ReceiverContractError  # noqa: E402


class PointFluxReceiverDryRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.producer = self.work / "h3-export"
        self.producer.mkdir()
        (self.producer / "render").mkdir()
        (self.producer / "native").mkdir()
        (self.producer / "render" / "take001.mp4").write_bytes(
            b"synthetic video payload - NOT a valid MP4 codec"
        )
        (self.producer / "native" / "production.json").write_bytes(b'{"synthetic":true}')
        self.package = self.work / "exchange"
        self.target = self.work / "pointflux-native"
        self.target.mkdir()
        (self.target / "important-project.json").write_text("NO_MODIFICATIONS", encoding="utf-8")
        self.meta = {
            "source_root": self.producer,
            "video": "render/take001.mp4",
            "native_file": "native/production.json",
            "destination": self.package,
            "project_id": "H3_demo",
            "revision": "fixture-r1",
            "shot_id": "H3Shot001",
            "artifact_id": "asset_H3_demo",
            "native_format": "minimax-h3/mock-native-v1",
            "fps_num": 30000,
            "fps_den": 1001,
            "frames": 1500,  # 50.05 seconds at 30000/1001
        }
        pack(**self.meta)

    def _read(self, kind):
        return json.loads((self.package / "manifests" / f"{kind}.json").read_text(encoding="utf-8"))

    def _replace(self, kind, obj):
        file = self.package / "manifests" / f"{kind}.json"
        file.write_text(json.dumps(obj), encoding="utf-8")
        marker = self.package / "ready.json"
        ready = json.loads(marker.read_text(encoding="utf-8"))
        key = f"{kind}ManifestSha256"
        ready[key] = hashlib.sha256(file.read_bytes()).hexdigest()
        marker.write_text(json.dumps(ready), encoding="utf-8")

    def _assess(self, **kwargs):
        return assess(self.package, "PF_demo", **kwargs)

    def test_structurally_valid_package_remains_blocked(self):
        report = self._assess()
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["format"], "trisynora.pointflux-receiver-assessment/v1")
        self.assertEqual(report["target"]["product"], "pointflux")
        self.assertTrue(report["asset"]["bytesVerified"])
        self.assertFalse(report["asset"]["realMp4CodecVerified"])
        self.assertFalse(report["authority"]["receiverAuthorized"])
        self.assertFalse(report["authority"]["pointfluxImported"])
        self.assertFalse(report["authority"]["crossProductE2EVerified"])
        self.assertIn("pointflux-native-video-layer-not-established", report["blockingReasons"])

    def test_read_only_proof_before_after_file_bytes(self):
        files = {
            p.relative_to(self.work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.work.rglob("*") if p.is_file()
        }
        self._assess()
        after = {
            p.relative_to(self.work).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.work.rglob("*") if p.is_file()
        }
        self.assertEqual(files, after)
        self.assertEqual((self.target / "important-project.json").read_text(), "NO_MODIFICATIONS")

    def test_target_fps_rational_exact_match(self):
        report = self._assess(target_fps_num=60000, target_fps_den=2002)
        self.assertTrue(report["timebase"]["exactFpsMatch"])
        self.assertNotIn("fps-mismatch-requires-explicit-conversion-plan", report["blockingReasons"])

    def test_target_fps_mismatch_never_silently_converts(self):
        report = self._assess(target_fps_num=30, target_fps_den=1)
        self.assertFalse(report["timebase"]["exactFpsMatch"])
        self.assertIn("fps-mismatch-requires-explicit-conversion-plan", report["blockingReasons"])
        self.assertEqual(report["shot"]["fpsNumerator"], 30000)

    def test_rejects_partial_or_invalid_target_fps(self):
        for args in (
            {"target_fps_num": 30},
            {"target_fps_den": 1},
            {"target_fps_num": 0, "target_fps_den": 1},
            {"target_fps_num": 300, "target_fps_den": 1},
            {"target_fps_num": 1, "target_fps_den": 4},
        ):
            with self.subTest(fps=args):
                with self.assertRaises(ReceiverContractError):
                    self._assess(**args)

    def test_rejects_invalid_target_id(self):
        for name in ("../PointFlux", "PF wrong", "/workspace", ""):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ReceiverContractError, "target project"):
                    assess(self.package, name)

    def test_rejects_tampered_media(self):
        path = self.package / "assets" / "asset_H3_demo.mp4"
        path.write_bytes(b"tampered media")
        with self.assertRaisesRegex(ReceiverContractError, "package verification failed"):
            self._assess()

    def test_rejects_missing_readiness_receipt(self):
        (self.package / "ready.json").unlink()
        with self.assertRaises(ReceiverContractError):
            self._assess()

    def test_rejects_nonvideo_mime_even_with_correct_manifest_digest(self):
        asset = self._read("asset")
        asset["media"]["mimeType"] = "image/png"
        self._replace("asset", asset)
        with self.assertRaisesRegex(ReceiverContractError, "only handles video/mp4"):
            self._assess()

    def test_rejects_foreign_product_even_if_receipt_updated(self):
        asset = self._read("asset")
        shot = self._read("shot")
        asset["origin"]["product"] = "pointflux"
        shot["origin"]["product"] = "pointflux"
        self._replace("asset", asset)
        self._replace("shot", shot)
        with self.assertRaises(ReceiverContractError):
            self._assess()

    def test_rejects_longer_than_60_second_pilot(self):
        shot = self._read("shot")
        shot["timebase"]["durationFrames"] = 2000
        self._replace("shot", shot)
        with self.assertRaisesRegex(ReceiverContractError, "60-second"):
            self._assess()

    def test_rejects_fps_above_policy_limit(self):
        shot = self._read("shot")
        shot["timebase"]["fpsNumerator"] = 121
        shot["timebase"]["fpsDenominator"] = 1
        self._replace("shot", shot)
        with self.assertRaisesRegex(ReceiverContractError, "fps beyond"):
            self._assess()

    def test_rejects_two_assets_even_if_structurally_valid(self):
        shot = self._read("shot")
        shot["assetIds"].append("another_asset")
        self._replace("shot", shot)
        with self.assertRaises(ReceiverContractError):
            self._assess()

    def test_rejects_receiver_downgrade_of_reference_only(self):
        shot = self._read("shot")
        shot["handoff"]["mode"] = "approved-media"
        self._replace("shot", shot)
        with self.assertRaises(ReceiverContractError):
            self._assess()


if __name__ == "__main__":
    unittest.main()
