"""G3 freeze checks only TRISYNORA's local Git index and historic evidence lock."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from g3_release_gate import (
    FreezeGateError, check, read_lock, validate_lock, _index_paths, _assert_ancestry,
)


class G3FreezeGateTests(unittest.TestCase):
    def setUp(self):
        self.lock = read_lock(ROOT / "governance" / "g3-freeze.json")

    def test_frozen_evidence_six_prs_valid(self):
        validate_lock(self.lock)
        prs = self.lock["pullRequests"]
        self.assertEqual([x["number"] for x in prs], [1, 2, 3, 4, 5, 6])
        self.assertEqual(prs[-1]["historicRecordedTests"], 113)

    def test_usable_full_checkout_fails_closed_on_real_prod(self):
        status = check(ROOT)
        self.assertEqual(status["status"], "g3-foundation-freeze-verified")
        self.assertEqual(status["historicPassedCIRunsRecorded"], 6)
        self.assertEqual(status["frozenContractTestCount"], 113)
        self.assertTrue(status["gitAncestryChecked"])
        self.assertTrue(status["staticHistoricCIOnly"])
        self.assertFalse(status["productionReleaseAllowed"])
        self.assertFalse(status["realCrossProductE2EVerified"])
        self.assertFalse(status["distributionLicenseCleared"])
        self.assertFalse(status["reviewMergeOwnerApproved"])

    def test_no_actual_product_repo_during_check(self):
        with patch("g3_release_gate.subprocess.run", wraps=None) as spy:
            # Validate JSON only: no command, network, or native product writes.
            validate_lock(self.lock)
            spy.assert_not_called()

    def test_release_authorization_cannot_be_forged(self):
        for field in (
            "nativeRuntimeIntegrated", "realCrossProductE2EVerified",
            "ownerApprovedMerge", "publicationLicenseFinalized", "productionReleaseAllowed",
        ):
            with self.subTest(field=field):
                lock = copy.deepcopy(self.lock)
                lock[field] = True
                with self.assertRaisesRegex(FreezeGateError, "unauthorized release"):
                    validate_lock(lock)

    def test_wrong_constitution_cannot_be_locked(self):
        lock = copy.deepcopy(self.lock)
        lock["policy"] = "fully-shared-state"
        with self.assertRaisesRegex(FreezeGateError, "constitution"):
            validate_lock(lock)

    def test_unknown_contract_version_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["format"] = "trisynora.g3-foundation-freeze/v2"
        with self.assertRaisesRegex(FreezeGateError, "unknown freeze"):
            validate_lock(lock)

    def test_wrong_repository_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["repository"] = "kevin781130-netizen/PointFlux"
        with self.assertRaisesRegex(FreezeGateError, "wrong repository"):
            validate_lock(lock)

    def test_wrong_native_product_count_and_order_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["upstreamNativeProducts"] = ["pointflux", "vera", "minimax-h3"]
        with self.assertRaisesRegex(FreezeGateError, "project owner"):
            validate_lock(lock)

    def test_incomplete_or_reordered_review_stack_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["reviewOrder"] = [6, 5, 4, 3, 2, 1]
        with self.assertRaisesRegex(FreezeGateError, "review order"):
            validate_lock(lock)
        lock = copy.deepcopy(self.lock)
        lock["pullRequests"] = lock["pullRequests"][:-1]
        with self.assertRaisesRegex(FreezeGateError, "exactly six"):
            validate_lock(lock)

    def test_p1_branch_dependency_reversal_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["pullRequests"][3]["baseBranch"] = "main"
        with self.assertRaisesRegex(FreezeGateError, "dependency"):
            validate_lock(lock)

    def test_head_commit_corruption_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["pullRequests"][1]["headCommit"] = "not-a-SHA"
        with self.assertRaisesRegex(FreezeGateError, "head/base"):
            validate_lock(lock)

    def test_historic_ci_must_be_explicit_but_is_not_live(self):
        lock = copy.deepcopy(self.lock)
        lock["sourceOfEvidence"] = "Live GitHub CI"
        with self.assertRaisesRegex(FreezeGateError, "historic"):
            validate_lock(lock)
        lock = copy.deepcopy(self.lock)
        lock["pullRequests"][2]["historicReportedConclusion"] = "not-verified"
        with self.assertRaisesRegex(FreezeGateError, "CI run"):
            validate_lock(lock)

    def test_six_historic_test_counts_immutable(self):
        lock = copy.deepcopy(self.lock)
        lock["pullRequests"][-1]["historicRecordedTests"] = 999
        with self.assertRaisesRegex(FreezeGateError, "test totals"):
            validate_lock(lock)

    def test_any_missing_required_family_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["contractFamilies"].remove("shot")
        with self.assertRaisesRegex(FreezeGateError, "contract families"):
            validate_lock(lock)

    def test_baseline_not_marked_production_ready(self):
        self.assertFalse(self.lock["productionReleaseAllowed"])
        self.assertFalse(self.lock["ownerApprovedMerge"])
        self.assertFalse(self.lock["realCrossProductE2EVerified"])
        self.assertGreaterEqual(len(self.lock["unverifiedMandatoryGates"]), 7)

    def test_index_contains_only_contract_implementation_paths(self):
        paths = _index_paths(ROOT)
        self.assertIn("CONSTITUTION.md", paths)
        self.assertIn("tools/pointflux_media_probe.py", paths)
        self.assertIn("governance/g3-freeze.json", paths)
        self.assertTrue(all(not x.startswith("pointflux/") for x in paths))
        self.assertTrue(all(not x.startswith("minimax-h3/") for x in paths))
        self.assertTrue(all(not x.startswith("vera/") for x in paths))

    def test_index_guards_detect_foreign_roots_and_gitlinks(self):
        from g3_release_gate import _git
        from unittest.mock import Mock
        # Mock only ls-files output, not real native products or network.
        for payload in (
            b"100644 " + b"a" * 40 + b" 0\tsrc/engine.py\0",
            b"160000 " + b"a" * 40 + b" 0\ttools/vendor_product\0",
            b"120000 " + b"a" * 40 + b" 0\tdocs/link.md\0",
        ):
            with self.subTest(payload=payload[:7]):
                with patch("g3_release_gate._git", return_value=Mock(stdout=payload)):
                    with self.assertRaises(FreezeGateError):
                        _index_paths(ROOT)

    def test_missing_ancestor_or_head_detected(self):
        invalid = "0" * 40
        with self.assertRaisesRegex(FreezeGateError, "commit chain"):
            _assert_ancestry(ROOT, invalid, self.lock["pullRequests"][-1]["headCommit"])

    def test_duplicate_json_key_in_freeze_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frozen.json"
            path.write_text('{"format":"v1","format":"v2"}', encoding="utf-8")
            with self.assertRaisesRegex(FreezeGateError, "duplicate"):
                read_lock(path)

    def test_symlinked_lock_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.json"
            path.write_text("{}", encoding="utf-8")
            link = Path(folder) / "alias.json"
            try:
                link.symlink_to(path)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(FreezeGateError, "linked"):
                read_lock(link)

    def test_not_an_actual_three_app_approval(self):
        status = check(ROOT)
        self.assertFalse(status["nativeProductsRun"])
        self.assertFalse(status["productionReleaseAllowed"])
        self.assertGreater(status["outstandingManualGates"], 0)


if __name__ == "__main__":
    unittest.main()
