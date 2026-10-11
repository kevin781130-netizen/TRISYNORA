#!/usr/bin/env python3
"""Explicitly anchored Ed25519 verification for V1 read-only status receipts.

No native connections; no key generation, signing keys, secret persistence, or
trust-on-first-use in this production-facing verifier. The caller supplies an
operator-approved registry and scoped replay floor OUT-OF-BAND. It is unsafe
to read the registry from the signed payload or an untrusted sibling file.

This gate proves possession of an explicitly pinned test/operational key, NOT
that a Vera/H3/PointFlux exporter is deployed, audited or connected.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from status_receipt import (
    ReceiptRejected, PRODUCT_KIND, ID, MAX_SEQ, MAX_BYTES, _utc,
    canonical_bytes, decode_receipt, validate,
)

SIGNED_SCHEMA = "trisynora.signed-status-receipt/v1"
TRUST_SCHEMA = "trisynora.product-publisher-trust/v1"
MAX_SIGNED_BYTES = 12288
MAX_ANCHORS = 16
SIGNING_DOMAIN = b"TRISYNORA:STATUS-RECEIPT:ED25519:V1\x00"
ANCHOR_KEYS = {
    "product", "instanceId", "keyId", "publicKeyBase64",
    "notBefore", "notAfter", "revoked",
}


class PublisherRejected(ReceiptRejected):
    """Fail-closed rejection; never report raw receipts or key material."""


def _require(test: bool, why: str) -> None:
    if not test:
        raise PublisherRejected(why)


def _keys(value: Any, expected: set[str], label: str) -> None:
    _require(type(value) is dict and set(value) == expected,
             "invalid " + label + " fields")


def _base64_bytes(value: Any, size: int) -> bytes:
    _require(type(value) is str and len(value) <= 96,
             "invalid cryptographic encoding")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise PublisherRejected("invalid cryptographic encoding") from exc
    _require(len(decoded) == size
             and base64.b64encode(decoded).decode("ascii") == value,
             "noncanonical or wrong-length cryptographic encoding")
    return decoded


def signing_message(receipt: dict, key_id: str) -> bytes:
    """Public wire format; signer tools may implement this independently."""
    _require(type(key_id) is str and bool(ID.fullmatch(key_id)),
             "invalid signing key identifier")
    return SIGNING_DOMAIN + canonical_bytes({
        "schema": SIGNED_SCHEMA, "algorithm": "Ed25519",
        "keyId": key_id, "receipt": receipt,
    })


def _trusted_anchors(registry: Any, *, minimum_epoch: int) -> dict:
    _keys(registry, {"schema", "epoch", "anchors"}, "trust registry")
    _require(registry["schema"] == TRUST_SCHEMA,
             "unapproved trust schema")
    _require(type(minimum_epoch) is int and minimum_epoch >= 1
             and type(registry["epoch"]) is int
             and minimum_epoch <= registry["epoch"] <= MAX_SEQ,
             "trust registry rollback/epoch refused")
    anchors = registry["anchors"]
    _require(type(anchors) is list and 0 < len(anchors) <= MAX_ANCHORS,
             "empty or oversized product trust registry")
    found = {}
    used_public_keys = {}
    for record in anchors:
        _keys(record, ANCHOR_KEYS, "publisher trust anchor")
        product = record["product"]
        instance = record["instanceId"]
        key_id = record["keyId"]
        _require(type(product) is str and product in PRODUCT_KIND
                 and all(type(s) is str and bool(ID.fullmatch(s))
                         for s in (instance, key_id)),
                 "unknown or unscoped publisher identity")
        _require(type(record["revoked"]) is bool,
                 "invalid key revocation flag")
        start = _utc(record["notBefore"])
        end = _utc(record["notAfter"])
        _require(start < end,
                 "invalid key lifetime")
        pub = _base64_bytes(record["publicKeyBase64"], 32)
        scope = (product, instance, key_id)
        _require(scope not in found, "duplicate publisher key binding")
        _require(pub not in used_public_keys,
                 "publisher key reused across identity or rotation")
        found[scope] = (pub, start, end, record["revoked"])
        used_public_keys[pub] = scope
    return found


def verify_signed(
    data: bytes,
    *,
    now: datetime,
    trust_registry: dict,
    minimum_registry_epoch: int,
    replay_floor: Mapping[tuple[str, str, str], int],
    expected_product: str | None = None,
) -> dict:
    """Validate a signed snapshot, with *externally provisioned* trust inputs.

    replay_floor must be read from the trusted durable per-(product,instance,
    key) replay ledger. This function never writes to that ledger. The caller
    MUST atomically commit the new sequence before using the status; therefore
    this API always returns usableAsAuthoritativeNativeStatus=false.
    """
    _require(type(data) is bytes and 0 < len(data) <= MAX_SIGNED_BYTES,
             "invalid or oversized signed receipt")
    _require(type(replay_floor) is dict, "explicit scoped replay floor required")
    try:
        envelope = decode_receipt(data)
    except ReceiptRejected as exc:
        raise PublisherRejected("malformed signed receipt envelope") from exc
    _keys(envelope, {"schema", "receipt", "signature"},
          "signed receipt envelope")
    _require(envelope["schema"] == SIGNED_SCHEMA,
             "wrong signed receipt schema")
    sig = envelope["signature"]
    _keys(sig, {"algorithm", "keyId", "value"}, "signature")
    _require(sig["algorithm"] == "Ed25519"
             and type(sig["keyId"]) is str
             and bool(ID.fullmatch(sig["keyId"])),
             "unsupported signature algorithm or key")
    raw_sig = _base64_bytes(sig["value"], 64)

    receipt = envelope["receipt"]
    _require(type(receipt) is dict, "receipt object required")
    try:
        plain = canonical_bytes(receipt)
        _require(len(plain) <= MAX_BYTES, "oversized inner receipt")
        # Uses the independently tested ninth-knife field/freshness/hash gate.
        snapshot = validate(plain, now=now, expected_product=expected_product)
    except ReceiptRejected as exc:
        raise PublisherRejected("inner receipt invalid") from exc

    producer = receipt["producer"]
    scope = (
        producer["product"], producer["instanceId"], sig["keyId"],
    )
    anchors = _trusted_anchors(
        trust_registry, minimum_epoch=minimum_registry_epoch,
    )
    _require(scope in anchors, "untrusted or cross-product signing key")
    pub, start, end, revoked = anchors[scope]
    _require(not revoked, "publisher key revoked")
    issued = _utc(receipt["issuedAt"])
    expires = _utc(receipt["expiresAt"])
    _require(isinstance(now, datetime) and now.tzinfo is not None
             and now.utcoffset() is not None,
             "timezone-aware evaluation required")
    instant = now.astimezone(timezone.utc)
    _require(start <= issued <= instant < end
             and expires <= end,
             "receipt or verification outside publisher key validity")
    # Scope-specific externally persisted replay checkpoint; no global
    # sequence mistakenly shared between different products or key rotations.
    _require(scope in replay_floor, "publisher replay ledger missing")
    floor = replay_floor[scope]
    _require(type(floor) is int and 0 <= floor <= MAX_SEQ,
             "publisher replay floor invalid")
    _require(receipt["sequence"] > floor,
             "replayed, reordered or rolled-back publisher status")
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(
            raw_sig, signing_message(receipt, sig["keyId"]),
        )
    except (InvalidSignature, ValueError) as exc:
        raise PublisherRejected("publisher signature verification failed") from exc

    # A synthetic anchored test key proves only a TEST key signature.
    # Runtime/native-product authenticity and durable ledger write are
    # deliberately not claimed by this standalone read-only verifier.
    return {
        **snapshot,
        "status": "pinned-publisher-key-signature-verified",
        "signatureAlgorithm": "Ed25519",
        "publisherKeyId": sig["keyId"],
        "registryEpoch": trust_registry["epoch"],
        "publisherKeyMatchedOutOfBandTrust": True,
        "producerAuthenticityVerified": True,
        "nativeProductRuntimeVerified": False,
        "replayFloorValidated": True,
        "durableReplayCommitPerformed": False,
        "usableAsAuthoritativeNativeStatus": False,
        "nativeProductsConnected": False,
        "nativeWriteAuthorized": False,
        "harnessJobControlAuthorized": False,
    }
