#!/usr/bin/env python3
"""Read-only, bounded three-product source integrity snapshots.

Tracks Git-indexed files plus explicitly named untracked/native media paths.
Capture writes only a fresh baseline outside all three source repositories.
Verification reads that baseline and source repositories without modifying them.
Neither command launches a product or certifies native runtime independence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ("vera", "minimax-h3", "pointflux")
FORMAT = "trisynora.source-isolation-snapshot/v1"
MAX_FILES = 20000
MAX_TRACKED_BYTES = 2 * 1024**3
MAX_SINGLE_BYTES = 256 * 1024**2
MAX_GIT_OUTPUT = 8 * 1024**2
MAX_BASELINE_BYTES = 32 * 1024**2
SHA = re.compile(r"^[a-f0-9]{64}$")


class IsolationAuditError(ValueError):
    pass


def _fail(message: str) -> None:
    raise IsolationAuditError(message)


def _git(root: Path, *args: str) -> bytes:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        run = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, check=False,
            timeout=20, env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise IsolationAuditError("Git repository inspection unavailable") from exc
    if run.returncode != 0 or len(run.stdout) > MAX_GIT_OUTPUT:
        _fail("Git inspection failed or result is too large")
    return run.stdout


def _relative(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 600
            or value.startswith("/") or "\\" in value or ":" in value
            or "\0" in value or "\r" in value or "\n" in value):
        _fail("invalid repository-relative path")
    parts = value.split("/")
    if any(x in ("", ".", "..") for x in parts):
        _fail("path traversal or non-normalized repository path")
    return value


def _roots(roots: dict[str, Path]) -> dict[str, Path]:
    if set(roots) != set(PRODUCTS):
        _fail("exactly Vera, MiniMax-H3 and PointFlux roots are required")
    resolved = {}
    for product in PRODUCTS:
        root = roots[product]
        if root.is_symlink() or not root.is_dir():
            _fail("source roots must be real directories")
        path = root.resolve(strict=True)
        if path == REPO_ROOT or path.is_relative_to(REPO_ROOT):
            _fail("a product root may not be TRISYNORA or a subdirectory of it")
        git_root = Path(os.fsdecode(_git(path, "rev-parse", "--show-toplevel")).strip()).resolve()
        if git_root != path:
            _fail("product root must be a Git top-level directory")
        resolved[product] = path
    for i, a in enumerate(PRODUCTS):
        for b in PRODUCTS[i+1:]:
            if (resolved[a] == resolved[b]
                    or resolved[a].is_relative_to(resolved[b])
                    or resolved[b].is_relative_to(resolved[a])):
                _fail("source product repositories must not overlap")
    return resolved


def _external_file(path: Path, roots: dict[str, Path], *, must_exist: bool) -> Path:
    if path.is_symlink():
        _fail("baseline or output must not be a symlink")
    if not path.name or not path.parent.is_dir() or path.parent.is_symlink():
        _fail("baseline/output parent must be a trusted directory")
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    if target.is_relative_to(REPO_ROOT):
        _fail("audit baseline must remain outside TRISYNORA")
    for root in roots.values():
        if target.is_relative_to(root):
            _fail("audit baseline must remain outside all native product repositories")
    if must_exist:
        if not target.is_file() or target.stat().st_size > MAX_BASELINE_BYTES:
            _fail("baseline missing, not a file or too large")
    elif target.exists():
        _fail("baseline destination exists; overwrite forbidden")
    return target


def _hash_tracked(root: Path, relative: str) -> dict[str, Any]:
    rel = _relative(relative)
    path = root
    for part in rel.split("/"):
        path = path / part
        if path.is_symlink():
            _fail("tracked or watched symlink encountered; content not attested")
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return {"path": rel, "kind": "missing", "sizeBytes": 0, "sha256": ""}
    if not stat.S_ISREG(mode):
        _fail("tracked or watched path is not a regular file")
    if path.stat().st_size > MAX_SINGLE_BYTES:
        _fail("tracked or watched file exceeds 256 MiB audit limit")
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while block := f.read(1024 * 1024):
            size += len(block)
            if size > MAX_SINGLE_BYTES:
                _fail("file grew past limit during audit")
            hasher.update(block)
    if size != path.stat().st_size:
        _fail("source changed during snapshot")
    return {"path": rel, "kind": "regular", "sizeBytes": size, "sha256": hasher.hexdigest()}


def _watch_paths(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict) or set(value) != set(PRODUCTS):
        _fail("watch list must contain all three products as keys")
    result = {}
    for product in PRODUCTS:
        items = value[product]
        if not isinstance(items, list) or len(items) > 100:
            _fail("watch paths must be bounded arrays")
        if any(not isinstance(x, str) for x in items):
            _fail("watch paths must be strings")
        mapped = [_relative(x) for x in items]
        if len(set(mapped)) != len(mapped):
            _fail("duplicate explicit watch paths")
        result[product] = sorted(mapped)
    return result


def _state(root: Path, watch: list[str], *, capturing: bool) -> dict[str, Any]:
    head = os.fsdecode(_git(root, "rev-parse", "HEAD")).strip()
    if not re.fullmatch(r"[a-f0-9]{40,64}", head):
        _fail("invalid Git HEAD")
    raw = _git(root, "ls-files", "--cached", "-z")
    indexed = [os.fsdecode(x) for x in raw.split(b"\0") if x]
    if len(indexed) + len(watch) > MAX_FILES:
        _fail("too many tracked files to attest")
    paths = sorted(set(_relative(x) for x in indexed) | set(watch))
    entries = []
    total = 0
    for rel in paths:
        entry = _hash_tracked(root, rel)
        if capturing and entry["kind"] == "missing":
            _fail("capture cannot certify a missing indexed or watched file")
        entries.append(entry)
        total += entry["sizeBytes"]
        if total > MAX_TRACKED_BYTES:
            _fail("tracked scope exceeds 2 GiB audit limit")
    return {
        "head": head, "fileCount": len(entries), "totalBytes": total,
        "watchPaths": watch, "entries": entries,
    }


def make_snapshot(roots: dict[str, Path], watches: dict[str, list[str]]) -> dict[str, Any]:
    dirs = _roots(roots)
    normalized = _watch_paths(watches)
    result = {
        "format": FORMAT,
        "scope": "git-indexed-files-and-explicit-watch-paths-only",
        "unwatchedUntrackedFilesIncluded": False,
        "nativeRuntimeIndependenceVerified": False,
        "products": {},
    }
    for name in PRODUCTS:
        result["products"][name] = _state(dirs[name], normalized[name], capturing=True)
    return result


def _json_bytes(data: bytes) -> dict:
    def unique(pairs):
        ret = {}
        for key, value in pairs:
            if key in ret:
                _fail("baseline JSON contains duplicate keys")
            ret[key] = value
        return ret
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IsolationAuditError("invalid baseline JSON") from exc
    if not isinstance(obj, dict):
        _fail("baseline JSON must be object")
    return obj


def capture(roots: dict[str, Path], watches: dict[str, list[str]], output: Path) -> dict[str, Any]:
    dirs = _roots(roots)
    target = _external_file(output, dirs, must_exist=False)
    record = make_snapshot(dirs, watches)
    body = (json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(body) > MAX_BASELINE_BYTES:
        _fail("baseline too large")
    with target.open("xb") as fp:
        fp.write(body)
    return {
        "status": "baseline-created",
        "baselineSha256": hashlib.sha256(body).hexdigest(),
        "trackedAndWatchedCounts": {p: record["products"][p]["fileCount"] for p in PRODUCTS},
        "unwatchedUntrackedFilesIncluded": False,
        "nativeRuntimeIndependenceVerified": False,
    }


def verify(roots: dict[str, Path], baseline: Path, expected_sha: str) -> dict[str, Any]:
    dirs = _roots(roots)
    file = _external_file(baseline, dirs, must_exist=True)
    if not SHA.fullmatch(expected_sha):
        _fail("expected baseline SHA-256 must be a lowercase 64-character digest")
    body = file.read_bytes()
    if hashlib.sha256(body).hexdigest() != expected_sha:
        _fail("baseline digest mismatch; trusted prior evidence is required")
    record = _json_bytes(body)
    if (set(record) != {"format", "scope", "unwatchedUntrackedFilesIncluded",
                        "nativeRuntimeIndependenceVerified", "products"}
            or record["format"] != FORMAT
            or record["scope"] != "git-indexed-files-and-explicit-watch-paths-only"
            or record["unwatchedUntrackedFilesIncluded"] is not False
            or record["nativeRuntimeIndependenceVerified"] is not False
            or not isinstance(record["products"], dict)
            or set(record["products"]) != set(PRODUCTS)):
        _fail("unsupported or malformed baseline policy")
    watches = _watch_paths({
        p: record["products"][p].get("watchPaths") for p in PRODUCTS
    })
    changes = {}
    counts = {}
    for p in PRODUCTS:
        state = _state(dirs[p], watches[p], capturing=False)
        base = record["products"][p]
        if set(base) != {"head", "fileCount", "totalBytes", "watchPaths", "entries"}:
            _fail("invalid baseline product record")
        if not isinstance(base["entries"], list):
            _fail("baseline entries missing")
        counts[p] = state["fileCount"]
        current_files = {x["path"]: x for x in state["entries"]}
        previous_files = {}
        for entry in base["entries"]:
            if (not isinstance(entry, dict)
                    or set(entry) != {"path", "kind", "sizeBytes", "sha256"}):
                _fail("malformed baseline file record")
            key = _relative(entry["path"])
            if key in previous_files:
                _fail("duplicate baseline paths")
            previous_files[key] = entry
        mismatches = sum(
            current_files.get(path) != previous_files.get(path)
            for path in current_files.keys() | previous_files.keys()
        )
        changes[p] = {
            "headChanged": state["head"] != base["head"],
            "pathDifferences": mismatches,
        }
    unchanged = all(not v["headChanged"] and v["pathDifferences"] == 0 for v in changes.values())
    return {
        "status": "unchanged-within-scope" if unchanged else "changed-within-scope",
        "baselineSha256": expected_sha, "products": changes,
        "fileCounts": counts,
        "unwatchedUntrackedFilesIncluded": False,
        "nativeRuntimeIndependenceVerified": False,
        "crossProductE2EVerified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("capture", "verify"):
        action = sub.add_parser(name)
        action.add_argument("--vera-root", type=Path, required=True)
        action.add_argument("--h3-root", type=Path, required=True)
        action.add_argument("--pointflux-root", type=Path, required=True)
        if name == "capture":
            action.add_argument("--watch-list", type=Path, required=True)
            action.add_argument("--out", type=Path, required=True)
        else:
            action.add_argument("--baseline", type=Path, required=True)
            action.add_argument("--expected-baseline-sha256", required=True)
    a = parser.parse_args()
    roots = {"vera": a.vera_root, "minimax-h3": a.h3_root, "pointflux": a.pointflux_root}
    try:
        if a.cmd == "capture":
            if a.watch_list.is_symlink() or a.watch_list.stat().st_size > 65536:
                _fail("watch-list file unavailable or too large")
            watches = _json_bytes(a.watch_list.read_bytes())
            outcome = capture(roots, watches, a.out)
        else:
            outcome = verify(roots, a.baseline, a.expected_baseline_sha256)
    except (IsolationAuditError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "not-verified", "reason": str(exc)}))
        return 2
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome["status"] in {"baseline-created", "unchanged-within-scope"} else 3


if __name__ == "__main__":
    sys.exit(main())
