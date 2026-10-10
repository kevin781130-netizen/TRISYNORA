"""G2: real H.264 full-chain rehearsal on SYNTHETIC three-product fixtures.

No native Vera, H3, PointFlux checkout or external service is used.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from bridge_rehearsal import (
    run_rehearsal, RehearsalRejected, RehearsalUnavailable,
)
from isolation_audit import IsolationAuditError
from pointflux_media_probe import MediaProbeRejected


def available() -> bool:
    return all(shutil.which(binary) for binary in ("git", "ffmpeg", "ffprobe"))


@unittest.skipUnless(available(), "Real FFmpeg and Git required; synthetic E2E NOT VERIFIED here")
class G2SyntheticRehearsalTests(unittest.TestCase):
    def test_real_h264_full_path_passes_but_never_claims_native_e2e(self):
        report = run_rehearsal()
        self.assertEqual(report["format"], "trisynora.g2-rehearsal-evidence/v1")
        self.assertEqual(report["status"], "synthetic-bridge-rehearsal-pass")
        self.assertEqual(report["sourceType"], "temporary-synthetic-git-products-only")
        self.assertTrue(report["media"]["fullFFmpegDecodeVerified"])
        self.assertTrue(report["media"]["ffprobeStreamVerified"])
        self.assertEqual(report["media"]["codec"], "h264")
        self.assertEqual(report["media"]["frames"], 30)
        self.assertTrue(report["isolation"]["unchangedWithinScope"])
        self.assertFalse(report["isolation"]["unwatchedUntrackedFilesVerified"])
        self.assertEqual(set(report["isolation"]["products"]), {"vera", "minimax-h3", "pointflux"})
        for value in report["isolation"]["products"].values():
            self.assertFalse(value["headChanged"])
            self.assertEqual(value["pathDifferences"], 0)
        self.assertFalse(report["nativeProductsActuallyRun"])
        self.assertFalse(report["receiverAuthorizationGranted"])
        self.assertFalse(report["pointfluxNativeVideoImported"])
        self.assertFalse(report["veraFinalVerification"])
        self.assertFalse(report["realThreeProjectE2EVerified"])

    def test_staged_source_hashes_are_preserved(self):
        observed = {}
        def observe(paths):
            for rel in (
                ("minimax-h3", "exports/approved.mp4"),
                ("minimax-h3", "projects/production.json"),
                ("pointflux", "projects/project.json"),
                ("vera", "settings/agent.json"),
            ):
                p = paths["roots"][rel[0]] / rel[1]
                observed[rel] = (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            observed["export_sha"] = hashlib.sha256(
                (paths["export"] / "video" / "approved.mp4").read_bytes()
            ).hexdigest()
        report = run_rehearsal(after_package=observe)
        self.assertEqual(report["media"]["sourceSha256"], observed["export_sha"])
        self.assertEqual(report["status"], "synthetic-bridge-rehearsal-pass")
        self.assertEqual(len(observed), 5)

    def test_pointflux_native_fixture_changed_blocks_release(self):
        def poison(paths):
            native = paths["roots"]["pointflux"] / "projects" / "project.json"
            native.write_text('{"tampered":true}', encoding="utf-8")
        with self.assertRaisesRegex(RehearsalRejected, "synthetic product source changed"):
            run_rehearsal(after_package=poison)

    def test_h3_approved_take_changed_blocks_release(self):
        def poison(paths):
            take = paths["roots"]["minimax-h3"] / "exports" / "approved.mp4"
            old = take.read_bytes()
            take.write_bytes(old[::-1])
        with self.assertRaisesRegex(RehearsalRejected, "synthetic product source changed"):
            run_rehearsal(after_package=poison)

    def test_vera_tracked_code_changed_blocks_release(self):
        def poison(paths):
            (paths["roots"]["vera"] / "src" / "native.txt").write_text("intrusive new code")
        with self.assertRaisesRegex(RehearsalRejected, "synthetic product source changed"):
            run_rehearsal(after_package=poison)

    def test_export_media_changed_after_pack_blocks_release(self):
        def poison(paths):
            file = paths["export"] / "video" / "approved.mp4"
            blob = file.read_bytes()
            file.write_bytes(blob[::-1])
        with self.assertRaisesRegex(RehearsalRejected, "operator-export source changed"):
            run_rehearsal(after_package=poison)

    def test_staged_exchange_media_mutation_fails_closed(self):
        def poison(paths):
            media = paths["package"] / "assets" / "SyntheticAsset001.mp4"
            media.write_bytes(b"not the expected SHA")
        with self.assertRaises(MediaProbeRejected):
            run_rehearsal(after_package=poison)

    def test_digest_locked_manifest_mutation_fails_closed(self):
        def poison(paths):
            manifest = paths["package"] / "manifests" / "shot.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["shotId"] = "ChangedShot"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(MediaProbeRejected):
            run_rehearsal(after_package=poison)

    def test_tampered_baseline_fails_even_when_sources_unchanged(self):
        def poison(paths):
            baseline = paths["baseline"]
            baseline.write_bytes(baseline.read_bytes() + b"\n")
        with self.assertRaisesRegex(IsolationAuditError, "digest mismatch"):
            run_rehearsal(after_package=poison)

    def test_no_real_products_imported_for_rehearsal(self):
        from inspect import getsource
        import bridge_rehearsal
        code = getsource(bridge_rehearsal)
        self.assertNotIn("import vera", code)
        self.assertNotIn("import minimax", code)
        self.assertNotIn("import pointflux_native", code)
        report = run_rehearsal()
        self.assertFalse(report["nativeProductsActuallyRun"])

    def test_cli_emits_only_sanitized_proof_and_exit_zero(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "bridge_rehearsal.py")],
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr[-1000:])
        data = json.loads(process.stdout)
        self.assertEqual(data["status"], "synthetic-bridge-rehearsal-pass")
        self.assertFalse(data["realThreeProjectE2EVerified"])
        self.assertNotIn("TemporaryDirectory", process.stdout)
        self.assertNotIn("ci@example.invalid", process.stdout)


class G2UnavailableToolTests(unittest.TestCase):
    def test_missing_ffprobe_causes_not_verified(self):
        original = shutil.which
        def missing(name):
            if name == "ffprobe":
                return None
            return original(name)
        with patch("bridge_rehearsal.shutil.which", side_effect=missing):
            with self.assertRaisesRegex(RehearsalUnavailable, "FFmpeg and FFprobe"):
                run_rehearsal()

    def test_missing_git_causes_not_verified(self):
        with patch("bridge_rehearsal.shutil.which", return_value=None):
            with self.assertRaisesRegex(RehearsalUnavailable, "Git is unavailable"):
                run_rehearsal()


if __name__ == "__main__":
    unittest.main()
