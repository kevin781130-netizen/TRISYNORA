"""Cross-envelope preflight must reject bad links and never grant authority."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from preflight_exchange import preflight, PreflightError  # noqa: E402


class TestExchangePreflight(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.docs = {}
        self.manifests = {}
        for kind in ("capability", "asset", "shot", "job", "evidence"):
            example = json.loads((ROOT / "examples" / "v1" / f"{kind}.json").read_text(encoding="utf-8"))
            if kind == "evidence":
                example["subject"]["artifactSha256"] = "a" * 64
            self.docs[kind] = example
            self.manifests[kind] = [f"manifests/{kind}.json"]
        (self.root / "manifests").mkdir()
        self.save()

    def save(self):
        for kind, body in self.docs.items():
            (self.root / self.manifests[kind][0]).write_text(json.dumps(body), encoding="utf-8")

    def run_preflight(self, **kwargs):
        return preflight(self.root, self.manifests, **kwargs)

    def test_valid_links_are_metadata_only(self):
        result = self.run_preflight()
        self.assertEqual(result["status"], "manifest-links-consistent")
        self.assertEqual(sum(result["envelopes"].values()), 5)
        self.assertFalse(result["receiverAuthorized"])
        self.assertFalse(result["crossProductE2EVerified"])
        self.assertEqual(result["assetBytesChecked"], 0)

    def test_optional_real_sha_check(self):
        payload = b"synthetic-nonvideo-bytes"
        (self.root / "assets").mkdir()
        (self.root / "assets" / "take.mp4").write_bytes(payload)
        media = self.docs["asset"]["media"]
        media["path"] = "assets/take.mp4"
        media["sha256"] = hashlib.sha256(payload).hexdigest()
        media["sizeBytes"] = len(payload)
        self.docs["evidence"]["subject"]["artifactSha256"] = media["sha256"]
        self.save()
        r = self.run_preflight(verify_bytes=True)
        self.assertEqual(r["assetBytesChecked"], 1)
        self.assertFalse(r["mediaSemanticsVerified"])

    def test_missing_shot_asset(self):
        self.docs["shot"]["assetIds"] = ["asset_nonexistent"]
        self.save()
        with self.assertRaisesRegex(PreflightError, "shot refers"):
            self.run_preflight()

    def test_missing_job_input(self):
        self.docs["job"]["inputArtifactIds"] = ["asset_nonexistent"]
        self.save()
        with self.assertRaisesRegex(PreflightError, "job refers"):
            self.run_preflight()

    def test_bad_evidence_job_reference(self):
        self.docs["evidence"]["subject"]["jobId"] = "missing_job"
        self.save()
        with self.assertRaisesRegex(PreflightError, "unknown job"):
            self.run_preflight()

    def test_bad_evidence_digest(self):
        self.docs["evidence"]["subject"]["artifactSha256"] = "c" * 64
        self.save()
        with self.assertRaisesRegex(PreflightError, "unknown artifact digest"):
            self.run_preflight()

    def test_bad_evidence_domain_origin(self):
        self.docs["evidence"]["origin"]["product"] = "minimax-h3"
        self.save()
        with self.assertRaisesRegex(PreflightError, "not target product"):
            self.run_preflight()

    def test_duplicate_source_asset_id(self):
        other = self.root / "manifests" / "duplicate.json"
        other.write_text(json.dumps(self.docs["asset"]), encoding="utf-8")
        self.manifests["asset"].append("manifests/duplicate.json")
        with self.assertRaisesRegex(PreflightError, "duplicate asset"):
            self.run_preflight()

    def test_duplicate_manifest_path(self):
        self.manifests["asset"].append(self.manifests["asset"][0])
        with self.assertRaisesRegex(PreflightError, "same manifest"):
            self.run_preflight()

    def test_missing_or_unsafe_manifest_path(self):
        for bad in ("../foreign.json", "/etc/passwd", "missing.json"):
            with self.subTest(path=bad):
                m = copy.deepcopy(self.manifests)
                m["shot"] = [bad]
                with self.assertRaises(PreflightError):
                    preflight(self.root, m)

    def test_bad_schema_fails_closed(self):
        self.docs["asset"]["authorization"] = "superuser"
        self.save()
        with self.assertRaisesRegex(PreflightError, "invalid asset"):
            self.run_preflight()

    def test_no_envelopes_is_not_success(self):
        with self.assertRaisesRegex(PreflightError, "no envelopes"):
            preflight(self.root, {})

    def test_unknown_category_fails(self):
        with self.assertRaisesRegex(PreflightError, "unknown manifest"):
            preflight(self.root, {"foreign": ["x.json"]})

    def test_rejects_duplicate_json_fields(self):
        (self.root / "manifests" / "asset.json").write_text('{"contract":"trisynora.asset/v1","contract":"x"}', encoding="utf-8")
        with self.assertRaisesRegex(PreflightError, "malformed"):
            self.run_preflight()

    def test_rejects_symlink_manifest(self):
        real = self.root / self.manifests["shot"][0]
        sym = self.root / "manifests" / "sym.json"
        try:
            sym.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        self.manifests["shot"] = ["manifests/sym.json"]
        with self.assertRaisesRegex(PreflightError, "unsafe"):
            self.run_preflight()

    def test_byte_verification_requires_declared_asset(self):
        self.manifests["asset"] = []
        with self.assertRaisesRegex(PreflightError, "requires at least one"):
            self.run_preflight(verify_bytes=True)


if __name__ == "__main__":
    unittest.main()
