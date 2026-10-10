#!/usr/bin/env python3
"""TRISYNORA read-only cross-envelope preflight.

It checks manifest structure and references, NOT the authority to execute jobs,
edit projects, load remote media, or verify a GPU render.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from verify_asset_package import (
    MAX_MANIFEST_BYTES,
    PackageVerificationError,
    _contained_file,
    _json_bytes,
    verify_package,
)

ROOT = Path(__file__).resolve().parents[1]
KINDS = ("capability", "asset", "shot", "job", "evidence")
KEYS = {"asset": "artifactId", "shot": "shotId", "job": "jobId", "evidence": "evidenceId"}
MAX_ENVELOPES = 200


class PreflightError(ValueError):
    pass


def preflight(package_root: Path, manifests: dict[str, list[str]], *, verify_bytes: bool = False) -> dict[str, Any]:
    """Validate untrusted local manifests without writing or invoking a product."""
    if package_root.is_symlink() or not package_root.is_dir():
        raise PreflightError("root must be an existing non-symlink package directory")
    root = package_root.resolve(strict=True)
    if any(k not in KINDS for k in manifests):
        raise PreflightError("unknown manifest category")
    if sum(len(paths) for paths in manifests.values()) > MAX_ENVELOPES:
        raise PreflightError("too many envelopes")
    if not any(manifests.values()):
        raise PreflightError("no envelopes supplied")
    if verify_bytes and not manifests.get("asset"):
        raise PreflightError("byte verification requires at least one asset manifest")

    parsed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ids: dict[str, set[Any]] = defaultdict(set)
    seen_manifests: set[str] = set()
    verified = 0

    for kind in KINDS:
        schema = json.loads((ROOT / "schemas" / "v1" / f"{kind}.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for manifest_relative in manifests.get(kind, []):
            try:
                manifest_file = _contained_file(root, manifest_relative)
            except PackageVerificationError as exc:
                raise PreflightError(f"unsafe {kind} manifest path") from exc
            normalized = manifest_file.relative_to(root).as_posix()
            if normalized in seen_manifests:
                raise PreflightError("same manifest listed more than once")
            seen_manifests.add(normalized)
            if manifest_file.stat().st_size > MAX_MANIFEST_BYTES:
                raise PreflightError("manifest exceeds 1 MiB")
            try:
                payload = _json_bytes(manifest_file.read_bytes())
            except PackageVerificationError as exc:
                raise PreflightError(f"malformed {kind} manifest") from exc
            problems = sorted(validator.iter_errors(payload), key=lambda e: str(e.path))
            if problems:
                raise PreflightError(f"invalid {kind} contract: {problems[0].message}")
            if kind in KEYS:
                if kind == "shot":
                    o = payload["origin"]
                    key = (o["product"], o["projectId"], payload[KEYS[kind]])
                else:
                    key = payload[KEYS[kind]]
                if key in ids[kind]:
                    raise PreflightError(f"duplicate {kind} identity")
                ids[kind].add(key)
            parsed[kind].append(payload)
            if verify_bytes and kind == "asset":
                try:
                    verify_package(root, normalized)
                except (PackageVerificationError, OSError) as exc:
                    raise PreflightError("asset byte verification failed") from exc
                verified += 1

    asset_ids = ids["asset"]
    for shot in parsed["shot"]:
        if any(x not in asset_ids for x in shot["assetIds"]):
            raise PreflightError("shot refers to missing asset manifest")
    for job in parsed["job"]:
        if any(x not in asset_ids for x in job["inputArtifactIds"]):
            raise PreflightError("job refers to missing input asset manifest")

    job_map = {j["jobId"]: j for j in parsed["job"]}
    known_digests = {a["media"]["sha256"] for a in parsed["asset"]}
    for evidence in parsed["evidence"]:
        job = job_map.get(evidence["subject"]["jobId"])
        if job is None:
            raise PreflightError("evidence refers to unknown job")
        if evidence["subject"]["artifactSha256"] not in known_digests:
            raise PreflightError("evidence refers to unknown artifact digest")
        if evidence["origin"]["product"] != job["target"]["product"]:
            raise PreflightError("evidence domain issuer is not target product")

    return {
        "status": "manifest-links-consistent",
        "envelopes": {k: len(parsed[k]) for k in KINDS},
        "assetBytesChecked": verified,
        "receiverAuthorized": False,
        "nativeProjectsModified": False,
        "mediaSemanticsVerified": False,
        "crossProductE2EVerified": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    for kind in KINDS:
        p.add_argument(f"--{kind}", action="append", default=[], metavar="RELATIVE_MANIFEST")
    p.add_argument("--verify-bytes", action="store_true", help="Also read and check each declared media SHA-256")
    args = p.parse_args()
    try:
        result = preflight(args.root, {k: getattr(args, k) for k in KINDS}, verify_bytes=args.verify_bytes)
    except (PreflightError, OSError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
