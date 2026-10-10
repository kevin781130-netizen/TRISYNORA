"""Cryptographic status receipt tests: all private keys are ephemeral in-memory.

No credentials, fixtures, native app runtimes or production trust anchors.
The receiver NEVER signs; only this isolated test module constructs signatures.
"""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone, timedelta
import importlib.util
from pathlib import Path
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

HERE = Path(__file__).resolve().parent


def load(fname, name):
    spec = importlib.util.spec_from_file_location(name, HERE / fname)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


s = load("status_receipt.py", "original_status_contract")
v = load("signed_status_receipt.py", "trusted_ed25519_receipt")
NOW = datetime(2026, 10, 11, 6, 0, 0, tzinfo=timezone.utc)


def dt(delta):
    return (NOW + timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def receipt(product="vera", instance="VeraTestInstance", seq=12):
    raw = {
        "schema": "trisynora.status-receipt/v1",
        "producer": {"product": product, "instanceId": instance},
        "subject": {"kind": s.PRODUCT_KIND[product], "id": "Synthetic0001"},
        "state": {"phase": "running", "outcome": "pending",
                  "progress": {"completed": 1, "total": 5}},
        "provenance": {
            "sourceRevision": "a" * 64, "evidenceSha256": "b" * 64,
            "sourceKind": "native-product-export",
        },
        "issuedAt": dt(-20), "expiresAt": dt(80),
        "sequence": seq,
        "authority": {"mode": "read-only-status", "grants": [],
                      "sideEffects": False},
        "integrity": {"algorithm": "sha256", "sha256": ""},
    }
    raw["integrity"]["sha256"] = s.encode_body_digest(raw)
    return raw


def key_record(private, product="vera", instance="VeraTestInstance",
               kid="SyntheticKeyA", **changes):
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    obj = {
        "product": product, "instanceId": instance, "keyId": kid,
        "publicKeyBase64": base64.b64encode(public).decode("ascii"),
        "notBefore": dt(-1000), "notAfter": dt(1000), "revoked": False,
    }
    obj.update(changes)
    return obj


def sign(private, r, kid="SyntheticKeyA"):
    sig = private.sign(v.signing_message(r, kid))
    return {
        "schema": v.SIGNED_SCHEMA,
        "receipt": copy.deepcopy(r),
        "signature": {
            "algorithm": "Ed25519",
            "keyId": kid,
            "value": base64.b64encode(sig).decode("ascii"),
        },
    }


def wire(envelope):
    return s.canonical_bytes(envelope)


class SignedStatusTrustTests(unittest.TestCase):
    def setUp(self):
        self.private = Ed25519PrivateKey.generate()
        self.r = receipt()
        self.e = sign(self.private, self.r)
        self.registry = {
            "schema": v.TRUST_SCHEMA, "epoch": 7,
            "anchors": [key_record(self.private)],
        }
        self.floor = {("vera", "VeraTestInstance", "SyntheticKeyA"): 11}

    def run_verified(self, envelope=None, registry=None, floor=None,
                     **options):
        return v.verify_signed(
            wire(self.e if envelope is None else envelope),
            now=NOW, trust_registry=self.registry if registry is None
            else registry,
            minimum_registry_epoch=7,
            replay_floor=self.floor if floor is None else floor,
            **options,
        )

    def deny(self, envelope=None, registry=None, floor=None, **options):
        with self.assertRaises(s.ReceiptRejected):
            self.run_verified(envelope, registry, floor, **options)

    def test_ed25519_vera_signature_verifies_against_explicit_pinned_key(self):
        result = self.run_verified(expected_product="vera")
        self.assertEqual(result["status"],
                         "pinned-publisher-key-signature-verified")
        self.assertTrue(result["publisherKeyMatchedOutOfBandTrust"])
        self.assertTrue(result["producerAuthenticityVerified"])
        self.assertFalse(result["nativeProductRuntimeVerified"])
        self.assertFalse(result["usableAsAuthoritativeNativeStatus"])
        self.assertFalse(result["durableReplayCommitPerformed"])
        self.assertFalse(result["harnessJobControlAuthorized"])
        self.assertFalse(result["nativeProductsConnected"])

    def test_h3_take_signature_uses_own_key_and_scope(self):
        key = Ed25519PrivateKey.generate()
        r = receipt("minimax-h3", "H3TestInstance")
        e = sign(key, r, "H3OnlyKey")
        registry = {"schema": v.TRUST_SCHEMA, "epoch": 7,
                    "anchors": [key_record(
                        key, "minimax-h3", "H3TestInstance", "H3OnlyKey",
                    )]}
        floor = {("minimax-h3", "H3TestInstance", "H3OnlyKey"): 11}
        self.assertEqual(
            self.run_verified(e, registry, floor)["subjectKind"],
            "director-take",
        )

    def test_pointflux_render_has_distinct_product_identity(self):
        key = Ed25519PrivateKey.generate()
        r = receipt("pointflux", "PFTestInstance")
        e = sign(key, r, "PFOnlyKey")
        registry = {"schema": v.TRUST_SCHEMA, "epoch": 7,
                    "anchors": [key_record(
                        key, "pointflux", "PFTestInstance", "PFOnlyKey",
                    )]}
        floor = {("pointflux", "PFTestInstance", "PFOnlyKey"): 11}
        self.assertEqual(
            self.run_verified(e, registry, floor)["subjectKind"],
            "render-result",
        )

    def test_rehashing_but_not_resigning_fails(self):
        e = copy.deepcopy(self.e)
        e["receipt"]["state"]["progress"]["completed"] = 4
        e["receipt"]["integrity"]["sha256"] = s.encode_body_digest(e["receipt"])
        self.deny(e)

    def test_attacker_own_key_cannot_impersonate_pinned_publisher(self):
        attacker = Ed25519PrivateKey.generate()
        self.deny(sign(attacker, self.r))

    def test_cross_product_publisher_key_substitution_fails(self):
        e = copy.deepcopy(self.e)
        e["receipt"] = receipt("pointflux", "VeraTestInstance")
        e = sign(self.private, e["receipt"])
        self.deny(e)

    def test_signature_byte_flip_fails(self):
        e = copy.deepcopy(self.e)
        raw = bytearray(base64.b64decode(e["signature"]["value"]))
        raw[0] ^= 1
        e["signature"]["value"] = base64.b64encode(raw).decode()
        self.deny(e)

    def test_wrong_key_id_fails(self):
        e = sign(self.private, self.r, "OtherKey")
        self.deny(e)

    def test_unknown_signer_scope_fails(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"][0]["instanceId"] = "SomeoneElse"
        self.deny(registry=registry)

    def test_revoked_key_fails_even_for_fresh_signature(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"][0]["revoked"] = True
        self.deny(registry=registry)

    def test_expired_signing_key_fails(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"][0]["notAfter"] = dt(-1)
        self.deny(registry=registry)

    def test_not_yet_valid_signing_key_fails(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"][0]["notBefore"] = dt(10)
        self.deny(registry=registry)

    def test_receipt_expiry_after_key_validity_fails(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"][0]["notAfter"] = dt(15)
        self.deny(registry=registry)

    def test_old_registry_epoch_rollbacks_fail(self):
        registry = copy.deepcopy(self.registry)
        registry["epoch"] = 6
        self.deny(registry=registry)

    def test_wrong_epoch_type_fails(self):
        registry = copy.deepcopy(self.registry)
        registry["epoch"] = True
        self.deny(registry=registry)

    def test_revocation_must_be_boolean(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"][0]["revoked"] = "false"
        self.deny(registry=registry)

    def test_duplicate_signer_binding_fails(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"].append(copy.deepcopy(registry["anchors"][0]))
        self.deny(registry=registry)

    def test_same_public_key_cannot_be_reused_for_other_product(self):
        registry = copy.deepcopy(self.registry)
        record = copy.deepcopy(registry["anchors"][0])
        record.update(product="pointflux", instanceId="PFTestInstance",
                      keyId="DifferentKey")
        registry["anchors"].append(record)
        self.deny(registry=registry)

    def test_malformed_public_key_fails(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"][0]["publicKeyBase64"] = "not-base64"
        self.deny(registry=registry)

    def test_wrong_public_key_size_fails(self):
        registry = copy.deepcopy(self.registry)
        registry["anchors"][0]["publicKeyBase64"] = base64.b64encode(
            b"x" * 31).decode()
        self.deny(registry=registry)

    def test_unknown_registry_fields_fail(self):
        registry = copy.deepcopy(self.registry)
        registry["source"] = "untrusted-payload"
        self.deny(registry=registry)

    def test_missing_replay_state_fails_closed(self):
        self.deny(floor={})
        self.deny(floor={("vera", "Other", "SyntheticKeyA"): 0})

    def test_duplicate_replay_number_fails(self):
        self.deny(floor={("vera", "VeraTestInstance", "SyntheticKeyA"): 12})

    def test_out_of_order_replay_fails(self):
        self.deny(floor={("vera", "VeraTestInstance", "SyntheticKeyA"): 13})

    def test_wrong_replay_type_fails(self):
        self.deny(floor={("vera", "VeraTestInstance", "SyntheticKeyA"): True})

    def test_fresh_replay_number_is_accepted_but_not_committed(self):
        a = self.run_verified()
        self.assertEqual(a["sequence"], 12)
        self.assertFalse(a["durableReplayCommitPerformed"])
        self.deny(floor={("vera", "VeraTestInstance", "SyntheticKeyA"): 12})

    def test_key_rotation_requires_new_pinned_anchor_and_ledger(self):
        rotated = Ed25519PrivateKey.generate()
        e = sign(rotated, self.r, "SyntheticRotated")
        self.deny(e)
        registry = copy.deepcopy(self.registry)
        registry["epoch"] = 8
        registry["anchors"].append(key_record(
            rotated, kid="SyntheticRotated",
        ))
        floor = dict(self.floor)
        floor[("vera", "VeraTestInstance", "SyntheticRotated")] = 0
        result = v.verify_signed(
            wire(e), now=NOW, trust_registry=registry,
            minimum_registry_epoch=8, replay_floor=floor,
        )
        self.assertEqual(result["publisherKeyId"], "SyntheticRotated")
        self.assertEqual(result["registryEpoch"], 8)

    def test_algorithm_downgrade_fails(self):
        e = copy.deepcopy(self.e)
        e["signature"]["algorithm"] = "none"
        self.deny(e)

    def test_unknown_envelope_field_fails(self):
        e = copy.deepcopy(self.e)
        e["trustRegistry"] = self.registry
        self.deny(e)

    def test_unsigned_envelope_fails(self):
        e = copy.deepcopy(self.e)
        del e["signature"]
        self.deny(e)

    def test_signature_noncanonical_base64_fails(self):
        e = copy.deepcopy(self.e)
        e["signature"]["value"] += "\n"
        self.deny(e)

    def test_malicious_grants_still_denied_even_if_signed(self):
        r = receipt()
        r["authority"]["grants"] = ["cancel-run"]
        r["integrity"]["sha256"] = s.encode_body_digest(r)
        self.deny(sign(self.private, r))

    def test_malicious_execution_command_denied_even_if_signed(self):
        r = receipt()
        r["nativeCommand"] = "rm -rf /"
        r["integrity"]["sha256"] = s.encode_body_digest(r)
        self.deny(sign(self.private, r))

    def test_nested_duplicate_json_field_fails(self):
        data = wire(self.e).replace(
            b'"sequence":12', b'"sequence":12,"sequence":13')
        with self.assertRaises(s.ReceiptRejected):
            v.verify_signed(data, now=NOW, trust_registry=self.registry,
                            minimum_registry_epoch=7, replay_floor=self.floor)

    def test_expired_signed_receipt_fails_even_with_good_crypto(self):
        r = receipt()
        r["issuedAt"], r["expiresAt"] = dt(-200), dt(-1)
        r["integrity"]["sha256"] = s.encode_body_digest(r)
        self.deny(sign(self.private, r))

    def test_wrong_expected_product_fails(self):
        self.deny(expected_product="pointflux")

    def test_no_auto_trust_or_key_download(self):
        with self.assertRaises((TypeError, s.ReceiptRejected)):
            v.verify_signed(wire(self.e), now=NOW, trust_registry=None,
                            minimum_registry_epoch=7, replay_floor=self.floor)

    def test_oversized_envelope_denied(self):
        with self.assertRaises(s.ReceiptRejected):
            v.verify_signed(b"0" * (v.MAX_SIGNED_BYTES + 1), now=NOW,
                            trust_registry=self.registry,
                            minimum_registry_epoch=7, replay_floor=self.floor)


if __name__ == "__main__":
    unittest.main()
