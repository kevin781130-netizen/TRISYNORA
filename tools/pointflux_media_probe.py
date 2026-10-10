#!/usr/bin/env python3
"""Read-only real MP4 probe for staged TRISYNORA H3 video packages.

It uses ffprobe for codec/frame metadata and ffmpeg to decode video frames
to a NULL sink. Successful probing never authorizes native PointFlux import.
No native source repository or PointFlux workspace is read or modified.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess
import sys

from p1_video_handoff import HandoffError, digest_file
from pointflux_receiver_dry_run import ReceiverContractError, assess
from verify_asset_package import _contained_file, _json_bytes, PackageVerificationError

MAX_VIDEO_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_WIDTH = 1920
MAX_HEIGHT = 1080
PROBE_TIMEOUT = 25
DECODE_TIMEOUT = 90


class MediaProbeRejected(ValueError):
    pass


class MediaProbeUnavailable(ValueError):
    pass


def _run(binary: str, args: list[str], timeout: int) -> str:
    if shutil.which(binary) is None:
        raise MediaProbeUnavailable(f"{binary} is not installed or on PATH")
    try:
        result = subprocess.run(
            [binary, *args], shell=False, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeUnavailable(f"{binary} timed out") from exc
    except OSError as exc:
        raise MediaProbeUnavailable(f"{binary} unavailable") from exc
    if len(result.stdout) > MAX_OUTPUT_BYTES or len(result.stderr) > MAX_OUTPUT_BYTES:
        raise MediaProbeRejected(f"{binary} emitted excessive output")
    if result.returncode != 0:
        raise MediaProbeRejected(f"{binary} reported media error; exit={result.returncode}")
    return result.stdout


def _fps(value: object) -> Fraction:
    if not isinstance(value, str):
        raise MediaProbeRejected("ffprobe frame rate unavailable")
    try:
        rate = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise MediaProbeRejected("ffprobe frame rate invalid") from exc
    if rate <= 0:
        raise MediaProbeRejected("ffprobe frame rate must be positive")
    return rate


def parse_probe(info: object, *, expected_fps: Fraction, expected_frames: int) -> dict:
    """Parse untrusted ffprobe JSON and compare with declared shot timebase."""
    if not isinstance(info, dict):
        raise MediaProbeRejected("ffprobe response must be an object")
    fmt = info.get("format")
    streams = info.get("streams")
    if not isinstance(fmt, dict) or not isinstance(streams, list):
        raise MediaProbeRejected("ffprobe response is missing format or streams")
    if "mp4" not in str(fmt.get("format_name", "")).split(","):
        raise MediaProbeRejected("media container is not MP4")
    if len(streams) != 1 or not isinstance(streams[0], dict):
        raise MediaProbeRejected("pilot requires exactly one video stream and no others")
    stream = streams[0]
    if stream.get("codec_type") != "video" or stream.get("codec_name") != "h264":
        raise MediaProbeRejected("pilot requires H.264 video")
    if stream.get("pix_fmt") != "yuv420p":
        raise MediaProbeRejected("pilot requires yuv420p pixel format")
    width, height = stream.get("width"), stream.get("height")
    if (type(width) is not int or type(height) is not int
            or width < 64 or height < 64 or width > MAX_WIDTH or height > MAX_HEIGHT):
        raise MediaProbeRejected("video dimensions exceed pilot policy")
    actual_fps = _fps(stream.get("avg_frame_rate"))
    if actual_fps != expected_fps:
        raise MediaProbeRejected("MP4 fps mismatches declared shot timebase")
    measured = stream.get("nb_read_frames")
    if not isinstance(measured, str) or not measured.isdecimal():
        raise MediaProbeRejected("ffprobe did not provide counted frames")
    actual_frames = int(measured)
    if actual_frames != expected_frames:
        raise MediaProbeRejected("MP4 frame count mismatches declared shot duration")
    declared_frames = stream.get("nb_frames")
    if declared_frames not in (None, "N/A") and declared_frames != measured:
        raise MediaProbeRejected("MP4 indexed frame count mismatches counted frames")
    return {
        "codec": "h264", "pixelFormat": "yuv420p",
        "width": width, "height": height,
        "fpsNumerator": actual_fps.numerator,
        "fpsDenominator": actual_fps.denominator,
        "frameCount": actual_frames,
    }


def verify_playable(package_root: Path, target_project_id: str) -> dict:
    """Inspect a package; return BLOCKED despite successful real-video decoding."""
    try:
        preflight = assess(package_root, target_project_id)
        root = package_root.resolve(strict=True)
        manifest = _json_bytes(_contained_file(root, "manifests/asset.json").read_bytes())
        shot = _json_bytes(_contained_file(root, "manifests/shot.json").read_bytes())
        media_file = _contained_file(root, manifest["media"]["path"])
    except (ReceiverContractError, HandoffError, PackageVerificationError, OSError) as exc:
        raise MediaProbeRejected("invalid H3-origin exchange package") from exc
    if not preflight["asset"]["bytesVerified"]:
        raise MediaProbeRejected("package media SHA-256 was not verified")
    if manifest["media"]["sizeBytes"] > MAX_VIDEO_BYTES:
        raise MediaProbeRejected("real video probe limited to 128 MiB")
    reference_sha = manifest["media"]["sha256"]
    if digest_file(media_file, MAX_VIDEO_BYTES)[1] != reference_sha:
        raise MediaProbeRejected("video changed before FFprobe")

    stdout = _run("ffprobe", [
        "-v", "error", "-protocol_whitelist", "file",
        "-count_frames", "-show_streams", "-show_format", "-of", "json", str(media_file),
    ], PROBE_TIMEOUT)
    try:
        probe_result = json.loads(stdout)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise MediaProbeRejected("ffprobe returned invalid JSON") from exc
    fps_n = shot["timebase"]["fpsNumerator"]
    fps_d = shot["timebase"]["fpsDenominator"]
    frames = shot["timebase"]["durationFrames"]
    metadata = parse_probe(
        probe_result, expected_fps=Fraction(fps_n, fps_d), expected_frames=frames
    )
    # Decode all frames to a null sink. Fixed args, shell=False, no output path,
    # restricted file-only protocol, capped source and duration. No media edits.
    _run("ffmpeg", [
        "-hide_banner", "-loglevel", "error", "-nostdin",
        "-protocol_whitelist", "file", "-threads", "1",
        "-i", str(media_file), "-map", "0:v:0", "-an", "-f", "null", "-",
    ], DECODE_TIMEOUT)
    if digest_file(media_file, MAX_VIDEO_BYTES)[1] != reference_sha:
        raise MediaProbeRejected("video changed during probing")

    return {
        "format": "trisynora.media-probe/v1",
        "status": "blocked",
        "blockingReasons": [
            "pointflux-native-video-layer-not-established",
            "receiver-owned-operator-approval-not-granted",
        ],
        "media": {
            "sha256": reference_sha, "container": "mp4",
            "ffprobeStreamMetadataChecked": True, "fullVideoDecodeSucceeded": True,
            **metadata,
        },
        "target": preflight["target"],
        "authority": {
            "receiverAuthorized": False, "explicitBindCompleted": False,
            "pointfluxImported": False, "crossProductE2EVerified": False,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", required=True, type=Path)
    p.add_argument("--target-project-id", required=True)
    args = p.parse_args()
    try:
        result = verify_playable(args.package, args.target_project_id)
    except MediaProbeUnavailable as exc:
        print(json.dumps({"status": "not-verified", "reason": str(exc)}))
        return 4
    except (MediaProbeRejected, ValueError, OSError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    # "Blocked" is success for contract checks but not for native import.
    return 3


if __name__ == "__main__":
    sys.exit(main())
