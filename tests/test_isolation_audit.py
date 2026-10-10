"""Three-product G1 snapshot/verify: synthetic Git roots only; never native repos."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from isolation_audit import IsolationAuditError, capture, verify, make_snapshot


@unittest.skipUnless(shutil.which("git"), "Git is required to audit indexed source files")
class IsolationAuditTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base = Path(t.name)
        self.roots = {}
        self.files = {}
        for product in ("vera", "minimax-h3", "pointflux"):
            root = self.base / product
            root.mkdir()
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "ci@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Fixture"], check=True)
            (root / "app").mkdir()
            f = root / "app" / "core.txt"
            f.write_text(f"{product} - independent application source", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "app/core.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            self.roots[product] = root
            self.files[product] = f
        (self.roots["minimax-h3"] / "exports").mkdir()
        self.h3_take = self.roots["minimax-h3"] / "exports" / "approved-take.mp4"
        self.h3_take.write_bytes(b"synthetic-not-a-video")
        (self.roots["pointflux"] / "projects").mkdir()
        self.pf_project = self.roots["pointflux"] / "projects" / "scene.json"
        self.pf_project.write_text('{"synthetic": true}', encoding="utf-8")
        self.watches = {
            "vera": [],
            "minimax-h3": ["exports/approved-take.mp4"],
            "pointflux": ["projects/scene.json"],
        }
        self.baseline = self.base / "audit-baseline.json"

    def _capture(self):
        return capture(self.roots, self.watches, self.baseline)

    def _verify(self, captured):
        return verify(self.roots, self.baseline, captured["baselineSha256"])

    def test_unchanged_roots_including_explicit_untracked_media(self):
        captured = self._capture()
        self.assertEqual(captured["status"], "baseline-created")
        self.assertRegex(captured["baselineSha256"], r"^[0-9a-f]{64}$")
        outcome = self._verify(captured)
        self.assertEqual(outcome["status"], "unchanged-within-scope")
        self.assertFalse(outcome["unwatchedUntrackedFilesIncluded"])
        self.assertFalse(outcome["nativeRuntimeIndependenceVerified"])
        self.assertFalse(outcome["crossProductE2EVerified"])
        self.assertEqual(captured["trackedAndWatchedCounts"],
                         {"vera": 1, "minimax-h3": 2, "pointflux": 2})

    def test_tracked_h3_edit_detected_without_mutating_others(self):
        baseline = self._capture()
        self.files["minimax-h3"].write_text("tampered tracked source", encoding="utf-8")
        result = self._verify(baseline)
        self.assertEqual(result["status"], "changed-within-scope")
        self.assertGreater(result["products"]["minimax-h3"]["pathDifferences"], 0)
        self.assertEqual(result["products"]["vera"]["pathDifferences"], 0)
        self.assertEqual(result["products"]["pointflux"]["pathDifferences"], 0)

    def test_changed_h3_approved_take_is_detected(self):
        baseline = self._capture()
        self.h3_take.write_bytes(b"changed native take same-size?"[:21])
        self.assertEqual(self._verify(baseline)["status"], "changed-within-scope")

    def test_same_size_mutation_detected_by_sha(self):
        baseline = self._capture()
        data = self.pf_project.read_bytes()
        self.pf_project.write_bytes(data[::-1])
        self.assertEqual(self.pf_project.stat().st_size, len(data))
        outcome = self._verify(baseline)
        self.assertGreater(outcome["products"]["pointflux"]["pathDifferences"], 0)

    def test_missing_watched_native_project_is_detected(self):
        baseline = self._capture()
        self.pf_project.unlink()
        result = self._verify(baseline)
        self.assertEqual(result["status"], "changed-within-scope")
        self.assertEqual(result["products"]["pointflux"]["pathDifferences"], 1)

    def test_added_indexed_source_is_detected(self):
        baseline = self._capture()
        another = self.roots["vera"] / "app" / "added.txt"
        another.write_text("new indexed file")
        subprocess.run(["git", "-C", str(self.roots["vera"]), "add", "app/added.txt"], check=True)
        result = self._verify(baseline)
        self.assertGreater(result["products"]["vera"]["pathDifferences"], 0)

    def test_head_commit_changes_even_if_file_bytes_do_not(self):
        baseline = self._capture()
        subprocess.run([
            "git", "-C", str(self.roots["vera"]), "commit", "--allow-empty", "-qm", "new commit"
        ], check=True)
        result = self._verify(baseline)
        self.assertTrue(result["products"]["vera"]["headChanged"])
        self.assertEqual(result["products"]["vera"]["pathDifferences"], 0)
        self.assertEqual(result["status"], "changed-within-scope")

    def test_unwatched_untracked_changes_are_outside_scope(self):
        baseline = self._capture()
        (self.roots["vera"] / "other-secret.txt").write_text("UNTRACKED AND NOT WATCHED")
        result = self._verify(baseline)
        self.assertEqual(result["status"], "unchanged-within-scope")
        self.assertFalse(result["unwatchedUntrackedFilesIncluded"])

    def test_tampered_baseline_rejected_with_external_sha(self):
        baseline = self._capture()
        self.baseline.write_bytes(self.baseline.read_bytes() + b" ")
        with self.assertRaisesRegex(IsolationAuditError, "digest mismatch"):
            self._verify(baseline)

    def test_duplicate_json_keys_in_baseline_rejected_even_if_rehashed(self):
        self._capture()
        self.baseline.write_text('{"format":"x","format":"y"}', encoding="utf-8")
        digest = hashlib.sha256(self.baseline.read_bytes()).hexdigest()
        with self.assertRaisesRegex(IsolationAuditError, "duplicate"):
            verify(self.roots, self.baseline, digest)

    def test_reject_unknown_baseline_policy(self):
        self._capture()
        value = json.loads(self.baseline.read_text(encoding="utf-8"))
        value["nativeRuntimeIndependenceVerified"] = True
        self.baseline.write_text(json.dumps(value), encoding="utf-8")
        digest = hashlib.sha256(self.baseline.read_bytes()).hexdigest()
        with self.assertRaisesRegex(IsolationAuditError, "malformed baseline policy"):
            verify(self.roots, self.baseline, digest)

    def test_reject_output_inside_h3_root(self):
        with self.assertRaisesRegex(IsolationAuditError, "outside all native"):
            capture(self.roots, self.watches, self.roots["minimax-h3"] / "BAD.json")
        self.assertFalse((self.roots["minimax-h3"] / "BAD.json").exists())

    def test_reject_baseline_overwrite(self):
        self._capture()
        existing = self.baseline.read_bytes()
        with self.assertRaisesRegex(IsolationAuditError, "overwrite forbidden"):
            self._capture()
        self.assertEqual(self.baseline.read_bytes(), existing)

    def test_reject_reused_product_root(self):
        roots = dict(self.roots)
        roots["vera"] = roots["pointflux"]
        with self.assertRaisesRegex(IsolationAuditError, "must not overlap"):
            make_snapshot(roots, self.watches)

    def test_reject_non_git_product_root(self):
        roots = dict(self.roots)
        roots["vera"] = self.base
        with self.assertRaises(IsolationAuditError):
            make_snapshot(roots, self.watches)

    def test_reject_absent_watched_take_during_capture(self):
        self.h3_take.unlink()
        with self.assertRaisesRegex(IsolationAuditError, "missing indexed or watched"):
            make_snapshot(self.roots, self.watches)

    def test_reject_path_traversal_in_watch_list(self):
        for path in ("../outside", "/absolute/path", "C:/drive/file", "nested//file", "a/./b",
                     "a/../b", "a\\b", "a\nb"):
            with self.subTest(path=path):
                watches = dict(self.watches, vera=[path])
                with self.assertRaises(IsolationAuditError):
                    make_snapshot(self.roots, watches)

    def test_reject_duplicate_watched_file_path(self):
        watches = dict(self.watches, vera=["app/core.txt", "app/core.txt"])
        with self.assertRaisesRegex(IsolationAuditError, "duplicate"):
            make_snapshot(self.roots, watches)

    def test_reject_watched_symlink_without_following(self):
        real = self.pf_project
        link = self.roots["pointflux"] / "projects" / "link.json"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symbolic links unavailable")
        watches = dict(self.watches, pointflux=["projects/link.json"])
        with self.assertRaisesRegex(IsolationAuditError, "symlink"):
            make_snapshot(self.roots, watches)

    def test_reject_baseline_symlink(self):
        baseline = self._capture()
        alias = self.base / "baseline-link.json"
        try:
            alias.symlink_to(self.baseline)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(IsolationAuditError, "symlink"):
            verify(self.roots, alias, baseline["baselineSha256"])

    def test_reject_invalid_expected_baseline_sha(self):
        self._capture()
        with self.assertRaisesRegex(IsolationAuditError, "expected baseline SHA"):
            verify(self.roots, self.baseline, "abc")

    def test_no_native_writes_on_verify(self):
        captured = self._capture()
        before = {p: (f.read_bytes(), f.stat().st_mtime_ns) for p, f in self.files.items()}
        media = (self.h3_take.read_bytes(), self.pf_project.read_bytes())
        self._verify(captured)
        for product, (content, modified) in before.items():
            self.assertEqual(self.files[product].read_bytes(), content)
            self.assertEqual(self.files[product].stat().st_mtime_ns, modified)
        self.assertEqual((self.h3_take.read_bytes(), self.pf_project.read_bytes()), media)


if __name__ == "__main__":
    unittest.main()
