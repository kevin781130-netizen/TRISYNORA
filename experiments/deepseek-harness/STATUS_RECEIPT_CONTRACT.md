# Ninth knife — isolated product-owned status snapshot receipt v1

This is a **contract and validation exercise**, not a native Vera/H3/PointFlux connection. No product exports are implemented; all green tests use synthetic samples created in memory. No stock Harness Jobs mirror is introduced.

## Intended ownership and three status subjects

| Declared producer | Native authority retained by product | Read-only receipt subject |
| --- | --- | --- |
| Vera | Agent run, verification, approvals, patch apply, cancellation | `verification-run` |
| MiniMax-H3 | Director workflow, ComfyUI, take review and retake | `director-take` |
| PointFlux | Scene IR, render, inspection, optimization, file approval | `render-result` |

The receiver is not a remote controller: no start/stop/cancel/retry/apply/approve URL, command, filesystem path, native job identifier mapping, arbitrary log text, secret or writable handle can appear in a v1 receipt.

## V1 strict JSON body

A synthetic Vera example (illustrative only; `integrity.sha256` below must be recomputed by the test helper from canonical JSON for acceptance):

```json
{
  "schema": "trisynora.status-receipt/v1",
  "producer": {"product": "vera", "instanceId": "OfflineTestOnly"},
  "subject": {"kind": "verification-run", "id": "SyntheticRun001"},
  "state": {
    "phase": "running",
    "outcome": "pending",
    "progress": {"completed": 2, "total": 7}
  },
  "provenance": {
    "sourceRevision": "1111111111111111111111111111111111111111111111111111111111111111",
    "evidenceSha256": "2222222222222222222222222222222222222222222222222222222222",
    "sourceKind": "native-product-export"
  },
  "issuedAt": "2026-10-11T05:59:45Z",
  "expiresAt": "2026-10-11T06:01:00Z",
  "sequence": 9,
  "authority": {"mode": "read-only-status", "grants": [], "sideEffects": false},
  "integrity": {"algorithm": "sha256", "sha256": "RECALCULATE-FROM-CANONICAL-BODY"}
}
```

V1 canonical body = JSON of all receipt fields except `integrity`, encoded UTF-8 with sorted keys, no whitespace separators and escaped non-ASCII; SHA-256 digest in lowercase hex. This digest catches accidental changes/tampering **only if** compared to a separately trusted value. Because an attacker can recompute it, it is **not an origin signature**. The strings declaring `sourceKind`, `instanceId`, revision or evidence hash are untrusted claims until externally authenticated.

**Validation limits:** at most 8 KiB UTF-8; reject duplicate JSON keys, missing/extra fields, undeclared producer kinds, pathlike or Unicode identifiers, negative or out-of-range progress, inconsistent terminal phase/outcome, timestamp formats other than whole-second UTC, expired/future-issued snapshots, expiry window longer than five minutes, invalid digests and grants/sideEffects. The consumer may pass a last-seen sequence to reject same or older sequences, but this *still cannot prove the producer* and does not write any replay ledger or query native databases.

`validate(data, now=..., expected_product=..., last_seen_sequence=...)` only returns sanitized metadata and permanently declares:

```json
{
  "status": "untrusted-snapshot-validated",
  "integrityChecked": true,
  "producerAuthenticityVerified": false,
  "nativeProductsConnected": false,
  "nativeWriteAuthorized": false,
  "harnessJobControlAuthorized": false,
  "usableAsAuthoritativeNativeStatus": false
}
```

Actual validation also returns allowlisted product, subject, phase, outcome, progress, sequence and expiry. It never returns opaque raw input.

## Acceptance, trust and remaining prerequisites

The executable validator is `status_receipt.py`. Synthetic negative/positive tests are in `test_status_receipt.py`, included in the existing MCP isolation CI unittest discovery.

Before **any** future Harness-facing read-only status tool or native status claim, a separate review must approve **all** of:
1. Native product team-owned exporter emitting accurate status and agreed provenance. Each product keeps its own execution and mutation ownership.
2. Product identity verification using explicit, pinned publisher trust anchors and asymmetric signatures or an equivalent independently authenticated channel, with rotation and revocation policy. Self-hash alone must never suffice.
3. A safe, independent read-only exchange outside native Git worktrees, with replay/freshness storage, durable sequencing, and a race-safe OS sandbox.
4. Integration into a separately reviewed *read-only* TRISYNORA endpoint — **never** Harness `job.list/job.kill` or native approval powers.
5. New real-product integration E2E and threat-model review. The existing three-tool MCP surface and ownership gate must remain unchanged until that review.

**Not verified:** actual producer authenticity, native state validity, signed receipts, Windows deployability, server integrations, network isolation from stock DSH tools, product execution/release readiness. All three native product repos remain untouched.
