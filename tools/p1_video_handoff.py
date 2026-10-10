#!/usr/bin/env python3
"""TRISYNORA P1: local H3-origin video handoff, without native product writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

from jsonschema import Draft202012Validator
from preflight_exchange import preflight, PreflightError
from verify_asset_package import _contained_file, _json_bytes, PackageVerificationError, MAX_ASSET_BYTES

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
REV = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FMT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")
MAX_NATIVE_BYTES = 16 * 1024 * 1024


class HandoffError(ValueError):
    pass


def digest_file(path: Path, limit: int) -> tuple[int, str]:
    if path.stat().st_size > limit:
        raise HandoffError("file exceeds size limit")
    hasher = hashlib.sha256()
    n = 0
    with path.open("rb") as fp:
        while chunk := fp.read(1024 * 1024):
            n += len(chunk)
            if n > limit:
                raise HandoffError("file grew past size limit")
            hasher.update(chunk)
    return n, hasher.hexdigest()


def write_json_new(path: Path, data: dict) -> str:
    body = (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    with path.open("xb") as fp:
        fp.write(body)
    return hashlib.sha256(body).hexdigest()


def validate(kind: str, data: dict) -> None:
    schema = json.loads((ROOT / "schemas" / "v1" / f"{kind}.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda x: str(x.path))
    if errors:
        raise HandoffError(f"invalid {kind} envelope: {errors[0].message}")


def pack(*, source_root: Path, video: str, native_file: str, destination: Path,
         project_id: str, revision: str, shot_id: str, artifact_id: str,
         native_format: str, fps_num: int, fps_den: int, frames: int) -> dict:
    if source_root.is_symlink() or not source_root.is_dir():
        raise HandoffError("source root must be a real directory")
    root = source_root.resolve(strict=True)
    if (destination.exists() or destination.is_symlink() or
            not destination.parent.is_dir() or destination.parent.is_symlink()):
        raise HandoffError("destination must be a NEW folder under a trusted existing parent")
    dest = destination.parent.resolve(strict=True) / destination.name
    if dest.is_relative_to(root) or dest.is_relative_to(ROOT):
        raise HandoffError("destination may not be inside source or TRISYNORA repository")
    for name, value, pattern in (("project", project_id, ID), ("revision", revision, REV),
                                 ("shot", shot_id, ID), ("artifact", artifact_id, ID),
                                 ("native format", native_format, FMT)):
        if not pattern.fullmatch(value):
            raise HandoffError(f"invalid {name}")
    if min(fps_num, fps_den, frames) <= 0:
        raise HandoffError("fps and frame count must be positive")
    if not video.lower().endswith(".mp4"):
        raise HandoffError("only mp4 files supported in P1")
    try:
        source_video = _contained_file(root, video)
        native = _contained_file(root, native_file)
    except PackageVerificationError as exc:
        raise HandoffError("unsafe or missing source file") from exc
    if source_video == native:
        raise HandoffError("native snapshot and video must be different files")
    size, video_sha = digest_file(source_video, MAX_ASSET_BYTES)
    _, native_sha = digest_file(native, MAX_NATIVE_BYTES)
    origin = {"product": "minimax-h3", "projectId": project_id, "revision": revision}
    asset = {
        "contract": "trisynora.asset/v1", "artifactId": artifact_id, "origin": origin,
        "media": {"kind": "video", "mimeType": "video/mp4", "sizeBytes": size,
                  "sha256": video_sha, "path": f"assets/{artifact_id}.mp4"},
        "publication": {"mode": "reference-only", "requiresReceiverApproval": True},
    }
    shot = {
        "contract": "trisynora.shot/v1", "shotId": shot_id, "origin": origin,
        "native": {"format": native_format, "sha256": native_sha},
        "timebase": {"fpsNumerator": fps_num, "fpsDenominator": fps_den,
                     "durationFrames": frames},
        "assetIds": [artifact_id],
        "handoff": {"mode": "reference-only", "requiresExplicitBind": True},
    }
    validate("asset", asset)
    validate("shot", shot)
    # os.mkdir is exclusive. Only a newly created staging folder may be cleaned up.
    dest.mkdir(mode=0o700, exist_ok=False)
    try:
        (dest / "assets").mkdir()
        (dest / "manifests").mkdir()
        copied = dest / "assets" / f"{artifact_id}.mp4"
        h = hashlib.sha256()
        count = 0
        with source_video.open("rb") as inp, copied.open("xb") as out:
            while chunk := inp.read(1024 * 1024):
                count += len(chunk)
                if count > MAX_ASSET_BYTES:
                    raise HandoffError("copy exceeds size limit")
                h.update(chunk)
                out.write(chunk)
        if count != size or h.hexdigest() != video_sha:
            raise HandoffError("source changed during copy")
        if digest_file(source_video, MAX_ASSET_BYTES) != (size, video_sha):
            raise HandoffError("source changed during packaging")
        if digest_file(native, MAX_NATIVE_BYTES)[1] != native_sha:
            raise HandoffError("native snapshot changed during packaging")
        asset_sha = write_json_new(dest / "manifests" / "asset.json", asset)
        shot_sha = write_json_new(dest / "manifests" / "shot.json", shot)
        write_json_new(dest / "ready.json", {
            "format": "trisynora.h3-video-package/v1",
            "assetManifestSha256": asset_sha,
            "shotManifestSha256": shot_sha,
        })
        result = inspect(dest)
        result["sourceUnchangedAtPackaging"] = True
        return result
    except BaseException:
        shutil.rmtree(dest)
        raise


def inspect(package_root: Path) -> dict:
    if package_root.is_symlink() or not package_root.is_dir():
        raise HandoffError("package must be a real directory")
    root = package_root.resolve(strict=True)
    try:
        marker_file = _contained_file(root, "ready.json")
        if marker_file.stat().st_size > 4096:
            raise HandoffError("readiness marker too large")
        marker = _json_bytes(marker_file.read_bytes())
    except PackageVerificationError as exc:
        raise HandoffError("missing or unsafe readiness marker") from exc
    if set(marker) != {"format", "assetManifestSha256", "shotManifestSha256"} or marker["format"] != "trisynora.h3-video-package/v1":
        raise HandoffError("invalid readiness marker")
    paths = {"asset": "manifests/asset.json", "shot": "manifests/shot.json"}
    for kind, key in (("asset", "assetManifestSha256"), ("shot", "shotManifestSha256")):
        try:
            f = _contained_file(root, paths[kind])
        except PackageVerificationError as exc:
            raise HandoffError("missing or unsafe manifest") from exc
        if not isinstance(marker[key], str) or len(marker[key]) != 64:
            raise HandoffError("invalid readiness SHA")
        if digest_file(f, 1024 * 1024)[1] != marker[key]:
            raise HandoffError("manifest changed after package creation")
    try:
        result = preflight(root, {k: [v] for k, v in paths.items()}, verify_bytes=True)
        asset = _json_bytes((root / paths["asset"]).read_bytes())
        shot = _json_bytes((root / paths["shot"]).read_bytes())
    except (PackageVerificationError, PreflightError) as exc:
        raise HandoffError("package bytes or contract references invalid") from exc
    if asset["origin"] != shot["origin"] or asset["origin"]["product"] != "minimax-h3":
        raise HandoffError("origin mismatch")
    if asset["publication"]["mode"] != "reference-only" or shot["handoff"]["mode"] != "reference-only":
        raise HandoffError("handoff must remain reference-only")
    return {
        "status": "handoff-package-verified", "producer": "minimax-h3",
        "shotId": shot["shotId"], "sha256": asset["media"]["sha256"],
        "assetBytesChecked": result["assetBytesChecked"],
        "receiverAuthorized": False, "pointfluxImported": False,
        "videoCodecVerified": False, "crossProductE2EVerified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack")
    for option in ("video", "native-file", "project-id", "revision", "shot-id",
                   "artifact-id", "native-format"):
        p.add_argument("--" + option, required=True)
    p.add_argument("--source-root", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    for option in ("fps-num", "fps-den", "frames"):
        p.add_argument("--" + option, required=True, type=int)
    q = sub.add_parser("inspect")
    q.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.cmd == "inspect":
            result = inspect(args.root)
        else:
            result = pack(source_root=args.source_root, video=args.video,
                          native_file=args.native_file, destination=args.out,
                          project_id=args.project_id, revision=args.revision,
                          shot_id=args.shot_id, artifact_id=args.artifact_id,
                          native_format=args.native_format,
                          fps_num=args.fps_num, fps_den=args.fps_den, frames=args.frames)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
