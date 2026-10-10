#!/usr/bin/env python3
"""PointFlux RECEIVER-SIDE contract preflight: read-only, NOT a native adapter.

Consumes a TRISYNORA H3-origin video exchange package and emits a JSON
assessment only. Never imports media, writes a PointFlux project, executes
Remotion/FFmpeg, or treats metadata as receiver authorization.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import sys

from p1_video_handoff import HandoffError, inspect
from verify_asset_package import PackageVerificationError, _contained_file, _json_bytes

ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
MAX_RECEIVER_FPS = 120
MAX_PILOT_SECONDS = 60


class ReceiverContractError(ValueError):
    pass


def assess(
    package_root: Path,
    target_project_id: str,
    *,
    target_fps_num: int | None = None,
    target_fps_den: int | None = None,
) -> dict:
    """Return data-only compatibility report, with no write or import permissions."""
    if not isinstance(target_project_id, str) or not ID.fullmatch(target_project_id):
        raise ReceiverContractError("invalid PointFlux target project identifier")
    if (target_fps_num is None) != (target_fps_den is None):
        raise ReceiverContractError("target fps requires both numerator and denominator")
    if target_fps_num is not None:
        if not isinstance(target_fps_num, int) or not isinstance(target_fps_den, int):
            raise ReceiverContractError("target fps must be integer rational")
        if target_fps_num < 1 or target_fps_den < 1:
            raise ReceiverContractError("target fps numerator and denominator must be positive")
        target_rate = Fraction(target_fps_num, target_fps_den)
        if not (Fraction(1, 1) <= target_rate <= Fraction(MAX_RECEIVER_FPS, 1)):
            raise ReceiverContractError("target fps beyond prototype safety range")
    else:
        target_rate = None

    # This call independently validates readiness, manifest digests, links,
    # producer origin, reference-only mode, and actual copied file SHA-256.
    try:
        checked = inspect(package_root)
        root = package_root.resolve(strict=True)
        asset_path = _contained_file(root, "manifests/asset.json")
        shot_path = _contained_file(root, "manifests/shot.json")
        asset = _json_bytes(asset_path.read_bytes())
        shot = _json_bytes(shot_path.read_bytes())
    except (HandoffError, PackageVerificationError, OSError) as exc:
        raise ReceiverContractError("H3 exchange package verification failed") from exc

    if asset["origin"] != shot["origin"] or asset["origin"]["product"] != "minimax-h3":
        raise ReceiverContractError("package has inconsistent or non-H3 origin")
    if asset["media"]["kind"] != "video" or asset["media"]["mimeType"] != "video/mp4":
        raise ReceiverContractError("this receiver proposal only handles video/mp4 manifests")
    if shot["assetIds"] != [asset["artifactId"]]:
        raise ReceiverContractError("pilot accepts exactly one declared video asset per shot")
    if (asset["publication"]["mode"] != "reference-only"
            or shot["handoff"]["mode"] != "reference-only"
            or not asset["publication"]["requiresReceiverApproval"]
            or not shot["handoff"]["requiresExplicitBind"]):
        raise ReceiverContractError("the handoff must remain reference-only and unbound")

    fps_n = shot["timebase"]["fpsNumerator"]
    fps_d = shot["timebase"]["fpsDenominator"]
    frames = shot["timebase"]["durationFrames"]
    source_rate = Fraction(fps_n, fps_d)
    seconds = Fraction(frames * fps_d, fps_n)
    if not (Fraction(1, 1) <= source_rate <= Fraction(MAX_RECEIVER_FPS, 1)):
        raise ReceiverContractError("source fps beyond prototype safety range")
    if not (Fraction(0, 1) < seconds <= Fraction(MAX_PILOT_SECONDS, 1)):
        raise ReceiverContractError("source duration exceeds 60-second pilot bound")

    blocks = [
        "pointflux-native-video-layer-not-established",
        "receiver-owned-operator-approval-not-granted",
        "media-container-codec-and-frame-count-not-probed",
    ]
    if target_rate is not None and source_rate != target_rate:
        blocks.append("fps-mismatch-requires-explicit-conversion-plan")

    return {
        "format": "trisynora.pointflux-receiver-assessment/v1",
        "status": "blocked",  # MUST remain blocked until native integration exists.
        "blockingReasons": blocks,
        "producer": {
            "product": "minimax-h3",
            "projectId": shot["origin"]["projectId"],
            "revision": shot["origin"]["revision"],
        },
        "target": {"product": "pointflux", "projectId": target_project_id},
        "shot": {
            "id": shot["shotId"],
            "sourceNativeFormat": shot["native"]["format"],
            "sourceNativeSha256": shot["native"]["sha256"],
            "sourceSnapshotBytesAvailable": False,
            "frames": frames,
            "fpsNumerator": fps_n,
            "fpsDenominator": fps_d,
            "durationSecondsNumerator": seconds.numerator,
            "durationSecondsDenominator": seconds.denominator,
        },
        "asset": {
            "id": asset["artifactId"],
            "sha256": asset["media"]["sha256"],
            "sizeBytes": asset["media"]["sizeBytes"],
            "bytesVerified": checked["assetBytesChecked"] == 1,
            "realMp4CodecVerified": False,
        },
        "timebase": {
            "targetFpsSpecified": target_rate is not None,
            "exactFpsMatch": target_rate is not None and source_rate == target_rate,
        },
        "authority": {
            "receiverAuthorized": False,
            "explicitBindCompleted": False,
            "sourceModified": False,
            "targetModified": False,
            "pointfluxImported": False,
            "crossProductE2EVerified": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--target-project-id", required=True)
    parser.add_argument("--target-fps-num", type=int)
    parser.add_argument("--target-fps-den", type=int)
    args = parser.parse_args()
    try:
        assessment = assess(
            args.package, args.target_project_id,
            target_fps_num=args.target_fps_num,
            target_fps_den=args.target_fps_den,
        )
    except ReceiverContractError as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(assessment, sort_keys=True))
    # 3 deliberately distinguishes "data valid but native import not available"
    # from completed success (exit 0). It is an EXPECTED safe status.
    return 3


if __name__ == "__main__":
    sys.exit(main())
