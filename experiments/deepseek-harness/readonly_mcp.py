#!/usr/bin/env python3
"""Standalone stdio MCP adapter for a DeepSeek Harness UI (read-only).

Only reads explicitly isolated, receipt-locked TRISYNORA exchange packages.
Never accesses H3/PointFlux/Vera source roots, executes commands, or grants
native project approval. No DeepSeek Harness dependency is needed to test it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

MAX_LINE = 65536
MAX_JSON_BYTES = 524288
MAX_MEDIA_BYTES = 128 * 1024 * 1024
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
SHA = re.compile(r"^[0-9a-f]{64}$")
CONTRACTS = ("trisynora.asset/v1", "trisynora.shot/v1")
PRODUCTS = {
    "vera": ("governance-evidence", "validate-handoff"),
    "minimax-h3": ("video-export", "approved-take-reference"),
    "pointflux": ("particle-render", "video-layer-import"),
}
TOOLS = [
    {
        "name": "trisynora_list_capabilities",
        "description": "List declared optional Vera, MiniMax-H3 and PointFlux capabilities. All native connections remain unavailable; declaration is not execution or authorization.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "trisynora_check_capability",
        "description": "Read-only lookup of a declared capability's current integration state. No native service is contacted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "enum": list(PRODUCTS)},
                "capability": {"type": "string", "maxLength": 64},
            },
            "required": ["product", "capability"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "trisynora_inspect_package",
        "description": "Read only an isolated staging package and its digest-locked Asset, Shot and media. Does not decode media, import into PointFlux, or approve a write.",
        "inputSchema": {
            "type": "object",
            "properties": {"packageId": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"}},
            "required": ["packageId"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
]


class Rejected(ValueError):
    """Closed, sanitized rejection. Never include full native filesystem paths."""


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = {}
    for key, val in pairs:
        if key in obj:
            raise Rejected("JSON contains duplicate keys")
        obj[key] = val
    return obj


def decode(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_JSON_BYTES:
        raise Rejected("JSON exceeds bounded read limit")
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Rejected("invalid UTF-8 JSON") from exc
    if not isinstance(obj, dict):
        raise Rejected("JSON object required")
    return obj


def _file(root: Path, relative: str, max_bytes: int) -> Path:
    # Never follow symlinks, including intermediate components.
    pieces = relative.split("/")
    if (not pieces or any(not piece or piece in {".", ".."} for piece in pieces)
            or "\\" in relative or ":" in relative or relative.startswith("/")):
        raise Rejected("unsafe package-relative path")
    cursor = root
    for component in pieces:
        cursor = cursor / component
        if cursor.is_symlink():
            raise Rejected("symlinks are forbidden")
    try:
        mode = cursor.lstat().st_mode
        if not stat.S_ISREG(mode) or cursor.stat().st_size > max_bytes:
            raise Rejected("nonregular or oversized package file")
    except FileNotFoundError as exc:
        raise Rejected("required package file missing") from exc
    return cursor


def _trusted_staging() -> Path:
    env = os.environ.get("TRISYNORA_EXCHANGE_ROOT", "")
    if not env:
        raise Rejected("separate exchange root not configured")
    root = Path(env)
    if not root.is_absolute() or not root.is_dir():
        raise Rejected("exchange root must be an existing absolute directory")
    # A user-chosen location inside ANY Git worktree is not independent.
    # Check all ancestors for worktree/submodule .git pointers.
    for entry in (root, *root.parents):
        if entry.is_symlink():
            raise Rejected("symlinked staging ancestry refused")
        if (entry / ".git").exists():
            raise Rejected("exchange staging may not be within any Git checkout")
    root = root.resolve(strict=True)
    sentinel = _file(root, ".trisynora-exchange-root.json", 2048)
    data = decode(sentinel.read_bytes())
    if data != {"format": "trisynora.external-exchange-root/v1", "kind": "read-only-staging"}:
        raise Rejected("exchange root marker not explicitly configured")
    return root


def _read_json(root: Path, rel: str) -> tuple[dict[str, Any], str]:
    path = _file(root, rel, MAX_JSON_BYTES)
    buf = path.read_bytes()
    return decode(buf), hashlib.sha256(buf).hexdigest()


def _sha_field(value: Any) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise Rejected("invalid declared SHA-256")
    return value


def _digest_media(path: Path, limit: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fd:
        while True:
            block = fd.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > limit:
                raise Rejected("media exceeds read-only pilot size limit")
            digest.update(block)
    if path.stat().st_size != size:
        raise Rejected("media changed during validation")
    return size, digest.hexdigest()


def inspect(package_id: str) -> dict[str, Any]:
    if not isinstance(package_id, str) or not ID.fullmatch(package_id):
        raise Rejected("invalid package identifier")
    root = _trusted_staging()
    pkg = root / package_id
    if pkg.is_symlink() or not pkg.is_dir():
        raise Rejected("package missing or linked")
    ready, _ = _read_json(pkg, "ready.json")
    if (set(ready) != {"format", "assetManifestSha256", "shotManifestSha256"}
            or ready["format"] != "trisynora.h3-video-package/v1"):
        raise Rejected("invalid package completion marker")
    asset, asset_digest = _read_json(pkg, "manifests/asset.json")
    shot, shot_digest = _read_json(pkg, "manifests/shot.json")
    if (asset_digest != _sha_field(ready["assetManifestSha256"])
            or shot_digest != _sha_field(ready["shotManifestSha256"])):
        raise Rejected("manifest receipt mismatch")
    if asset.get("contract") != CONTRACTS[0] or shot.get("contract") != CONTRACTS[1]:
        raise Rejected("incompatible manifest contract")
    origin = asset.get("origin")
    if (not isinstance(origin, dict) or origin.get("product") != "minimax-h3"
            or shot.get("origin") != origin):
        raise Rejected("untrusted or inconsistent producer identity")
    media = asset.get("media")
    pub, handoff = asset.get("publication"), shot.get("handoff")
    art_id = asset.get("artifactId")
    shot_id = shot.get("shotId")
    if (not isinstance(art_id, str) or not ID.fullmatch(art_id)
            or not isinstance(shot_id, str) or not ID.fullmatch(shot_id)
            or not isinstance(media, dict)
            or media.get("kind") != "video" or media.get("mimeType") != "video/mp4"
            or media.get("path") != f"assets/{art_id}.mp4"
            or not isinstance(pub, dict) or pub.get("mode") != "reference-only"
            or pub.get("requiresReceiverApproval") is not True
            or not isinstance(handoff, dict) or handoff.get("mode") != "reference-only"
            or handoff.get("requiresExplicitBind") is not True
            or shot.get("assetIds") != [art_id]):
        raise Rejected("unsafe asset, link or approval flags")
    if (type(media.get("sizeBytes")) is not int
            or media["sizeBytes"] < 1 or media["sizeBytes"] > MAX_MEDIA_BYTES):
        raise Rejected("declared media exceeds pilot limit")
    sha = _sha_field(media.get("sha256"))
    size, actual = _digest_media(_file(pkg, media["path"], MAX_MEDIA_BYTES), MAX_MEDIA_BYTES)
    if size != media["sizeBytes"] or actual != sha:
        raise Rejected("media bytes do not match receipt")
    # Manifest may mutate during hashing; without a locked snapshot, reject.
    if (_read_json(pkg, "manifests/asset.json")[1] != asset_digest
            or _read_json(pkg, "manifests/shot.json")[1] != shot_digest
            or _read_json(pkg, "ready.json")[0] != ready):
        raise Rejected("manifest changed during validation")
    return {
        "status": "verified-reference-only",
        "packageId": package_id,
        "producer": "minimax-h3",
        "shotId": shot_id,
        "artifactId": art_id,
        "mediaSha256": sha,
        "mediaSizeBytes": size,
        "mediaCodecVerified": False,
        "sourceAuthenticityVerified": False,
        "nativeReceiverAuthorized": False,
        "nativeProductsConnected": False,
        "pointfluxImported": False,
        "threeProductE2EVerified": False,
    }


def capabilities() -> dict[str, Any]:
    return {
        "status": "catalog-only",
        "products": [
            {"id": product, "connected": False,
             "declaredCapabilities": [
                 {"id": cap, "callable": False, "nativePermissionGranted": False}
                 for cap in caps
             ]}
            for product, caps in PRODUCTS.items()
        ],
        "mcpReadOnly": True, "nativeWriteToolsExposed": False,
        "operatorApprovalSubstituted": False,
    }


def dispatch(name: Any, args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise Rejected("tool arguments must be a JSON object")
    if name == "trisynora_list_capabilities" and args == {}:
        return capabilities()
    if name == "trisynora_check_capability" and set(args) == {"product", "capability"}:
        p, c = args["product"], args["capability"]
        if not isinstance(p, str) or p not in PRODUCTS or not isinstance(c, str) or c not in PRODUCTS[p]:
            raise Rejected("unknown or unauthorized capability")
        return {"product": p, "capability": c, "status": "not-connected",
                "callable": False, "authorized": False}
    if name == "trisynora_inspect_package" and set(args) == {"packageId"}:
        return inspect(args["packageId"])
    raise Rejected("unknown tool or unsupported/mutating operation")


def _reply(id_value: Any, result: Any = None, error: dict | None = None) -> dict:
    if error is not None:
        return {"jsonrpc": "2.0", "id": id_value, "error": error}
    return {"jsonrpc": "2.0", "id": id_value, "result": result}


def handle(req: dict[str, Any]) -> dict | None:
    version = req.get("jsonrpc")
    method = req.get("method")
    req_id = req.get("id")
    if version != "2.0" or not isinstance(method, str):
        return _reply(req_id, error={"code": -32600, "message": "Invalid Request"})
    if "id" not in req:
        return None  # Notification: never executes a tool.
    if type(req_id) not in (str, int):
        return _reply(None, error={"code": -32600, "message": "Invalid Request ID"})
    if method == "initialize":
        return _reply(req_id, {"protocolVersion": "2025-06-18",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "trisynora-readonly-capabilities", "version": "0.1.0-spike"}})
    if method == "ping":
        return _reply(req_id, {})
    if method == "tools/list":
        return _reply(req_id, {"tools": TOOLS})
    if method == "tools/call":
        params = req.get("params", {})
        if not isinstance(params, dict):
            return _reply(req_id, error={"code": -32602, "message": "Invalid params"})
        try:
            outcome = dispatch(params.get("name"), params.get("arguments", {}))
        except (Rejected, OSError, TypeError, KeyError) as exc:
            return _reply(req_id, {"content": [{"type": "text", "text": json.dumps({
                "status": "rejected", "reason": str(exc)}, ensure_ascii=False)}], "isError": True})
        return _reply(req_id, {"content": [{"type": "text", "text": json.dumps(
            outcome, sort_keys=True, ensure_ascii=False)}], "isError": False})
    return _reply(req_id, error={"code": -32601, "message": "Method not found"})


def main() -> int:
    # JSON-RPC stdio (one message per line). No stdout logs or file writes.
    while True:
        line = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not line:
            return 0
        if len(line) > MAX_LINE or not line.endswith(b"\n"):
            return 2
        try:
            response = handle(decode(line))
        except (Rejected, TypeError, KeyError) as exc:
            response = _reply(None, error={"code": -32700, "message": str(exc)})
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
