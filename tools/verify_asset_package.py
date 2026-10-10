#!/usr/bin/env python3
"""Read-only TRISYNORA asset package verifier (NOT an authorization gate).

Accepts only a declared asset envelope and package-relative media. It never
fetches remote URLs, executes received data, writes native product stores or
asserts a renderer/AI Take is correct.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "v1" / "asset.schema.json"
RELATIVE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*(?:/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)*$")
CHUNK = 1024 * 1024
MAX_ASSET_BYTES = 10 * 1024**3
MAX_MANIFEST_BYTES = 1024 * 1024


class PackageVerificationError(ValueError):
    pass


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackageVerificationError("duplicate JSON key")
        result[key] = value
    return result


def _json_bytes(data: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(PackageVerificationError("nonfinite JSON value")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PackageVerificationError("invalid JSON manifest") from exc
    if not isinstance(parsed, dict):
        raise PackageVerificationError("manifest must be object")
    return parsed


def _contained_file(root: Path, path: str) -> Path:
    if not isinstance(path, str) or len(path) > 500 or not RELATIVE.fullmatch(path):
        raise PackageVerificationError("invalid package-relative file path")
    current = root
    for piece in path.split("/"):
        current = current / piece
        if current.is_symlink():
            raise PackageVerificationError("symlink not permitted in package path")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise PackageVerificationError("package file not contained or missing") from exc
    if not resolved.is_file():
        raise PackageVerificationError("package path is not a regular file")
    return resolved


def verify_package(package_root: Path, manifest_relative: str = "asset.json", max_bytes: int = MAX_ASSET_BYTES) -> dict[str, Any]:
    if max_bytes < 0 or max_bytes > MAX_ASSET_BYTES:
        raise PackageVerificationError("invalid configured size ceiling")
    if package_root.is_symlink() or not package_root.is_dir():
        raise PackageVerificationError("package root must be a non-symlink directory")
    root = package_root.resolve(strict=True)
    manifest_file = _contained_file(root, manifest_relative)
    if manifest_file.stat().st_size > MAX_MANIFEST_BYTES:
        raise PackageVerificationError("manifest too large")
    manifest = _json_bytes(manifest_file.read_bytes())
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    problems = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: str(e.path))
    if problems:
        raise PackageVerificationError("schema invalid: " + problems[0].message)
    media = manifest["media"]
    path = _contained_file(root, media["path"])
    size = path.stat().st_size
    if size > max_bytes or size != media["sizeBytes"]:
        raise PackageVerificationError("media size mismatch or ceiling exceeded")
    h = hashlib.sha256()
    total = 0
    # O_NOFOLLOW protects the final component where supported. Concurrent
    # hostile filesystem changes still require a receiving-product sandbox.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as fp:
        if not stat.S_ISREG(os.fstat(fp.fileno()).st_mode):
            raise PackageVerificationError("not a regular media file")
        while chunk := fp.read(CHUNK):
            total += len(chunk)
            if total > max_bytes:
                raise PackageVerificationError("media exceeded limit while reading")
            h.update(chunk)
    if total != size or h.hexdigest() != media["sha256"]:
        raise PackageVerificationError("media changed during read or SHA-256 mismatch")
    return {
        "status": "asset-bytes-verified",
        "artifactId": manifest["artifactId"],
        "sizeBytes": total,
        "sha256": h.hexdigest(),
        "receiverAuthorized": False,
        "mediaSemanticsVerified": False,
        "crossProductE2EVerified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Local immutable exchange package directory")
    parser.add_argument("--manifest", default="asset.json", help="Path relative to package root")
    parser.add_argument("--max-bytes", type=int, default=MAX_ASSET_BYTES)
    args = parser.parse_args()
    try:
        result = verify_package(args.root, args.manifest, args.max_bytes)
    except (PackageVerificationError, OSError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
