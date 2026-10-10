#!/usr/bin/env python3
"""G3 OFFLINE release freeze gate, not a native three-app release approval.

Verifies a pinned six-PR historic evidence chain against local Git ancestry,
basic repo boundaries and constitution. NEVER queries a private product repo,
uses GitHub credentials, modifies Git refs, creates tags, or merges pull requests.
A PASS means only 'TRISYNORA draft release evidence is coherent'.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = "governance/g3-freeze.json"
EXPECTED_FAMILIES = ("asset", "capability", "evidence", "job", "shot")
EXPECTED_NAMES = ("vera", "minimax-h3", "pointflux")
ALLOWED_ROOT_FILES = {
    "README.md", "AGENTS.md", "CONSTITUTION.md", "requirements-dev.txt", "LICENSE",
}
ALLOWED_DIRECTORIES = {
    "docs", "examples", "schemas", "tools", "tests", "scripts", "governance",
    ".github",
}
BAD_REPOSITORY_DIRECTORIES = {
    "vera", "minimax-h3", "pointflux", "backend", "frontend", "src",
    "vendor", "third_party", "node_modules", "upstream",
}
HEX40 = re.compile(r"^[a-f0-9]{40}$")
MAX_LOCK_BYTES = 131072
MAX_INDEX_BYTES = 2000000


class FreezeGateError(ValueError):
    pass


def _fail(message: str) -> None:
    raise FreezeGateError(message)


def _distinct_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate JSON lock key")
        result[key] = value
    return result


def read_lock(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOCK_BYTES:
        _fail("freeze lock missing, linked or too large")
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_distinct_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FreezeGateError("invalid release-lock JSON") from exc
    if not isinstance(data, dict):
        _fail("freeze lock must be object")
    return data


def validate_lock(lock: dict[str, Any]) -> None:
    """Validate static claims without mistaking them for current GitHub state."""
    if lock.get("format") != "trisynora.g3-foundation-freeze/v1":
        _fail("unknown freeze format")
    if lock.get("policy") != "zero-cross-project-contamination":
        _fail("highest constitution was not preserved")
    if lock.get("repository") != "kevin781130-netizen/TRISYNORA":
        _fail("freeze lock targets wrong repository")
    if lock.get("sourceOfEvidence") != (
        "verified GitHub Actions records captured during six PR acceptance reviews; "
        "static historic facts, not a live check"
    ):
        _fail("CI evidence must be described as historic rather than live")
    if lock.get("upstreamNativeProducts") != list(EXPECTED_NAMES):
        _fail("unexpected or missing native project owner list")
    if lock.get("reviewOrder") != [1, 2, 3, 4, 5, 6]:
        _fail("required stacked human review order changed")
    if lock.get("contractFamilies") != list(EXPECTED_FAMILIES):
        _fail("five neutral contract families changed without review")
    for field in ("nativeRuntimeIntegrated", "realCrossProductE2EVerified",
                  "ownerApprovedMerge", "publicationLicenseFinalized",
                  "productionReleaseAllowed"):
        if lock.get(field) is not False:
            _fail(f"unverified/unauthorized release assertion: {field}")
    blockers = lock.get("unverifiedMandatoryGates")
    if not isinstance(blockers, list) or len(blockers) < 7:
        _fail("unverified production gates cannot be omitted")
    prs = lock.get("pullRequests")
    if not isinstance(prs, list) or len(prs) != 6:
        _fail("freeze must pin exactly six reviewed PRs")
    for i, entry in enumerate(prs):
        if not isinstance(entry, dict) or entry.get("number") != i + 1:
            _fail("pull request sequence mismatch")
        if (not isinstance(entry.get("branch"), str)
                or not isinstance(entry.get("baseBranch"), str)
                or not HEX40.fullmatch(str(entry.get("headCommit", "")))):
            _fail("PR frozen head/base metadata invalid")
        if (type(entry.get("githubActionsRun")) is not int
                or entry["githubActionsRun"] < 1
                or entry.get("historicReportedConclusion") != "success"
                or type(entry.get("historicRecordedTests")) is not int
                or entry["historicRecordedTests"] <= 0):
            _fail("historic CI run evidence missing or misstated")
        if i == 0:
            if entry["baseBranch"] != "main":
                _fail("PR #1 must target main")
        elif entry["baseBranch"] != prs[i-1]["branch"]:
            _fail("stacked PR dependency broken")
    if [x["historicRecordedTests"] for x in prs] != [36, 49, 63, 78, 100, 113]:
        _fail("historical CI test totals were altered")
    if len({x["headCommit"] for x in prs}) != 6:
        _fail("frozen PR revisions must be distinct")


def _git(root: Path, *args: str, allow_nonzero: bool = False) -> subprocess.CompletedProcess[bytes]:
    try:
        p = subprocess.run(
            ["git", "-C", str(root), *args], check=False, capture_output=True,
            timeout=20, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FreezeGateError("local Git evidence unavailable") from exc
    if not allow_nonzero and p.returncode:
        _fail("Git evidence command failed")
    if len(p.stdout) > MAX_INDEX_BYTES:
        _fail("Git evidence output exceeds limit")
    return p


def _assert_ancestry(root: Path, older: str, newer: str) -> None:
    p = _git(root, "merge-base", "--is-ancestor", older, newer, allow_nonzero=True)
    if p.returncode != 0:
        _fail("frozen PR commit chain not present in the checkout")


def _index_paths(root: Path) -> list[str]:
    p = _git(root, "ls-files", "--cached", "--stage", "-z")
    result = []
    for raw in p.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            info, path_bytes = raw.split(b"\t", 1)
            mode = info.split(b" ", 1)[0].decode("ascii")
            path = path_bytes.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise FreezeGateError("unsupported Git-index entry") from exc
        if mode not in {"100644", "100755"}:
            _fail("symlink or Git submodule detected in the release index")
        if (not path or path.startswith("/") or "\\" in path
                or any(v in ("", ".", "..") for v in path.split("/"))):
            _fail("unsafe repository path in release index")
        components = path.split("/")
        if len(components) == 1:
            if path not in ALLOWED_ROOT_FILES:
                _fail("unexpected root-level implementation file")
        elif (components[0] not in ALLOWED_DIRECTORIES
              or any(v.casefold() in BAD_REPOSITORY_DIRECTORIES for v in components)):
            _fail("foreign product implementation location in release index")
        result.append(path)
    if len(set(result)) != len(result):
        _fail("duplicate release index path")
    return result


def check(root: Path, lock: dict[str, Any] | None = None) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        _fail("release root must be an existing directory")
    root = root.resolve(strict=True)
    file = root / LOCK_PATH
    record = read_lock(file) if lock is None else lock
    validate_lock(record)
    top = _git(root, "rev-parse", "--show-toplevel").stdout.decode("utf-8").strip()
    if Path(top).resolve() != root:
        _fail("release check requires TRISYNORA Git top-level directory")
    paths = _index_paths(root)
    required = {
        "README.md", "AGENTS.md", "CONSTITUTION.md",
        "governance/g3-freeze.json", "schemas/v1/asset.schema.json",
        "schemas/v1/capability.schema.json", "schemas/v1/evidence.schema.json",
        "schemas/v1/job.schema.json", "schemas/v1/shot.schema.json",
        "tools/bridge_rehearsal.py", "tools/isolation_audit.py",
        "tools/pointflux_media_probe.py", ".github/workflows/contract-tests.yml",
    }
    if not required.issubset(set(paths)):
        _fail("mandatory constitutional/contract/acceptance files missing")
    constitution = (root / "CONSTITUTION.md").read_text(encoding="utf-8")
    for term in ("Zero Cross-Project Contamination", "No TRISYNORA task", "Standalone"):
        if term not in constitution:
            _fail("highest constitutional text is incomplete")
    if (root / ".gitmodules").exists():
        _fail("release must not embed native repositories as submodules")
    prs = record["pullRequests"]
    for i in range(1, len(prs)):
        _assert_ancestry(root, prs[i-1]["headCommit"], prs[i]["headCommit"])
    head = _git(root, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    _assert_ancestry(root, prs[-1]["headCommit"], head)
    return {
        "format": "trisynora.g3-freeze-check/v1",
        "status": "g3-foundation-freeze-verified",
        "historicPassedCIRunsRecorded": len(prs),
        "frozenContractTestCount": prs[-1]["historicRecordedTests"],
        "checkedRepositoryFiles": len(paths),
        "gitAncestryChecked": True,
        "staticHistoricCIOnly": True,
        "reviewMergeOwnerApproved": False,
        "distributionLicenseCleared": False,
        "nativeProductsModified": False,
        "nativeProductsRun": False,
        "realCrossProductE2EVerified": False,
        "productionReleaseAllowed": False,
        "outstandingManualGates": len(record["unverifiedMandatoryGates"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = check(args.root)
    except (FreezeGateError, OSError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
