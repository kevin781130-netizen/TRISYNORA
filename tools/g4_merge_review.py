#!/usr/bin/env python3
"""G4 local-only review of seven incremental PR diffs. No merges, network or native writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

from g3_release_gate import ROOT, FreezeGateError, check as check_g3
from g3_release_gate import read_lock, _git as git, _fail as reject

REVIEW_PATH = "governance/g4-review-scope.json"
SHA40 = re.compile(r"^[a-f0-9]{40}$")
ALLOWED_STATUS = {"A", "M"}
CURRENT_FILES = {
    ".github/workflows/contract-tests.yml", "README.md",
    "docs/G3_RELEASE_REVIEW.md", "governance/g3-freeze.json",
    "tests/test_g3_release_gate.py", "tools/g3_release_gate.py",
    "docs/G4_MERGE_READINESS.md", "governance/g4-review-scope.json",
    "tests/test_g4_merge_review.py", "tools/g4_merge_review.py",
}
NATIVE_ROOTS = {
    "vera", "minimax-h3", "pointflux", "backend", "frontend", "src",
    "vendor", "node_modules", "upstream", "third_party",
}


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            reject("duplicate G4 manifest JSON property")
        out[key] = value
    return out


def read_scope(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        reject("G4 manifest missing, symlinked or too large")
    try:
        result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FreezeGateError("malformed G4 manifest JSON") from exc
    if not isinstance(result, dict):
        reject("G4 manifest must be JSON object")
    return result


def valid_path(value: Any) -> str:
    if (not isinstance(value, str) or not value or value.startswith("/")
            or "\\" in value or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        reject("unsafe/non-normalized Git path in review")
    return value


def valid_changes(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        reject("review scope needs a nonempty path/status dictionary")
    seen = set()
    for path, status in value.items():
        valid_path(path)
        if path.casefold() in seen:
            reject("casefold collision in review file list")
        seen.add(path.casefold())
        if status not in ALLOWED_STATUS:
            reject("deletions, renames and type changes require separate human approval")
    return value


def parse_git_diff(raw: bytes) -> dict[str, str]:
    """Decode Git name/status NUL output without accepting rename/delete."""
    if not raw or not raw.endswith(b"\0"):
        reject("malformed NUL-separated Git diff output")
    fields = raw[:-1].split(b"\0")
    if len(fields) % 2:
        reject("Git diff does not contain complete name/status pairs")
    out = {}
    for i in range(0, len(fields), 2):
        try:
            status = fields[i].decode("ascii")
            path = fields[i+1].decode("utf-8")
        except UnicodeError as exc:
            raise FreezeGateError("unsupported Git diff path encoding") from exc
        valid_path(path)
        if status not in ALLOWED_STATUS or path in out:
            reject("forbidden Git diff operation or duplicate path")
        out[path] = status
    return out


def diff(root: Path, older: str, newer: str) -> dict[str, str]:
    if not SHA40.fullmatch(older) or not SHA40.fullmatch(newer):
        reject("invalid pinned commit sha")
    return parse_git_diff(git(
        root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
        "--name-status", "-z", older, newer,
    ).stdout)


def validate_scope(scope: dict, g3: dict) -> None:
    expected = {
        "format", "repository", "policy", "evidenceType", "draftStackLength",
        "historicP1toP6", "parentP6Commit", "requiredCurrentPR7Changes",
        "forbiddenNativeProductWrites", "humanMergeApprovalRecorded",
        "productionReleaseAllowed", "liveGithubPrStatusVerifiedByThisFile",
    }
    if set(scope) != expected:
        reject("unreviewed G4 manifest properties")
    if (scope["format"] != "trisynora.g4-premerge-scope/v1"
            or scope["repository"] != "kevin781130-netizen/TRISYNORA"
            or scope["policy"] != "zero-cross-project-contamination"
            or scope["evidenceType"] != "operator-reviewed-historic-github-diff-manifest-no-live-api-auth"):
        reject("G4 review policy changed")
    if (type(scope["draftStackLength"]) is not int or scope["draftStackLength"] != 7
            or scope["forbiddenNativeProductWrites"] is not True
            or scope["humanMergeApprovalRecorded"] is not False
            or scope["productionReleaseAllowed"] is not False
            or scope["liveGithubPrStatusVerifiedByThisFile"] is not False):
        reject("unapproved merge or native release assertion")
    rows = scope["historicP1toP6"]
    locked = g3["pullRequests"]
    if not isinstance(rows, list) or len(rows) != 6:
        reject("all six frozen PR changes must be reviewed")
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {
                "pr", "baseCommit", "headCommit", "expectedChanges"}:
            reject("malformed G4 PR row")
        if type(row["pr"]) is not int or row["pr"] != i + 1:
            reject("PR review order mismatch")
        if (row["headCommit"] != locked[i]["headCommit"]
                or (i and row["baseCommit"] != rows[i-1]["headCommit"])
                or not SHA40.fullmatch(str(row["baseCommit"]))):
            reject("pinned G4 PR ancestry differs from G3 freeze")
        changes = valid_changes(row["expectedChanges"])
        if i and "CONSTITUTION.md" in changes:
            reject("foundation constitution cannot be altered by later feature PR")
        for path in changes:
            if path.split("/", 1)[0].casefold() in NATIVE_ROOTS:
                reject("native product implementation path found in PR scope")
    if scope["parentP6Commit"] != locked[-1]["headCommit"]:
        reject("G4 parent does not match G3 frozen PR #6")
    seventh = valid_changes(scope["requiredCurrentPR7Changes"])
    if set(seventh) != CURRENT_FILES:
        reject("unreviewed files in PR #7 scope")
    for path in CURRENT_FILES:
        kind = "M" if path in {
            "README.md", ".github/workflows/contract-tests.yml"
        } else "A"
        if seventh[path] != kind:
            reject("PR #7 file status does not match reviewed type")


def check(root: Path) -> dict:
    if root.is_symlink() or not root.is_dir():
        reject("review checkout must be a real directory")
    root = root.resolve(strict=True)
    g3_result = check_g3(root)
    frozen = read_lock(root / "governance/g3-freeze.json")
    scope = read_scope(root / REVIEW_PATH)
    validate_scope(scope, frozen)
    counts = {}
    for row in scope["historicP1toP6"]:
        actual = diff(root, row["baseCommit"], row["headCommit"])
        if actual != row["expectedChanges"]:
            reject("frozen PR scope differs from Git diff")
        counts[str(row["pr"])] = len(actual)
    head = git(root, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    current = diff(root, scope["parentP6Commit"], head)
    if current != scope["requiredCurrentPR7Changes"]:
        reject("PR #7 changes differ from pinned review manifest")
    return {
        "format": "trisynora.g4-premerge-check/v1",
        "status": "review-scope-consistent",
        "historicPrDiffFiles": counts,
        "currentPr7Files": len(current),
        "g3Status": g3_result["status"],
        "githubMergeabilityActuallyVerified": False,
        "prHumanReviewApproved": False,
        "nativeProductsRun": False,
        "nativeRuntimeE2EVerified": False,
        "mergesExecuted": False,
        "productionReleaseAllowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    a = parser.parse_args()
    try:
        result = check(a.root)
    except (FreezeGateError, OSError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
