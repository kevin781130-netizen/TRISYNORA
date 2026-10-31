#!/usr/bin/env python3
"""Operator-controlled H3 Take -> TRISYNORA P1 package + real MP4 gate.

This is a staging adapter, NOT an H3-native exporter or PointFlux importer.
Inputs must be immutable copies exported by the operator. The command never
contacts H3, ComfyUI, GPU, PointFlux or a model, and never grants approval.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from h3_take_source_gate import GateError, _hash, _safe_file, check, MEDIA_LIMIT, PROJECT_LIMIT
from p1_video_handoff import HandoffError, pack
from pointflux_media_probe import (
    MAX_VIDEO_BYTES, MediaProbeRejected, MediaProbeUnavailable,
    _run, parse_probe, verify_playable,
)


class BridgeError(ValueError):
    pass


def _media_timebase(video: Path) -> tuple[int, int, int, dict]:
    """Read real frames once; do not trust declarative fps/frame CLI flags."""
    if video.stat().st_size > MAX_VIDEO_BYTES:
        raise BridgeError("MEDIA_EXCEEDS_PILOT_128_MIB")
    raw = _run("ffprobe", [
        "-v", "error", "-protocol_whitelist", "file", "-count_frames",
        "-show_streams", "-show_format", "-of", "json", str(video),
    ], 25)
    try:
        data = json.loads(raw)
        streams = data["streams"]
        stream = streams[0]
        frames = int(stream["nb_read_frames"])
        rate = Fraction(stream["avg_frame_rate"])
    except (KeyError, IndexError, ValueError, ZeroDivisionError, TypeError, OverflowError) as exc:
        raise BridgeError("INVALID_PROBED_TIMEBASE") from exc
    if len(streams) != 1 or frames < 1 or rate <= 0:
        raise BridgeError("UNSUPPORTED_STREAMS_OR_TIMEBASE")
    metadata = parse_probe(data, expected_fps=rate, expected_frames=frames)
    if Fraction(frames, 1) / rate > 60:
        raise BridgeError("PILOT_SHOT_LONGER_THAN_60_SECONDS")
    return rate.numerator, rate.denominator, frames, metadata


def bridge(*, source_root: Path, project_file: str, video_file: str,
           project_id: str, take_id: str, destination: Path,
           target_project_id: str) -> dict:
    """Stage one exact H3 Take as reference-only, decode-test, retain source."""
    # Refuse to write anything until the real Take receipt and media bytes match.
    proof = check(source_root, project_file, video_file, project_id, take_id)
    root = source_root.resolve(strict=True)
    source_video = _safe_file(root, video_file, MEDIA_LIMIT)
    snapshot = _safe_file(root, project_file, PROJECT_LIMIT)
    snapshot_sha = proof["snapshotSha256"]
    original_media_sha = proof["mediaSha256"]

    fps_num, fps_den, frames, metadata = _media_timebase(source_video)
    # No accepting a source that changed while codec/frame tests were running.
    if _hash(snapshot, PROJECT_LIMIT) != snapshot_sha or _hash(source_video, MEDIA_LIMIT) != original_media_sha:
        raise BridgeError("EXPORTED_SOURCE_CHANGED_DURING_PREFLIGHT")

    # Existing TRISYNORA P1 packer creates a fresh exclusive directory,
    # copies only the MP4, checks source hashes, and never authorizes import.
    package = pack(
        source_root=root, video=video_file, native_file=project_file,
        destination=destination, project_id=project_id,
        revision="snapshot-" + snapshot_sha[:20], shot_id=take_id,
        artifact_id="take_" + take_id,
        native_format="minimax-h3/export-snapshot", fps_num=fps_num,
        fps_den=fps_den, frames=frames,
    )
    if package.get("status") != "handoff-package-verified" or package.get("pointfluxImported") is not False:
        raise BridgeError("PACKAGE_CONTRACT_UNVERIFIED")
    result = verify_playable(destination, target_project_id)
    media = result.get("media", {})
    authority = result.get("authority", {})
    if (result.get("status") != "blocked"
            or media.get("sha256") != original_media_sha
            or media.get("fullVideoDecodeSucceeded") is not True
            or authority.get("receiverAuthorized") is not False
            or authority.get("pointfluxImported") is not False):
        raise BridgeError("REAL_MEDIA_OR_RECEIVER_CONTRACT_UNVERIFIED")
    # Second source check, after staging and real FFmpeg decoding.
    if _hash(snapshot, PROJECT_LIMIT) != snapshot_sha or _hash(source_video, MEDIA_LIMIT) != original_media_sha:
        raise BridgeError("EXPORTED_SOURCE_CHANGED_DURING_PACKAGING")
    return {
        "status": "staged_verified_receiver_blocked",
        "exportKind": "operator-supplied-untrusted-copy",
        "package": str(destination),
        "projectId": project_id, "takeId": take_id,
        "sourceSnapshotSha256": snapshot_sha,
        "sourceMediaSha256": original_media_sha,
        "video": metadata,
        "takeReceiptAndMediaBytesMatched": True,
        "realMediaDecoded": True,
        "nativeH3ExporterVerified": False,
        "pointfluxImported": False,
        "receiverAuthorized": False,
        "crossProductE2EVerified": False,
        "sourceModified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--project-file", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--take-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target-project-id", required=True)
    args = parser.parse_args()
    try:
        result = bridge(source_root=args.source_root,
                        project_file=args.project_file, video_file=args.video,
                        project_id=args.project_id, take_id=args.take_id,
                        destination=args.out,
                        target_project_id=args.target_project_id)
        code = 3  # media success, native importer deliberately blocked
    except MediaProbeUnavailable as exc:
        result = {"status": "not_verified", "reason": str(exc), "crossProductE2EVerified": False}
        code = 4
    except (BridgeError, GateError, HandoffError, MediaProbeRejected, OSError, ValueError) as exc:
        result = {"status": "blocked", "reason": str(exc), "crossProductE2EVerified": False}
        code = 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
