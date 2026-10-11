#!/usr/bin/env python3
"""Operator-root-signed publisher registry + SQLite atomic issuer replay fence.

Optional *isolated test-only consumer*: no native apps, jobs, model calls,
publisher private keys or registry-root private key. The OS-isolated operator
must provision the root public key from a trustworthy OUT-OF-BAND channel.
Successful acceptance is not a claim of production native-product connection.
"""
from __future__ import annotations

import base64
from datetime import datetime
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from signed_status_receipt import (
    PublisherRejected, TRUST_SCHEMA, _trusted_anchors, _base64_bytes,
    verify_signed,
)
from status_receipt import (
    MAX_SEQ, ReceiptRejected, _utc, canonical_bytes, decode_receipt,
)

REGISTRY_ENVELOPE = "trisynora.signed-publisher-registry/v1"
REGISTRY_DOMAIN = b"TRISYNORA:PUBLISHER-REGISTRY:ED25519:V1\x00"
MAX_REGISTRY_BYTES = 12288
DB_VERSION = 1


class DurableTrustRejected(PublisherRejected):
    """Trust root, registry rollback or persisted replay rejected."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise DurableTrustRejected(reason)


def _keys(obj: Any, fields: set[str]) -> None:
    _require(type(obj) is dict and set(obj) == fields,
             "unexpected registry envelope fields")


def registry_message(registry: dict) -> bytes:
    """Public domain-separated wire contract; no private signing capability."""
    return REGISTRY_DOMAIN + canonical_bytes({
        "schema": REGISTRY_ENVELOPE,
        "algorithm": "Ed25519",
        "registry": registry,
    })


def authenticate_registry(
    signed_blob: bytes, *, pinned_root_public_key: bytes,
) -> tuple[dict, str, str]:
    """Authenticate full registry against a separately provisioned root key."""
    _require(type(signed_blob) is bytes
             and 0 < len(signed_blob) <= MAX_REGISTRY_BYTES,
             "invalid signed-registry size")
    _require(type(pinned_root_public_key) is bytes
             and len(pinned_root_public_key) == 32,
             "root must be a pinned raw 32-byte Ed25519 public key")
    try:
        envelope = decode_receipt(signed_blob)
        _keys(envelope, {"schema", "registry", "signature"})
        _require(envelope["schema"] == REGISTRY_ENVELOPE,
                 "invalid signed registry schema")
        signature = envelope["signature"]
        _keys(signature, {"algorithm", "value"})
        _require(signature["algorithm"] == "Ed25519",
                 "unapproved trust registry algorithm")
        signature_bytes = _base64_bytes(signature["value"], 64)
        registry = envelope["registry"]
        # Validates every anchor and issuer identity BEFORE accepting epoch.
        _trusted_anchors(registry, minimum_epoch=1)
        Ed25519PublicKey.from_public_bytes(pinned_root_public_key).verify(
            signature_bytes, registry_message(registry),
        )
    except (ReceiptRejected, TypeError, KeyError, InvalidSignature,
            ValueError) as exc:
        raise DurableTrustRejected(
            "untrusted registry or invalid root signature"
        ) from exc
    registry_hash = hashlib.sha256(canonical_bytes(registry)).hexdigest()
    root_fingerprint = hashlib.sha256(pinned_root_public_key).hexdigest()
    return registry, registry_hash, root_fingerprint


def _isolated_db_path(filename: Path) -> Path:
    """Reject paths within ANY Git tree and obvious symlink/unsafe file types.

    This is a configuration safety guard, NOT a race-safe malicious filesystem
    isolation primitive; filesystem and OS sandbox must be controlled outside.
    """
    _require(isinstance(filename, Path) and filename.is_absolute(),
             "external absolute replay ledger path required")
    _require(filename.name not in ("", ".", "..")
             and not filename.is_symlink(),
             "symlinked or invalid replay database")
    parent = filename.parent
    _require(parent.is_dir(), "replay ledger parent must already exist")
    for component in (parent, *parent.parents):
        _require(not component.is_symlink()
                 and not (component / ".git").exists(),
                 "replay ledger must not be in git or symlinked tree")
    if filename.exists():
        mode = filename.lstat().st_mode
        _require(stat.S_ISREG(mode) and filename.stat().st_nlink == 1,
                 "replay database must be a single regular file")
    return filename


def _open_db(filename: Path) -> sqlite3.Connection:
    path = _isolated_db_path(filename)
    try:
        db = sqlite3.connect(str(path), timeout=8, isolation_level=None)
        db.execute("PRAGMA busy_timeout=8000")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        _require(db.execute("PRAGMA user_version").fetchone()[0] in (0, DB_VERSION),
                 "unknown ledger schema version")
        return db
    except (sqlite3.Error, DurableTrustRejected) as exc:
        if "db" in locals():
            db.close()
        raise DurableTrustRejected("cannot open safely versioned replay ledger") from exc


def _schema(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS trust_state ("
        " id INTEGER PRIMARY KEY CHECK(id=1),"
        " epoch INTEGER NOT NULL, hash TEXT NOT NULL,"
        " root_sha256 TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS issuer_sequences ("
        " product TEXT NOT NULL, instance TEXT NOT NULL,"
        " max_seq INTEGER NOT NULL,"
        " PRIMARY KEY(product, instance))"
    )
    db.execute(f"PRAGMA user_version={DB_VERSION}")


def _state_check(db: sqlite3.Connection, registry: dict,
                 registry_hash: str, root_hash: str) -> int:
    state = db.execute(
        "SELECT epoch, hash, root_sha256 FROM trust_state WHERE id=1"
    ).fetchone()
    epoch = registry["epoch"]
    if state is None:
        return 0
    prev_epoch, prev_hash, prev_root = state
    _require(type(prev_epoch) is int and type(prev_hash) is str
             and type(prev_root) is str and prev_root == root_hash,
             "trust root mismatch or corrupt trust metadata")
    _require(epoch >= prev_epoch, "old publisher registry rollback denied")
    _require(epoch != prev_epoch or registry_hash == prev_hash,
             "same-epoch registry substitution denied")
    return prev_epoch


def _save_state(db: sqlite3.Connection, registry: dict, digest: str,
                root_hash: str) -> None:
    db.execute(
        "INSERT INTO trust_state(id,epoch,hash,root_sha256) VALUES(1,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET epoch=excluded.epoch,"
        " hash=excluded.hash, root_sha256=excluded.root_sha256",
        (registry["epoch"], digest, root_hash),
    )


def _perform(
    signed_registry: bytes, *, pinned_root_public_key: bytes,
    state_path: Path, now: datetime, signed_receipt: bytes | None,
    expected_product: str | None,
) -> dict:
    registry, reg_hash, root_hash = authenticate_registry(
        signed_registry, pinned_root_public_key=pinned_root_public_key,
    )
    _require(isinstance(now, datetime) and now.tzinfo is not None
             and now.utcoffset() is not None,
             "aware evaluation clock required")
    # Future status verification must fail even for a signed manifest with an
    # attacker-selected key lifetime. The registry itself carries no grants.
    result = None
    db = _open_db(state_path)
    try:
        db.execute("BEGIN IMMEDIATE")  # SQLite single-writer fence.
        _schema(db)
        prev_epoch = _state_check(db, registry, reg_hash, root_hash)
        if signed_receipt is not None:
            # Parse only metadata to query the correct durable high-water mark;
            # actual identity and signature are enforced by verify_signed().
            try:
                envelope = decode_receipt(signed_receipt)
                producer = envelope["receipt"]["producer"]
                signature = envelope["signature"]
                product, instance, kid = (
                    producer["product"], producer["instanceId"],
                    signature["keyId"],
                )
                _require(all(type(x) is str for x in (product, instance, kid)),
                         "invalid issuer identity")
            except (KeyError, TypeError, ReceiptRejected) as exc:
                raise DurableTrustRejected(
                    "bad signed receipt metadata"
                ) from exc
            current = db.execute(
                "SELECT max_seq FROM issuer_sequences "
                "WHERE product=? AND instance=?",
                (product, instance),
            ).fetchone()
            floor = current[0] if current is not None else 0
            _require(type(floor) is int and 0 <= floor <= MAX_SEQ,
                     "corrupted issuer replay floor")
            result = verify_signed(
                signed_receipt, now=now, trust_registry=registry,
                minimum_registry_epoch=max(1, prev_epoch),
                replay_floor={(product, instance, kid): floor},
                expected_product=expected_product,
            )
            db.execute(
                "INSERT INTO issuer_sequences(product,instance,max_seq) "
                "VALUES(?,?,?) ON CONFLICT(product,instance) DO UPDATE "
                "SET max_seq=excluded.max_seq",
                (product, instance, result["sequence"]),
            )
        if registry["epoch"] > prev_epoch or prev_epoch == 0:
            _save_state(db, registry, reg_hash, root_hash)
        db.execute("COMMIT")
        if signed_receipt is None:
            return {
                "status": "root-signed-registry-installed",
                "registryEpoch": registry["epoch"],
                "trustRootFingerprint": root_hash,
                "nativeProductsConnected": False,
                "nativeWriteAuthorized": False,
                "harnessJobControlAuthorized": False,
            }
        return {
            **result,
            "status": "durable-issuer-replay-accepted",
            "rootSignedRegistryVerified": True,
            "registryEpochRollbackProtected": True,
            "durableReplayCommitPerformed": True,
            "issuerSequenceScopedAcrossKeyRotation": True,
            # Local signature/replay state is NOT a native runtime attestation.
            "nativeProductRuntimeVerified": False,
            "usableAsAuthoritativeNativeStatus": False,
            "nativeProductsConnected": False,
            "nativeWriteAuthorized": False,
            "harnessJobControlAuthorized": False,
        }
    except (sqlite3.Error, DurableTrustRejected, ReceiptRejected, ValueError,
            TypeError, KeyError) as exc:
        try:
            db.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise DurableTrustRejected(
            "trusted registry or durable replay transaction rejected"
        ) from exc
    finally:
        db.close()


def install_registry(
    signed_registry: bytes, *, pinned_root_public_key: bytes,
    state_path: Path, now: datetime,
) -> dict:
    """Atomically record signed registry, including standalone revocations."""
    return _perform(
        signed_registry, pinned_root_public_key=pinned_root_public_key,
        state_path=state_path, now=now, signed_receipt=None,
        expected_product=None,
    )


def verify_and_commit(
    signed_receipt: bytes, *, signed_registry: bytes,
    pinned_root_public_key: bytes, state_path: Path, now: datetime,
    expected_product: str | None = None,
) -> dict:
    """Verify authenticated publisher snapshot and atomically fence replay."""
    _require(type(signed_receipt) is bytes, "signed receipt bytes required")
    return _perform(
        signed_registry, pinned_root_public_key=pinned_root_public_key,
        state_path=state_path, now=now, signed_receipt=signed_receipt,
        expected_product=expected_product,
    )
