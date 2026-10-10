#!/usr/bin/env python3
"""G2 bridge rehearsal on THREE SYNTHETIC Git roots, never actual product repos.

Synthetic H3 video copy -> digest-locked P1 exchange -> read-only receiver gate
-> real FFprobe + FFmpeg decode -> G1 scoped hashes unchanged.

The rehearsal does NOT run or modify native Vera, MiniMax-H3 or PointFlux.
It does not produce a native imported video, visual effect or final movie.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Any

from isolation_audit import capture, verify, IsolationAuditError
from p1_video_handoff import pack, HandoffError
from pointflux_receiver_dry_run import assess, ReceiverContractError
from pointflux_media_probe import (
    verify_playable, MediaProbeRejected, MediaProbeUnavailable,
)

PRODUCTS = ("vera", "minimax-h3", "pointflux")


class RehearsalRejected(ValueError):
    pass


class RehearsalUnavailable(ValueError):
    pass


def _command(args: list[str]) -> None:
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=45, check=False,
        shell=False,
    )
    if result.returncode:
        raise RehearsalRejected("isolated fixture initialization failed")


def _fixture_repo(root: Path, name: str) -> None:
    """Only create/commit under a freshly owned TemporaryDirectory."""
    root.mkdir()
    _command(["git", "-C", str(root), "init", "-q"])
    _command(["git", "-C", str(root), "config", "--local", "user.name", "TRISYNORA Fixture"])
    _command(["git", "-C", str(root), "config", "--local", "user.email", "ci@example.invalid"])
    (root / "src").mkdir()
    (root / "src" / "native.txt").write_text(
        f"synthetic mock {name}; not the real {name} product", encoding="utf-8"
    )
    _command(["git", "-C", str(root), "add", "src/native.txt"])
    _command(["git", "-C", str(root), "commit", "-qm", "synthetic isolated fixture"])


def _make_mp4(path: Path) -> None:
    """Create a genuinely decodable H.264 fixture, never a fake MP4 stub."""
    _command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
        "-f", "lavfi", "-i", "color=c=black:s=128x72:r=30:d=1",
        "-frames:v", "30", "-an", "-c:v", "libx264",
        "-preset", "ultrafast", "-threads", "1", "-pix_fmt", "yuv420p",
        str(path),
    ])
    if not path.is_file() or path.stat().st_size == 0:
        raise RehearsalRejected("real H.264 fixture was not created")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_rehearsal(
    after_package: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Self-contained test. Hook is exclusively for unit-test fault injection.

    The hook may only access paths underneath a synthetic TemporaryDirectory;
    it is NOT exposed as a CLI option or native product integration.
    """
    if shutil.which("git") is None:
        raise RehearsalUnavailable("Git is unavailable")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RehearsalUnavailable("FFmpeg and FFprobe are both required")

    # tempfile creates a fresh, isolated directory and cleans it up on exit.
    with tempfile.TemporaryDirectory(prefix="trisynora-g2-synthetic-") as dirname:
        root = Path(dirname).resolve(strict=True)
        native_roots = {product: root / product for product in PRODUCTS}
        for product in PRODUCTS:
            _fixture_repo(native_roots[product], product)

        h3_take = native_roots["minimax-h3"] / "exports" / "approved.mp4"
        h3_take.parent.mkdir()
        h3_native = native_roots["minimax-h3"] / "projects" / "production.json"
        h3_native.parent.mkdir()
        h3_native.write_text('{"fixture":"mock H3 project, not H3 native schema"}\n', encoding="utf-8")

        pf_native = native_roots["pointflux"] / "projects" / "project.json"
        pf_native.parent.mkdir()
        pf_native.write_text('{"fixture":"mock PF native, not a real PF scene"}\n', encoding="utf-8")
        vera_native = native_roots["vera"] / "settings" / "agent.json"
        vera_native.parent.mkdir()
        vera_native.write_text('{"fixture":"mock Vera agent"}\n', encoding="utf-8")

        export_root = root / "isolated-operator-export"
        export_root.mkdir()
        (export_root / "video").mkdir()
        (export_root / "project").mkdir()
        source_video = export_root / "video" / "approved.mp4"
        _make_mp4(source_video)
        shutil.copyfile(source_video, h3_take)
        shutil.copyfile(h3_native, export_root / "project" / "snapshot.json")
        video_sha = _sha(source_video)
        snapshot_sha = _sha(export_root / "project" / "snapshot.json")

        watch = {
            "vera": ["settings/agent.json"],
            "minimax-h3": ["exports/approved.mp4", "projects/production.json"],
            "pointflux": ["projects/project.json"],
        }
        baseline_file = root / "g1-baseline.json"
        before = capture(native_roots, watch, baseline_file)

        package_root = root / "isolated-exchange"
        copied = pack(
            source_root=export_root, video="video/approved.mp4",
            native_file="project/snapshot.json", destination=package_root,
            project_id="SyntheticH3", revision="synthetic-demo-v1",
            shot_id="SyntheticShot001", artifact_id="SyntheticAsset001",
            native_format="minimax-h3/synthetic-not-native",
            fps_num=30, fps_den=1, frames=30,
        )
        receiver = assess(
            package_root, "SyntheticPointFlux", target_fps_num=30, target_fps_den=1,
        )

        if after_package is not None:
            after_package({
                "roots": native_roots, "package": package_root,
                "export": export_root, "baseline": baseline_file,
            })

        decoded = verify_playable(package_root, "SyntheticPointFlux")
        after = verify(native_roots, baseline_file, before["baselineSha256"])
        if _sha(source_video) != video_sha or _sha(export_root / "project" / "snapshot.json") != snapshot_sha:
            raise RehearsalRejected("operator-export source changed during rehearsal")
        if after["status"] != "unchanged-within-scope":
            raise RehearsalRejected("synthetic product source changed during rehearsal")
        if (copied["status"] != "handoff-package-verified"
                or receiver["status"] != "blocked"
                or decoded["status"] != "blocked"
                or not decoded["media"]["fullVideoDecodeSucceeded"]
                or decoded["media"]["frameCount"] != 30
                or decoded["media"]["sha256"] != video_sha
                or receiver["authority"]["pointfluxImported"]
                or decoded["authority"]["receiverAuthorized"]):
            raise RehearsalRejected("media/authorization handoff invariant violated")

        return {
            "format": "trisynora.g2-rehearsal-evidence/v1",
            "status": "synthetic-bridge-rehearsal-pass",
            "sourceType": "temporary-synthetic-git-products-only",
            "media": {
                "container": "mp4", "codec": "h264",
                "width": 128, "height": 72, "fps": "30/1", "frames": 30,
                "sourceSha256": video_sha,
                "ffprobeStreamVerified": True, "fullFFmpegDecodeVerified": True,
            },
            "isolation": {
                "scope": "git-indexed-and-explicit-watches",
                "products": {p: after["products"][p] for p in PRODUCTS},
                "unchangedWithinScope": True,
                "unwatchedUntrackedFilesVerified": False,
            },
            "nativeProductsActuallyRun": False,
            "receiverAuthorizationGranted": False,
            "pointfluxNativeVideoImported": False,
            "veraFinalVerification": False,
            "realThreeProjectE2EVerified": False,
        }


def main() -> int:
    try:
        result = run_rehearsal()
    except (RehearsalUnavailable, MediaProbeUnavailable) as exc:
        print(json.dumps({"status": "not-verified", "reason": str(exc)}))
        return 4
    except (RehearsalRejected, IsolationAuditError, HandoffError,
            ReceiverContractError, MediaProbeRejected, OSError, ValueError,
            subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
