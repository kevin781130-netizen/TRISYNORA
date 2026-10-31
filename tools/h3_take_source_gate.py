#!/usr/bin/env python3
"""Read-only H3 exported Take + media-byte gate before TRISYNORA P1 packaging.

This does not run H3, authenticate its export, decode a video, approve a
receiver, or mutate any source project. Run against an operator-controlled
export COPY, never against a live H3 project database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
PACKS = {"h3-short-drama", "h3-music-video", "h3-native-shot"}
PROJECT_LIMIT = 16 * 1024 * 1024
MEDIA_LIMIT = 10 * 1024 * 1024 * 1024


class GateError(ValueError):
    pass


def _safe_file(root: Path, name: str, limit: int) -> Path:
    if (not isinstance(name, str) or not name or "\\" in name or
            name.startswith("/") or ":" in name or
            any(p in ("", ".", "..") for p in name.split("/"))):
        raise GateError("UNSAFE_RELATIVE_PATH")
    cursor = root
    for part in name.split("/"):
        cursor = cursor / part
        if cursor.is_symlink():
            raise GateError("SYMLINK_SOURCE_REJECTED")
    try:
        if not cursor.is_file() or cursor.stat().st_size > limit:
            raise GateError("MISSING_OR_OVERSIZE_SOURCE")
        cursor.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise GateError("SOURCE_OUTSIDE_EXPORT_ROOT") from exc
    return cursor


def _hash(path: Path, limit: int) -> str:
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            count += len(block)
            if count > limit:
                raise GateError("SOURCE_GREW_PAST_LIMIT")
            digest.update(block)
    return digest.hexdigest()


def _strict_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise GateError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def check(root: Path, project_file: str, video_file: str,
          project_id: str, take_id: str) -> dict:
    if not ID.fullmatch(project_id) or not ID.fullmatch(take_id):
        raise GateError("INVALID_IDENTIFIER")
    if root.is_symlink() or not root.is_dir():
        raise GateError("EXPORT_ROOT_NOT_DIRECTORY")
    root = root.resolve(strict=True)
    snapshot = _safe_file(root, project_file, PROJECT_LIMIT)
    media = _safe_file(root, video_file, MEDIA_LIMIT)
    if snapshot == media or media.suffix.lower() != ".mp4":
        raise GateError("EXPECTED_SEPARATE_MP4")
    before = _hash(snapshot, PROJECT_LIMIT)
    try:
        obj = json.loads(snapshot.read_text(encoding="utf-8"),
                         object_pairs_hook=_strict_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(GateError("NONFINITE_JSON")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GateError("INVALID_SNAPSHOT_JSON") from exc
    if not isinstance(obj, dict) or obj.get("id") != project_id:
        raise GateError("PROJECT_ID_MISMATCH")
    production = obj.get("production_v1")
    if not isinstance(production, dict):
        raise GateError("PRODUCTION_RECORD_MISSING")
    takes = production.get("takes")
    if not isinstance(takes, list):
        raise GateError("TAKES_MISSING")
    found = [t for t in takes if isinstance(t, dict) and t.get("id") == take_id]
    if len(found) != 1:
        raise GateError("TAKE_MISSING_OR_AMBIGUOUS")
    take = found[0]
    prompt_id = take.get("h3_prompt_id")
    if not isinstance(prompt_id, str) or not ID.fullmatch(prompt_id):
        raise GateError("TAKE_PROMPT_RECEIPT_MISSING")
    runtime = production.get("workflow_runtime_v1")
    runs = runtime.get("runs") if isinstance(runtime, dict) else None
    valid_runs = [r for r in runs if isinstance(r, dict)
                  and r.get("prompt_id") == prompt_id
                  and r.get("pack_id") in PACKS] if isinstance(runs, list) else []
    if len(valid_runs) != 1:
        raise GateError("H3_RUNTIME_RECEIPT_MISSING_OR_AMBIGUOUS")
    history = production.get("generation_history")
    matching_history = [h for h in history if isinstance(h, dict)
                        and h.get("prompt_id") == prompt_id
                        and h.get("status") == "complete"] if isinstance(history, list) else []
    if len(matching_history) != 1:
        raise GateError("H3_RENDER_HISTORY_NOT_COMPLETE_OR_AMBIGUOUS")
    asset = take.get("asset")
    if (not isinstance(asset, dict) or asset.get("type") != "output"
            or asset.get("filename") != media.name):
        raise GateError("TAKE_OUTPUT_FILENAME_NOT_BOUND")
    expected = take.get("source_media_sha256")
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        raise GateError("TAKE_MEDIA_DIGEST_MISSING")
    actual = _hash(media, MEDIA_LIMIT)
    if actual.lower() != expected.lower():
        raise GateError("TAKE_MEDIA_DIGEST_MISMATCH")
    if _hash(snapshot, PROJECT_LIMIT) != before:
        raise GateError("SNAPSHOT_CHANGED_DURING_CHECK")
    return {
        "status": "ready_for_native_media_probe",
        "projectId": project_id, "takeId": take_id, "h3PromptId": prompt_id,
        "snapshotSha256": before, "mediaSha256": actual,
        "takeReceiptAndMediaBytesMatched": True, "sourceModified": False,
        "nativeExportAuthenticated": False, "h3RealRenderVerified": False,
        "videoCodecVerified": False, "receiverAuthorized": False,
        "pointfluxImported": False, "crossProductE2EVerified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--project-file", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--take-id", required=True)
    args = parser.parse_args()
    try:
        result = check(args.source_root, args.project_file, args.video,
                       args.project_id, args.take_id)
        code = 0
    except (GateError, OSError) as exc:
        result = {"status": "blocked", "reason": str(exc),
                  "crossProductE2EVerified": False}
        code = 2
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
