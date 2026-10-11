#!/usr/bin/env python3
"""V1 *untrusted* product-owned status snapshot RECEIPT contract.

No product adapter, private signing key, native runtime, files or network calls.
SHA-256 here checks envelope integrity only; it cannot authenticate the author.
Validation never upgrades a snapshot to a permission, executable job or trusted
native fact. Origin authenticity must be added in a separately reviewed gate.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import re
from typing import Any

MAX_BYTES = 8192
MAX_TTL_SECONDS = 300
MAX_FUTURE_SKEW_SECONDS = 60
MAX_SEQ = 2**53 - 1
PRODUCT_KIND = {
    "vera": "verification-run",
    "minimax-h3": "director-take",
    "pointflux": "render-result",
}
ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$", re.ASCII)
DIGEST = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
RFC3339_UTC = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
    re.ASCII,
)
PHASES = ("queued", "running", "finished")
OUTCOMES = ("pending", "success", "failed", "blocked", "cancelled")
EXPECTED_FIELDS = {
    "schema", "producer", "subject", "state", "provenance",
    "issuedAt", "expiresAt", "sequence", "integrity",
    "authority",
}


class ReceiptRejected(ValueError):
    """Closed, non-leaky rejection. No original receipt data in errors."""


def _require(test: bool, why: str) -> None:
    if not test:
        raise ReceiptRejected(why)


def _keys(obj: Any, keys: set[str]) -> None:
    _require(isinstance(obj, dict) and set(obj) == keys,
             "unexpected status receipt fields")


def _positive_id(x: Any) -> bool:
    return isinstance(x, str) and bool(ID.fullmatch(x))


def _sha(x: Any) -> bool:
    return isinstance(x, str) and bool(DIGEST.fullmatch(x))


def _integer(x: Any, minimum: int, maximum: int) -> bool:
    return type(x) is int and minimum <= x <= maximum


def _utc(x: Any) -> datetime:
    _require(isinstance(x, str) and bool(RFC3339_UTC.fullmatch(x)),
             "timestamps must be exact whole-second UTC")
    try:
        return datetime.strptime(x, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc,
        )
    except ValueError as exc:
        raise ReceiptRejected("invalid calendar timestamp") from exc


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for k, v in pairs:
        _require(k not in out, "duplicate receipt JSON key")
        out[k] = v
    return out


def _no_constants(v: str) -> None:
    raise ReceiptRejected("non-JSON numeric constants refused")


def canonical_bytes(value: dict[str, Any]) -> bytes:
    """Bounded canonicalization for the narrow ASCII-field v1 contract."""
    try:
        return json.dumps(
            value, sort_keys=True, ensure_ascii=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReceiptRejected("receipt cannot be canonically encoded") from exc


def encode_body_digest(receipt: dict[str, Any]) -> str:
    """Public, NON-AUTHENTICATING hash (not a product signature)."""
    _require(isinstance(receipt, dict), "receipt object required")
    payload = {k: v for k, v in receipt.items() if k != "integrity"}
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def decode_receipt(data: bytes) -> dict[str, Any]:
    _require(isinstance(data, bytes) and 0 < len(data) <= MAX_BYTES,
             "bounded receipt bytes required")
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_unique,
                         parse_constant=_no_constants)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptRejected("invalid JSON or UTF-8") from exc
    _require(isinstance(obj, dict), "receipt JSON object required")
    return obj


def validate(
    data: bytes,
    *,
    now: datetime,
    expected_product: str | None = None,
    last_seen_sequence: int | None = None,
) -> dict[str, Any]:
    """Read-only structural/integrity/freshness validation, no I/O or grants.

    last_seen_sequence is supplied by an independent future consumer. No
    counter/DB is created here; sequence alone never authenticates an issuer.
    """
    _require(isinstance(now, datetime) and now.tzinfo is not None
             and now.utcoffset() is not None,
             "caller must supply aware evaluation time")
    _require(expected_product is None or expected_product in PRODUCT_KIND,
             "unknown expected product")
    _require(last_seen_sequence is None or _integer(
        last_seen_sequence, 0, MAX_SEQ), "invalid prior sequence")

    receipt = decode_receipt(data)
    _keys(receipt, EXPECTED_FIELDS)
    _require(receipt["schema"] == "trisynora.status-receipt/v1",
             "unsupported status receipt version")

    producer = receipt["producer"]
    _keys(producer, {"product", "instanceId"})
    product = producer["product"]
    _require(type(product) is str and product in PRODUCT_KIND,
             "unknown native product")
    _require(_positive_id(producer["instanceId"]),
             "invalid producer instance identifier")
    _require(expected_product is None or expected_product == product,
             "product identity mismatch")

    subject = receipt["subject"]
    _keys(subject, {"kind", "id"})
    _require(subject["kind"] == PRODUCT_KIND[product]
             and _positive_id(subject["id"]),
             "subject is not owned by declared producer")

    state = receipt["state"]
    _keys(state, {"phase", "outcome", "progress"})
    _require(state["phase"] in PHASES and type(state["phase"]) is str,
             "invalid phase")
    _require(state["outcome"] in OUTCOMES and type(state["outcome"]) is str,
             "invalid outcome")
    progress = state["progress"]
    _keys(progress, {"completed", "total"})
    _require(_integer(progress["completed"], 0, 1000000)
             and _integer(progress["total"], 1, 1000000)
             and progress["completed"] <= progress["total"],
             "invalid progress bounds")
    _require(
        (state["phase"] == "finished") ==
        (state["outcome"] != "pending"),
        "non-terminal result or terminal pending mismatch",
    )
    _require(
        state["phase"] != "queued" or progress["completed"] == 0,
        "queued phase cannot report completed progress",
    )

    provenance = receipt["provenance"]
    _keys(provenance, {"sourceRevision", "evidenceSha256", "sourceKind"})
    _require(provenance["sourceKind"] == "native-product-export",
             "receipt must declare native producer origin")
    _require(_sha(provenance["sourceRevision"])
             and _sha(provenance["evidenceSha256"]),
             "invalid evidence or revision digest")

    issued = _utc(receipt["issuedAt"])
    expires = _utc(receipt["expiresAt"])
    now_utc = now.astimezone(timezone.utc)
    _require(issued <= now_utc + timedelta(
        seconds=MAX_FUTURE_SKEW_SECONDS), "receipt issued too far in future")
    _require(expires > now_utc, "expired status cannot be called current")
    _require(issued <= now_utc, "future-issued snapshot not yet effective")
    lifetime = (expires - issued).total_seconds()
    _require(0 < lifetime <= MAX_TTL_SECONDS,
             "unbounded status freshness window")
    _require(_integer(receipt["sequence"], 1, MAX_SEQ),
             "invalid producer sequence")
    _require(last_seen_sequence is None
             or receipt["sequence"] > last_seen_sequence,
             "replayed or reordered producer sequence")

    authority = receipt["authority"]
    _keys(authority, {"mode", "grants", "sideEffects"})
    _require(authority["mode"] == "read-only-status"
             and authority["grants"] == []
             and authority["sideEffects"] is False,
             "native execution/approval authority forbidden")

    integrity = receipt["integrity"]
    _keys(integrity, {"algorithm", "sha256"})
    _require(integrity["algorithm"] == "sha256"
             and _sha(integrity["sha256"]),
             "invalid integrity digest")
    _require(hmac.compare_digest(
        integrity["sha256"], encode_body_digest(receipt),
    ), "receipt integrity mismatch")

    # This is intentionally NOT a verified product-origin statement. A fake
    # author can recompute the hash; only separately provisioned signer trust
    # anchors could justify elevating the result to authenticated status.
    return {
        "status": "untrusted-snapshot-validated",
        "product": product,
        "subjectKind": subject["kind"],
        "subjectId": subject["id"],
        "phase": state["phase"],
        "outcome": state["outcome"],
        "progress": dict(progress),
        "sequence": receipt["sequence"],
        "expiresAt": receipt["expiresAt"],
        "integrityChecked": True,
        "producerAuthenticityVerified": False,
        "nativeProductsConnected": False,
        "nativeWriteAuthorized": False,
        "harnessJobControlAuthorized": False,
        "usableAsAuthoritativeNativeStatus": False,
    }
