"""11th knife: real ephemeral keys, trust-root-signed manifests, durable SQLite."""
from __future__ import annotations

import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from test_signed_status_receipt import (
    receipt, key_record, sign, wire, NOW,
)
import durable_publisher_trust as t
from status_receipt import ReceiptRejected
from signed_status_receipt import TRUST_SCHEMA


def public_bytes(key):
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def seal_registry(root, registry):
    sig = root.sign(t.registry_message(registry))
    return wire({
        "schema": t.REGISTRY_ENVELOPE,
        "registry": copy.deepcopy(registry),
        "signature": {
            "algorithm": "Ed25519",
            "value": base64.b64encode(sig).decode("ascii"),
        },
    })


class DurablePublisherTrustTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="trisynora-pub-root-test-")
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "replay.sqlite"
        self.root = Ed25519PrivateKey.generate()
        self.publisher = Ed25519PrivateKey.generate()
        self.root_pub = public_bytes(self.root)
        self.registry = {
            "schema": TRUST_SCHEMA, "epoch": 7,
            "anchors": [key_record(self.publisher)],
        }
        self.sealed = seal_registry(self.root, self.registry)
        self.signed12 = wire(sign(self.publisher, receipt(seq=12)))

    def install(self, sealed=None, root_pub=None, db=None):
        return t.install_registry(
            self.sealed if sealed is None else sealed,
            pinned_root_public_key=self.root_pub if root_pub is None else root_pub,
            state_path=self.db_path if db is None else db,
            now=NOW,
        )

    def commit(self, signed=None, sealed=None, root_pub=None, db=None,
               expected_product="vera"):
        return t.verify_and_commit(
            self.signed12 if signed is None else signed,
            signed_registry=self.sealed if sealed is None else sealed,
            pinned_root_public_key=self.root_pub if root_pub is None else root_pub,
            state_path=self.db_path if db is None else db,
            now=NOW, expected_product=expected_product,
        )

    def deny(self, operation):
        with self.assertRaises(ReceiptRejected):
            operation()

    def test_install_root_signed_registry_without_native_connection(self):
        verdict = self.install()
        self.assertEqual(verdict["status"], "root-signed-registry-installed")
        self.assertFalse(verdict["nativeProductsConnected"])
        self.assertTrue(self.db_path.is_file())

    def test_authenticated_manifest_and_durable_replay_commit(self):
        res = self.commit()
        self.assertEqual(res["status"], "durable-issuer-replay-accepted")
        self.assertTrue(res["rootSignedRegistryVerified"])
        self.assertTrue(res["durableReplayCommitPerformed"])
        self.assertTrue(res["issuerSequenceScopedAcrossKeyRotation"])
        self.assertFalse(res["usableAsAuthoritativeNativeStatus"])
        self.assertFalse(res["nativeProductRuntimeVerified"])
        self.assertFalse(res["harnessJobControlAuthorized"])

    def test_replay_rejected_after_connection_reopens(self):
        self.commit()
        self.deny(self.commit)

    def test_high_watermark_persists_after_reopening_another_connection(self):
        self.commit()
        with sqlite3.connect(str(self.db_path)) as db:
            self.assertEqual(db.execute(
                "SELECT max_seq FROM issuer_sequences "
                "WHERE product='vera' AND instance='VeraTestInstance'",
            ).fetchone()[0], 12)
        self.deny(lambda: self.commit(
            signed=wire(sign(self.publisher, receipt(seq=11))),
        ))
        self.assertEqual(self.commit(
            signed=wire(sign(self.publisher, receipt(seq=13))),
        )["sequence"], 13)

    def test_two_threads_same_sequence_only_one_commits(self):
        def one(_):
            try:
                self.commit()
                return "committed"
            except ReceiptRejected:
                return "rejected"
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(one, range(2)))
        self.assertEqual(sorted(outcomes), ["committed", "rejected"])

    def test_parallel_different_sequences_cannot_roll_back(self):
        a = wire(sign(self.publisher, receipt(seq=12)))
        b = wire(sign(self.publisher, receipt(seq=13)))
        def one(value):
            try:
                self.commit(signed=value)
                return True
            except ReceiptRejected:
                return False
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes = list(workers.map(one, (a, b)))
        self.assertTrue(any(outcomes))
        with sqlite3.connect(str(self.db_path)) as db:
            max_seq = db.execute(
                "SELECT max_seq FROM issuer_sequences",
            ).fetchone()[0]
        self.assertEqual(max_seq, 13)
        self.deny(lambda: self.commit(signed=a))
        self.deny(lambda: self.commit(signed=b))

    def test_revocation_epoch_installed_without_a_receipt(self):
        self.install()
        newer = copy.deepcopy(self.registry)
        newer["epoch"] = 8
        newer["anchors"][0]["revoked"] = True
        sealed = seal_registry(self.root, newer)
        self.assertEqual(self.install(sealed=sealed)["registryEpoch"], 8)
        self.deny(self.commit)
        self.deny(lambda: self.commit(sealed=sealed))

    def test_rotation_to_new_key_preserves_issuer_sequence(self):
        self.commit()
        rotated = Ed25519PrivateKey.generate()
        newer = copy.deepcopy(self.registry)
        newer["epoch"] = 8
        newer["anchors"][0]["revoked"] = True
        newer["anchors"].append(key_record(
            rotated, kid="KeyAfterRotation",
        ))
        signed_registry = seal_registry(self.root, newer)
        self.install(sealed=signed_registry)
        old = wire(sign(self.publisher, receipt(seq=13)))
        self.deny(lambda: self.commit(signed=old, sealed=signed_registry))
        replay = wire(sign(rotated, receipt(seq=12), "KeyAfterRotation"))
        self.deny(lambda: self.commit(signed=replay, sealed=signed_registry))
        accepted = wire(sign(rotated, receipt(seq=13), "KeyAfterRotation"))
        verdict = self.commit(signed=accepted, sealed=signed_registry)
        self.assertEqual(verdict["sequence"], 13)
        self.deny(lambda: self.commit(signed=accepted, sealed=signed_registry))

    def test_manifest_rollback_after_reopen_is_rejected(self):
        self.install()
        newer = copy.deepcopy(self.registry)
        newer["epoch"] = 8
        newer["anchors"].append(key_record(
            Ed25519PrivateKey.generate(),
            kid="AdditionalTestKey",
        ))
        updated = seal_registry(self.root, newer)
        self.install(sealed=updated)
        self.deny(self.install)
        self.deny(self.commit)

    def test_same_epoch_different_valid_root_signed_manifest_rejected(self):
        self.install()
        changed = copy.deepcopy(self.registry)
        changed["anchors"][0]["notAfter"] = (
            NOW + timedelta(seconds=900)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        different = seal_registry(self.root, changed)
        self.deny(lambda: self.install(sealed=different))
        self.deny(lambda: self.commit(sealed=different))

    def test_explicit_root_change_cannot_replace_stored_root(self):
        self.install()
        attacker_root = Ed25519PrivateKey.generate()
        attacker_reg = copy.deepcopy(self.registry)
        attacker_reg["epoch"] = 8
        signed = seal_registry(attacker_root, attacker_reg)
        self.deny(lambda: self.install(
            sealed=signed, root_pub=public_bytes(attacker_root),
        ))

    def test_rogue_root_cannot_sign_trusted_registry(self):
        rogue = Ed25519PrivateKey.generate()
        self.deny(lambda: self.install(sealed=seal_registry(
            rogue, self.registry,
        )))

    def test_registry_content_tamper_but_stale_signature_rejected(self):
        parsed = __import__("json").loads(self.sealed)
        parsed["registry"]["epoch"] = 9
        self.deny(lambda: self.install(sealed=wire(parsed)))

    def test_registry_signature_malformed_rejected(self):
        parsed = __import__("json").loads(self.sealed)
        parsed["signature"]["value"] = "not-valid"
        self.deny(lambda: self.install(sealed=wire(parsed)))

    def test_unsigned_registry_rejected(self):
        parsed = __import__("json").loads(self.sealed)
        del parsed["signature"]
        self.deny(lambda: self.install(sealed=wire(parsed)))

    def test_wrong_registry_algorithm_rejected(self):
        parsed = __import__("json").loads(self.sealed)
        parsed["signature"]["algorithm"] = "none"
        self.deny(lambda: self.install(sealed=wire(parsed)))

    def test_untrusted_publisher_private_key_rejected(self):
        rogue = Ed25519PrivateKey.generate()
        self.deny(lambda: self.commit(
            signed=wire(sign(rogue, receipt(seq=12))),
        ))

    def test_registry_failed_update_does_not_erase_sequence(self):
        self.commit()
        invalid = copy.deepcopy(self.registry)
        invalid["epoch"] = 8
        invalid["anchors"][0]["revoked"] = True
        signed_new = seal_registry(self.root, invalid)
        self.deny(lambda: self.commit(sealed=signed_new))
        self.deny(self.commit)

    def test_trust_registry_can_register_h3_independently(self):
        key = Ed25519PrivateKey.generate()
        newer = copy.deepcopy(self.registry)
        newer["epoch"] = 8
        newer["anchors"].append(key_record(
            key, product="minimax-h3", instance="H3TestInstance",
            kid="H3Key",
        ))
        signed = seal_registry(self.root, newer)
        verdict = self.commit(
            signed=wire(sign(key, receipt(
                "minimax-h3", "H3TestInstance", seq=1), kid="H3Key",
            )), sealed=signed, expected_product="minimax-h3",
        )
        self.assertEqual(verdict["subjectKind"], "director-take")

    def test_native_permission_in_signed_snapshot_remains_forbidden(self):
        raw = receipt()
        raw["authority"]["grants"] = ["cancel"]
        from status_receipt import encode_body_digest
        raw["integrity"]["sha256"] = encode_body_digest(raw)
        self.deny(lambda: self.commit(
            signed=wire(sign(self.publisher, raw)),
        ))

    def test_replay_db_path_must_be_absolute(self):
        self.deny(lambda: self.install(db=Path("replay.sqlite")))

    def test_symlinked_db_path_forbidden(self):
        external = Path(self.tmp.name) / "elsewhere.sqlite"
        external.write_bytes(b"")
        alias = Path(self.tmp.name) / "link.sqlite"
        alias.symlink_to(external)
        self.deny(lambda: self.install(db=alias))

    def test_db_inside_git_checkout_forbidden(self):
        folder = Path(self.tmp.name) / "repo"
        folder.mkdir()
        (folder / ".git").mkdir()
        self.deny(lambda: self.install(db=folder / "ledger.sqlite"))

    def test_no_state_after_bad_root_signature(self):
        self.deny(lambda: self.install(sealed=seal_registry(
            Ed25519PrivateKey.generate(), self.registry,
        )))
        self.assertFalse(self.db_path.exists())

    def test_wrong_expected_product_denied(self):
        self.deny(lambda: self.commit(expected_product="pointflux"))

    def test_zero_exposed_native_jobs_or_connections(self):
        r = self.commit()
        self.assertFalse(r["nativeProductsConnected"])
        self.assertFalse(r["harnessJobControlAuthorized"])
        self.assertFalse(r["nativeWriteAuthorized"])
        self.assertFalse(r["usableAsAuthoritativeNativeStatus"])


if __name__ == "__main__":
    unittest.main()
