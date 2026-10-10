"""Adversarial isolated status receipt contract regression (synthetic data only)."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "trisynora_status_receipt_under_test", HERE / "status_receipt.py",
)
assert spec and spec.loader
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
NOW = datetime(2026, 10, 11, 6, 0, 0, tzinfo=timezone.utc)


def _date(delta: int) -> str:
    return (NOW + timedelta(seconds=delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def fixture(product="vera"):
    r = {
        "schema": "trisynora.status-receipt/v1",
        "producer": {"product": product, "instanceId": "OfflineTestOnly"},
        "subject": {"kind": s.PRODUCT_KIND[product], "id": "SyntheticRun001"},
        "state": {
            "phase": "running",
            "outcome": "pending",
            "progress": {"completed": 2, "total": 7},
        },
        "provenance": {
            "sourceRevision": "1" * 64,
            "evidenceSha256": "2" * 64,
            "sourceKind": "native-product-export",
        },
        "issuedAt": _date(-15),
        "expiresAt": _date(60),
        "sequence": 9,
        "authority": {"mode": "read-only-status",
                      "grants": [], "sideEffects": False},
        "integrity": {"algorithm": "sha256", "sha256": ""},
    }
    return r


def encode(r, rehash=True):
    r = copy.deepcopy(r)
    if rehash:
        r["integrity"]["sha256"] = s.encode_body_digest(r)
    return s.canonical_bytes(r)


class StatusReceiptContractTests(unittest.TestCase):
    def setUp(self):
        self.receipt = fixture()
        self.data = encode(self.receipt)

    def verify(self, r=None, *, rehash=True, **options):
        return s.validate(
            self.data if r is None else encode(r, rehash=rehash),
            now=NOW, **options,
        )

    def reject(self, r, *, rehash=True, **options):
        with self.assertRaises(s.ReceiptRejected):
            self.verify(r, rehash=rehash, **options)

    def test_vera_running_verification_receipt_is_untrusted(self):
        r = self.verify(expected_product="vera")
        self.assertEqual(r["status"], "untrusted-snapshot-validated")
        self.assertEqual(r["subjectKind"], "verification-run")
        self.assertEqual(r["progress"], {"completed": 2, "total": 7})
        self.assertFalse(r["producerAuthenticityVerified"])
        self.assertFalse(r["usableAsAuthoritativeNativeStatus"])
        self.assertFalse(r["harnessJobControlAuthorized"])
        self.assertFalse(r["nativeProductsConnected"])

    def test_h3_take_contract(self):
        r = self.verify(fixture("minimax-h3"), expected_product="minimax-h3")
        self.assertEqual(r["subjectKind"], "director-take")

    def test_pointflux_render_contract(self):
        r = self.verify(fixture("pointflux"), expected_product="pointflux")
        self.assertEqual(r["subjectKind"], "render-result")

    def test_terminal_outcomes_supported_without_changing_authority(self):
        for outcome in ("success", "failed", "blocked", "cancelled"):
            with self.subTest(outcome=outcome):
                r = fixture()
                r["state"]["phase"] = "finished"
                r["state"]["outcome"] = outcome
                x = self.verify(r)
                self.assertFalse(x["usableAsAuthoritativeNativeStatus"])

    def test_reference_hash_is_not_signature(self):
        r = fixture()
        r["state"]["progress"]["completed"] = 6
        forged = self.verify(r, rehash=True)
        self.assertTrue(forged["integrityChecked"])
        self.assertFalse(forged["producerAuthenticityVerified"])

    def test_modified_body_rejected_if_digest_not_recomputed(self):
        r = fixture()
        r["integrity"]["sha256"] = s.encode_body_digest(r)
        r["state"]["progress"]["completed"] = 6
        self.reject(r, rehash=False)

    def test_wrong_expected_product_denied(self):
        self.reject(fixture(), expected_product="pointflux")

    def test_cross_product_subject_denied(self):
        r = fixture("minimax-h3")
        r["subject"]["kind"] = "verification-run"
        self.reject(r)

    def test_unknown_product_denied(self):
        r = fixture()
        r["producer"]["product"] = "deepseek-harness"
        self.reject(r)

    def test_product_id_cannot_be_path(self):
        r = fixture()
        r["subject"]["id"] = "../../.vera/latest_run.json"
        self.reject(r)

    def test_issuer_id_cannot_be_path(self):
        r = fixture()
        r["producer"]["instanceId"] = "/tmp/native"
        self.reject(r)

    def test_receipt_cannot_embed_raw_log_or_commands(self):
        r = fixture()
        r["command"] = "kill agent"
        self.reject(r)

    def test_receipt_cannot_embed_action_or_cancel_link(self):
        r = fixture()
        r["authority"]["cancelUrl"] = "http://127.0.0.1/delete"
        self.reject(r)

    def test_native_grants_denied(self):
        r = fixture()
        r["authority"]["grants"] = ["stop"]
        self.reject(r)

    def test_native_side_effects_denied(self):
        r = fixture()
        r["authority"]["sideEffects"] = True
        self.reject(r)

    def test_mode_must_be_read_only_status(self):
        r = fixture()
        r["authority"]["mode"] = "approval"
        self.reject(r)

    def test_progress_cannot_overflow(self):
        r = fixture()
        r["state"]["progress"]["completed"] = 9
        self.reject(r)

    def test_total_cannot_be_zero(self):
        r = fixture()
        r["state"]["progress"]["total"] = 0
        self.reject(r)

    def test_booleans_are_not_integers(self):
        r = fixture()
        r["sequence"] = True
        self.reject(r)

    def test_running_cannot_claim_terminal_success(self):
        r = fixture()
        r["state"]["outcome"] = "success"
        self.reject(r)

    def test_finished_cannot_be_pending(self):
        r = fixture()
        r["state"]["phase"] = "finished"
        self.reject(r)

    def test_queued_progress_must_be_zero(self):
        r = fixture()
        r["state"]["phase"] = "queued"
        self.reject(r)

    def test_expired_receipt_denied(self):
        r = fixture()
        r["issuedAt"], r["expiresAt"] = _date(-90), _date(-1)
        self.reject(r)

    def test_future_issued_receipt_denied(self):
        r = fixture()
        r["issuedAt"], r["expiresAt"] = _date(1), _date(50)
        self.reject(r)

    def test_ttl_over_five_minutes_denied(self):
        r = fixture()
        r["issuedAt"], r["expiresAt"] = _date(-30), _date(280)
        self.reject(r)

    def test_replay_seq_denied_by_external_prior_counter(self):
        self.reject(fixture(), last_seen_sequence=9)
        self.reject(fixture(), last_seen_sequence=10)
        self.assertEqual(self.verify(last_seen_sequence=8)["sequence"], 9)

    def test_unaware_now_denied(self):
        with self.assertRaises(s.ReceiptRejected):
            s.validate(self.data, now=datetime(2026, 10, 11))

    def test_digest_must_be_hex(self):
        r = fixture()
        r["provenance"]["evidenceSha256"] = "something"
        self.reject(r)

    def test_duplicate_json_keys_denied(self):
        raw = self.data.decode().replace(
            '"sequence":9', '"sequence":9,"sequence":10',
        ).encode()
        with self.assertRaises(s.ReceiptRejected):
            s.validate(raw, now=NOW)

    def test_unicode_escape_does_not_bypass_identifier_rules(self):
        r = fixture()
        r["subject"]["id"] = "Full\uFF0FWidth"
        self.reject(r)

    def test_oversize_denied_before_json_parse(self):
        with self.assertRaises(s.ReceiptRejected):
            s.validate(b"x" * (s.MAX_BYTES + 1), now=NOW)

    def test_missing_fields_fail_closed(self):
        r = fixture()
        del r["provenance"]
        self.reject(r)

    def test_wrong_schema_denied(self):
        r = fixture()
        r["schema"] = "trisynora.status-receipt/v2"
        self.reject(r)

    def test_bad_timestamp_denied(self):
        r = fixture()
        r["issuedAt"] = "2026-02-30T06:00:00Z"
        self.reject(r)

    def test_source_kind_must_be_native_declared(self):
        r = fixture()
        r["provenance"]["sourceKind"] = "harness-mock"
        self.reject(r)

    def test_unknown_nested_state_field_denied(self):
        r = fixture()
        r["state"]["script"] = "echo"
        self.reject(r)

    def test_encoding_is_bounded_and_side_effect_free(self):
        self.assertLessEqual(len(self.data), s.MAX_BYTES)
        self.assertEqual(self.data, encode(fixture()))


if __name__ == "__main__":
    unittest.main()
