"""G4 premerge evidence lock tests; synthetic invalid changes never touch native repos."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from g3_release_gate import FreezeGateError, read_lock
from g4_merge_review import (
    check, read_scope, validate_scope, valid_changes, parse_git_diff, diff,
)


class G4ReviewScopeTests(unittest.TestCase):
    def setUp(self):
        self.scope = read_scope(ROOT / "governance/g4-review-scope.json")
        self.freeze = read_lock(ROOT / "governance/g3-freeze.json")

    def test_actual_checked_out_7_pr_stack_is_scoped(self):
        result = check(ROOT)
        self.assertEqual(result["status"], "review-scope-consistent")
        self.assertEqual(result["g3Status"], "g3-foundation-freeze-verified")
        self.assertEqual(result["historicPrDiffFiles"], {
            "1": 30, "2": 3, "3": 3, "4": 4, "5": 3, "6": 4,
        })
        self.assertEqual(result["currentPr7Files"], 10)
        self.assertFalse(result["prHumanReviewApproved"])
        self.assertFalse(result["mergesExecuted"])
        self.assertFalse(result["productionReleaseAllowed"])
        self.assertFalse(result["nativeRuntimeE2EVerified"])
        self.assertFalse(result["githubMergeabilityActuallyVerified"])

    def test_exact_changes_in_current_diff_have_no_native_roots(self):
        current = self.scope["requiredCurrentPR7Changes"]
        self.assertEqual(current["README.md"], "M")
        self.assertIn("tools/g4_merge_review.py", current)
        self.assertIn("governance/g4-review-scope.json", current)
        self.assertNotIn("CONSTITUTION.md", current)

    def test_operator_approval_is_not_inferred(self):
        for key in (
            "forbiddenNativeProductWrites", "humanMergeApprovalRecorded",
            "productionReleaseAllowed", "liveGithubPrStatusVerifiedByThisFile",
        ):
            with self.subTest(key=key):
                scope = copy.deepcopy(self.scope)
                scope[key] = not scope[key]
                with self.assertRaisesRegex(FreezeGateError, "unapproved merge"):
                    validate_scope(scope, self.freeze)

    def test_reordered_or_missing_historic_pr_is_rejected(self):
        altered = copy.deepcopy(self.scope)
        altered["historicP1toP6"].reverse()
        with self.assertRaises(FreezeGateError):
            validate_scope(altered, self.freeze)
        altered = copy.deepcopy(self.scope)
        altered["historicP1toP6"].pop()
        with self.assertRaisesRegex(FreezeGateError, "six"):
            validate_scope(altered, self.freeze)

    def test_foreign_code_cannot_be_injected_into_scopes(self):
        for forbidden in ("vera/engine.py", "minimax-h3/runtime.py", "pointflux/src/foo.ts",
                          "backend/server.py", "vendor/h3.py"):
            with self.subTest(path=forbidden):
                scope = copy.deepcopy(self.scope)
                scope["historicP1toP6"][2]["expectedChanges"][forbidden] = "A"
                with self.assertRaisesRegex(FreezeGateError, "native product"):
                    validate_scope(scope, self.freeze)

    def test_constitution_cannot_change_in_later_pr(self):
        scope = copy.deepcopy(self.scope)
        scope["historicP1toP6"][4]["expectedChanges"]["CONSTITUTION.md"] = "M"
        with self.assertRaisesRegex(FreezeGateError, "constitution"):
            validate_scope(scope, self.freeze)

    def test_extra_new_file_in_current_review_fails_closed(self):
        scope = copy.deepcopy(self.scope)
        scope["requiredCurrentPR7Changes"]["tools/accidental_runtime.py"] = "A"
        with self.assertRaisesRegex(FreezeGateError, "unreviewed files"):
            validate_scope(scope, self.freeze)

    def test_unexpected_existing_file_type_does_not_pass(self):
        scope = copy.deepcopy(self.scope)
        scope["requiredCurrentPR7Changes"]["README.md"] = "A"
        with self.assertRaisesRegex(FreezeGateError, "status"):
            validate_scope(scope, self.freeze)

    def test_modified_g3_frozen_commit_detected(self):
        scope = copy.deepcopy(self.scope)
        scope["historicP1toP6"][5]["headCommit"] = "0" * 40
        with self.assertRaisesRegex(FreezeGateError, "frozen"):
            validate_scope(scope, self.freeze)

    def test_missing_current_lock_field_detected(self):
        scope = copy.deepcopy(self.scope)
        scope.pop("policy")
        with self.assertRaisesRegex(FreezeGateError, "unreviewed G4"):
            validate_scope(scope, self.freeze)

    def test_git_status_parser_regular_pairs(self):
        self.assertEqual(
            parse_git_diff(b"A\0docs/new.md\0M\0README.md\0"),
            {"docs/new.md": "A", "README.md": "M"},
        )

    def test_git_status_parser_rejects_delete_or_rename(self):
        for raw in (b"D\0CONSTITUTION.md\0", b"R100\0before\0after\0",
                    b"T\0docs/file.md\0"):
            with self.subTest(raw=raw):
                with self.assertRaises(FreezeGateError):
                    parse_git_diff(raw)

    def test_git_status_parser_rejects_traversal(self):
        for raw in (b"A\0../outside\0", b"A\0src//bad.py\0",
                    b"A\0/absolute/file\0", b"A\0nested\\backslash\0"):
            with self.subTest(raw=raw):
                with self.assertRaises(FreezeGateError):
                    parse_git_diff(raw)

    def test_git_status_parser_rejects_malformed_result(self):
        for raw in (b"", b"A\0README.md", b"A\0", b"\0README.md\0"):
            with self.subTest(raw=raw):
                with self.assertRaises(FreezeGateError):
                    parse_git_diff(raw)

    def test_manifest_json_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "g4.json"
            path.write_text('{"format":"a","format":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(FreezeGateError, "duplicate"):
                read_scope(path)

    def test_review_manifest_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "scope.json"
            path.write_text("{}", encoding="utf-8")
            alias = Path(d) / "alias.json"
            try:
                alias.symlink_to(path)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(FreezeGateError, "symlink"):
                read_scope(alias)

    def test_git_diff_on_real_frozen_pr(self):
        first = self.scope["historicP1toP6"][1]
        got = diff(ROOT, first["baseCommit"], first["headCommit"])
        self.assertEqual(got, first["expectedChanges"])
        self.assertEqual(len(got), 3)

    def test_g4_does_not_use_git_remote_or_api(self):
        import inspect
        import g4_merge_review
        source = inspect.getsource(g4_merge_review)
        self.assertNotIn("github.com/", source)
        self.assertNotIn("merge_pull_request", source)
        self.assertNotIn("os.chdir", source)

    def test_unapproved_rename_requires_review(self):
        changes = dict(self.scope["requiredCurrentPR7Changes"])
        changes["README.md"] = "R100"
        with self.assertRaisesRegex(FreezeGateError, "deletions"):
            valid_changes(changes)


if __name__ == "__main__":
    unittest.main()
