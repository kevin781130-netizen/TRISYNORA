"""TRISYNORA P1 MP4 frame and decode tests; no PointFlux/H3 runtime."""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from p1_video_handoff import pack
from pointflux_media_probe import (
    MediaProbeRejected, MediaProbeUnavailable,
    parse_probe, verify_playable,
)


def metadata() -> dict:
    return {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        "streams": [{
            "codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p",
            "width": 128, "height": 72, "avg_frame_rate": "30/1",
            "nb_read_frames": "30", "nb_frames": "30",
        }],
    }


class TestStrictProbeParser(unittest.TestCase):
    def check(self, source):
        return parse_probe(source, expected_fps=Fraction(30, 1), expected_frames=30)

    def test_valid_synthetic_metadata(self):
        r = self.check(metadata())
        self.assertEqual(r["codec"], "h264")
        self.assertEqual(r["frameCount"], 30)

    def test_fps_mismatch_rejected(self):
        v = metadata()
        v["streams"][0]["avg_frame_rate"] = "30000/1001"
        with self.assertRaisesRegex(MediaProbeRejected, "fps mismatches"):
            self.check(v)

    def test_frame_count_mismatch_rejected(self):
        v = metadata()
        v["streams"][0]["nb_read_frames"] = "29"
        with self.assertRaisesRegex(MediaProbeRejected, "frame count mismatches"):
            self.check(v)

    def test_indexed_frame_mismatch_rejected(self):
        v = metadata()
        v["streams"][0]["nb_frames"] = "31"
        with self.assertRaisesRegex(MediaProbeRejected, "indexed frame count"):
            self.check(v)

    def test_unknown_count_rejected(self):
        v = metadata()
        v["streams"][0]["nb_read_frames"] = "N/A"
        with self.assertRaisesRegex(MediaProbeRejected, "counted frames"):
            self.check(v)

    def test_extra_video_or_audio_streams_rejected(self):
        v = metadata()
        v["streams"].append({"codec_type": "audio", "codec_name": "aac"})
        with self.assertRaisesRegex(MediaProbeRejected, "exactly one video"):
            self.check(v)

    def test_wrong_codec_and_format_rejected(self):
        for attr, val in (("codec_name", "mpeg4"), ("pix_fmt", "yuv444p"),
                          ("codec_type", "audio")):
            with self.subTest(field=attr):
                v = metadata()
                v["streams"][0][attr] = val
                with self.assertRaises(MediaProbeRejected):
                    self.check(v)
        v = metadata()
        v["format"]["format_name"] = "matroska,webm"
        with self.assertRaisesRegex(MediaProbeRejected, "not MP4"):
            self.check(v)

    def test_invalid_dimensions_rejected(self):
        for key, value in (("width", 4096), ("height", 5000),
                           ("width", 0), ("height", 40), ("width", True)):
            with self.subTest(key=key, value=value):
                v = metadata()
                v["streams"][0][key] = value
                with self.assertRaises(MediaProbeRejected):
                    self.check(v)

    def test_invalid_or_missing_fields_rejected(self):
        for invalid in (None, {}, [], {"streams": []}, {"format": {}}):
            with self.subTest(data=invalid):
                with self.assertRaises(MediaProbeRejected):
                    self.check(invalid)
        for invalid in ("N/A", "0/0", "0/1", "-1/1", ""):
            with self.subTest(fps=invalid):
                v = metadata()
                v["streams"][0]["avg_frame_rate"] = invalid
                with self.assertRaises(MediaProbeRejected):
                    self.check(v)


class TestReceiverProbeIntegration(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.export = self.root / "isolated-h3-export"
        self.export.mkdir()
        (self.export / "video").mkdir()
        (self.export / "native").mkdir()
        self.media = self.export / "video" / "approved.mp4"
        self.media.write_bytes(b"synthetic bytes - deliberately invalid mp4")
        self.native = self.export / "native" / "snapshot.json"
        self.native.write_text('{"fixture":true}', encoding="utf-8")
        self.package = self.root / "fresh-package"
        self.target = self.root / "pointflux-preserve"
        self.target.mkdir()
        (self.target / "keep.txt").write_text("NO WRITES TO POINTFLUX", encoding="utf-8")

    def produce(self):
        pack(
            source_root=self.export, video="video/approved.mp4",
            native_file="native/snapshot.json", destination=self.package,
            project_id="H3demo", revision="export-fixture",
            shot_id="Shot001", artifact_id="asset_Shot001",
            native_format="minimax-h3/export-fixture",
            fps_num=30, fps_den=1, frames=30,
        )

    def test_mocked_ffprobe_and_decoder_never_authorizes_or_imports(self):
        self.produce()
        old_hashes = {
            p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.root.rglob("*") if p.is_file()
        }
        calls = []
        def fake_runner(bin_name, args, timeout):
            calls.append((bin_name, args, timeout))
            return json.dumps(metadata()) if bin_name == "ffprobe" else ""
        with patch("pointflux_media_probe._run", side_effect=fake_runner):
            result = verify_playable(self.package, "PFdemo")
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["media"]["fullVideoDecodeSucceeded"])
        self.assertFalse(result["authority"]["pointfluxImported"])
        self.assertFalse(result["authority"]["receiverAuthorized"])
        self.assertFalse(result["authority"]["crossProductE2EVerified"])
        self.assertEqual([x[0] for x in calls], ["ffprobe", "ffmpeg"])
        new_hashes = {
            p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.root.rglob("*") if p.is_file()
        }
        self.assertEqual(old_hashes, new_hashes)

    def test_invalid_synthetic_video_is_not_playable(self):
        self.produce()
        if not shutil.which("ffprobe"):
            self.skipTest("ffprobe missing; no decode attempt possible")
        with self.assertRaises(MediaProbeRejected):
            verify_playable(self.package, "PFdemo")

    def test_forged_frame_count_never_calls_decoder(self):
        self.produce()
        v = metadata()
        v["streams"][0]["nb_read_frames"] = "25"
        with patch("pointflux_media_probe._run", return_value=json.dumps(v)) as called:
            with self.assertRaisesRegex(MediaProbeRejected, "frame count"):
                verify_playable(self.package, "PFdemo")
        self.assertEqual(called.call_count, 1)

    def test_mismatched_mime_does_not_run_external_tools(self):
        self.produce()
        m = self.package / "manifests" / "asset.json"
        data = json.loads(m.read_text(encoding="utf-8"))
        data["media"]["mimeType"] = "image/png"
        m.write_text(json.dumps(data), encoding="utf-8")
        with patch("pointflux_media_probe._run") as called:
            with self.assertRaises(MediaProbeRejected):
                verify_playable(self.package, "PFdemo")
        called.assert_not_called()

    def test_missing_ffprobe_is_not_a_false_pass(self):
        self.produce()
        with patch("pointflux_media_probe.shutil.which", return_value=None):
            with self.assertRaises(MediaProbeUnavailable):
                verify_playable(self.package, "PFdemo")

    def test_real_h264_mp4_is_decoded_with_ffmpeg(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg/ffprobe not installed on this runner")
        proc = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=128x72:r=30:d=1",
            "-frames:v", "30", "-an", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", str(self.media),
        ], shell=False, capture_output=True, timeout=40)
        if proc.returncode != 0:
            self.fail("runner has FFmpeg but failed to encode H.264 test fixture")
        original_video = hashlib.sha256(self.media.read_bytes()).hexdigest()
        original_native = hashlib.sha256(self.native.read_bytes()).hexdigest()
        self.produce()
        result = verify_playable(self.package, "PFdemo")
        self.assertEqual(result["media"]["codec"], "h264")
        self.assertEqual(result["media"]["frameCount"], 30)
        self.assertEqual(result["media"]["width"], 128)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["media"]["fullVideoDecodeSucceeded"])
        self.assertFalse(result["authority"]["receiverAuthorized"])
        self.assertFalse(result["authority"]["pointfluxImported"])
        self.assertEqual(hashlib.sha256(self.media.read_bytes()).hexdigest(), original_video)
        self.assertEqual(hashlib.sha256(self.native.read_bytes()).hexdigest(), original_native)
        self.assertEqual((self.target / "keep.txt").read_text(), "NO WRITES TO POINTFLUX")


if __name__ == "__main__":
    unittest.main()
