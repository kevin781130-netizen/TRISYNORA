"""Isolated bridge unit tests: mock P1 package/receiver, real Take + FFprobe fixture.

These tests DO NOT prove full TRISYNORA checkout or native H3/PointFlux E2E.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

# Bring in the real source gate but replace unmounted P1 dependencies in this
# independent developer test. Production uses actual sibling imports.
package_module = types.ModuleType("p1_video_handoff")
package_module.HandoffError = type("HandoffError", (ValueError,), {})
package_module.pack = lambda **kwargs: {"status": "handoff-package-verified", "pointfluxImported": False}
probe_module = types.ModuleType("pointflux_media_probe")
probe_module.MAX_VIDEO_BYTES = 128 * 1024 * 1024
probe_module.MediaProbeRejected = type("MediaProbeRejected", (ValueError,), {})
probe_module.MediaProbeUnavailable = type("MediaProbeUnavailable", (ValueError,), {})


def _run(binary, args, timeout):
    cp = subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
    if cp.returncode:
        raise probe_module.MediaProbeRejected("real media probe error")
    return cp.stdout


def _parse(data, *, expected_fps, expected_frames):
    stream = data["streams"][0]
    assert stream["codec_name"] == "h264"
    assert stream["pix_fmt"] == "yuv420p"
    assert Fraction(stream["avg_frame_rate"]) == expected_fps
    assert int(stream["nb_read_frames"]) == expected_frames
    assert data["format"]["format_name"].split(",").count("mp4") == 1
    return {"codec": "h264", "frameCount": expected_frames,
            "fpsNumerator": expected_fps.numerator, "fpsDenominator": expected_fps.denominator}


probe_module._run = _run
probe_module.parse_probe = _parse
probe_module.verify_playable = lambda output, target: {
    "status": "blocked",
    "media": {"sha256": None, "fullVideoDecodeSucceeded": True},
    "authority": {"receiverAuthorized": False, "pointfluxImported": False},
}
spec = importlib.util.spec_from_file_location("isolated_h3_take_bridge", TOOLS / "h3_take_exchange_bridge.py")
bridge_module = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"p1_video_handoff": package_module,
                              "pointflux_media_probe": probe_module}):
    spec.loader.exec_module(bridge_module)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "real FFmpeg/FFprobe required")
class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "export"
        (self.root / "project").mkdir(parents=True)
        (self.root / "render").mkdir()
        self.video = self.root / "render" / "take.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=128x72:rate=24:duration=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.video)
        ], check=True, capture_output=True)
        self.media_sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.snapshot = {
            "id": "p1", "production_v1": {
                "takes": [{"id": "take1", "h3_prompt_id": "job1",
                           "source_media_sha256": self.media_sha,
                           "asset": {"type": "output", "filename": "take.mp4"}}],
                "workflow_runtime_v1": {"runs": [{"pack_id": "h3-native-shot", "prompt_id": "job1"}]},
                "generation_history": [{"prompt_id": "job1", "status": "complete"}],
            },
        }
        self.json_path = self.root / "project" / "snapshot.json"
        self.save()
        self.destination = Path(self.tmp.name) / "exchange1"

    def save(self):
        self.json_path.write_text(json.dumps(self.snapshot), encoding="utf-8")

    def run_bridge(self):
        return bridge_module.bridge(source_root=self.root,
                                    project_file="project/snapshot.json",
                                    video_file="render/take.mp4", project_id="p1",
                                    take_id="take1", destination=self.destination,
                                    target_project_id="pf1")

    def test_real_ffprobe_timebase(self):
        assert shutil.which("ffmpeg")
        fn, fd, frames, info = bridge_module._media_timebase(self.video)
        self.assertEqual((fn, fd, frames), (24, 1, 24))
        self.assertEqual(info["codec"], "h264")

    def test_pass_to_pack_is_digest_bound_and_never_authorized(self):
        before = {f: f.read_bytes() for f in (self.video, self.json_path)}
        with patch.object(bridge_module, "pack", wraps=package_module.pack) as p, \
             patch.object(bridge_module, "verify_playable", return_value={
                 "status": "blocked", "media": {"sha256": self.media_sha, "fullVideoDecodeSucceeded": True},
                 "authority": {"receiverAuthorized": False, "pointfluxImported": False},
             }):
            result = self.run_bridge()
        self.assertEqual(result["status"], "staged_verified_receiver_blocked")
        self.assertFalse(result["nativeH3ExporterVerified"])
        self.assertFalse(result["pointfluxImported"])
        self.assertEqual((p.call_args.kwargs["fps_num"], p.call_args.kwargs["fps_den"], p.call_args.kwargs["frames"]), (24,1,24))
        self.assertEqual(before, {f: f.read_bytes() for f in before})

    def test_changed_mp4_blocks_before_pack(self):
        self.video.write_bytes(b"bad")
        with patch.object(bridge_module, "pack") as p:
            with self.assertRaisesRegex(Exception, "DIGEST_MISMATCH"):
                self.run_bridge()
            p.assert_not_called()

    def test_fake_mp4_blocks_before_pack(self):
        self.video.write_bytes(b"fake mp4")
        self.snapshot["production_v1"]["takes"][0]["source_media_sha256"] = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.save()
        with patch.object(bridge_module, "pack") as p:
            with self.assertRaisesRegex(Exception, "media probe error"):
                self.run_bridge()
            p.assert_not_called()

    def test_receiver_approval_invented_blocks(self):
        with patch.object(bridge_module, "verify_playable", return_value={
            "status": "blocked", "media": {"sha256": self.media_sha, "fullVideoDecodeSucceeded": True},
            "authority": {"receiverAuthorized": True, "pointfluxImported": False},
        }):
            with self.assertRaisesRegex(bridge_module.BridgeError, "CONTRACT_UNVERIFIED"):
                self.run_bridge()

    def test_wrong_target_hash_blocks(self):
        with patch.object(bridge_module, "verify_playable", return_value={
            "status": "blocked", "media": {"sha256": "0"*64, "fullVideoDecodeSucceeded": True},
            "authority": {"receiverAuthorized": False, "pointfluxImported": False},
        }):
            with self.assertRaisesRegex(bridge_module.BridgeError, "CONTRACT_UNVERIFIED"):
                self.run_bridge()


if __name__ == "__main__":
    unittest.main()
