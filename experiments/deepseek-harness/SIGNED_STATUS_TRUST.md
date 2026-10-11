# Tenth knife — Ed25519 publisher identity and externally pinned product trust

This is an **independent signature-verification prototype**, not a live Vera,
MiniMax-H3 or PointFlux connector. No product runtime, signer service, private
key, or real product credential is installed or modified. All test signing keys
are generated **ephemerally in process** and discarded after each run.

## Why the ninth knife was not enough

The previous `status_receipt.py` checks format, bounded lifetime, progress,
and a body SHA-256. A forger can recompute SHA-256. It **cannot authenticate**
that Vera actually published a run state, that H3 approved a Take, or that
PointFlux produced a render.

`signed_status_receipt.py` now adds the **Ed25519** signature-verification
layer using the pinned external `cryptography==46.0.4` dependency (no custom
cryptography). It continues to use the ninth knife's strict inner-receipt
validation before accepting any signature.

## Wire contract

A signed envelope has exactly these three top-level fields:

```json
{
  "schema": "trisynora.signed-status-receipt/v1",
  "receipt": "<entire validated v1 status receipt OBJECT>",
  "signature": {
    "algorithm": "Ed25519",
    "keyId": "ApprovedPublisherKeyId",
    "value": "<canonical Base64, 64-byte Ed25519 signature>"
  }
}
```

The signature covers a fixed domain separator
`TRISYNORA:STATUS-RECEIPT:ED25519:V1\0` followed by canonical JSON:

```json
{
  "algorithm": "Ed25519",
  "keyId": "<approved signer key ID>",
  "receipt": "<entire inner receipt OBJECT, including its SHA-256>",
  "schema": "trisynora.signed-status-receipt/v1"
}
```

The JSON string values above illustrate the fields; sign the actual canonical
JSON object, not the illustrative string or pretty-printed Markdown.

## Trusted key registry — supplied OUT-OF-BAND ONLY

The registry is a separate API argument; **never read it from the receipt**,
an untrusted file adjacent to the receipt, a model answer or an arbitrary URL.
Its provenance must be independently reviewed/controlled by the product owner
and operator; merely matching it cannot establish that the operator selected
a genuine native publisher.

```json
{
  "schema": "trisynora.product-publisher-trust/v1",
  "epoch": 7,
  "anchors": [
    {
      "product": "vera",
      "instanceId": "ApprovedInstance",
      "keyId": "ApprovedKey",
      "publicKeyBase64": "<canonical Base64, 32-byte Ed25519 public key>",
      "notBefore": "2026-10-10T00:00:00Z",
      "notAfter": "2026-10-12T00:00:00Z",
      "revoked": false
    }
  ]
}
```

**This is a structural EXAMPLE, not a configured trust store.**
There are **zero production trust anchors** and no publisher signing keys
checked into this repo. Test signers are created in memory, scoped separately
to Vera, H3 and PointFlux; not a single key is shared across product identities.

`verify_signed(..., now, trust_registry, minimum_registry_epoch,
replay_floor, expected_product)` enforces:

- Strict JSON fields and bounded 12 KiB signed envelope; strict Base64 length.
- SHA-256 integrity, expiration ≤300 seconds, product/subject and no native
  permissions, using the existing v1 receipt validator.
- Ed25519 over the exact domain-separated canonical payload.
- Exact bound **product + instanceId + keyId**, not key-name-only matching.
- Key validity window and explicit revocation; no trust-on-first-use or
  implicit key discovery; distinct keys for distinct identities.
- A separately pinned minimum trust-registry epoch to reject old trust-list
  rollback; removal/revocation must update an externally controlled registry.
- An explicitly supplied replay floor scoped to the issuer identity. Rejects
  missing floor, duplicate sequence, old sequence, invalid counters.

The verifier **does not write/update** any durable replay ledger, nor does it
verify the registry was obtained through a trustworthy deployment channel.
An actual product integration must atomically commit its new floor before
presenting trusted state. Read-only test acceptance is therefore never
promoted to a production fact or a native command.

The successful verdict is
`pinned-publisher-key-signature-verified`. It means the envelope verifies
against the **caller-provided trust registry**. With test-only keys, this
authenticates only the test signer, not an actual Vera/H3/PointFlux process.
The returned fields deliberately include:

```json
{
  "publisherKeyMatchedOutOfBandTrust": true,
  "nativeProductRuntimeVerified": false,
  "durableReplayCommitPerformed": false,
  "usableAsAuthoritativeNativeStatus": false,
  "nativeProductsConnected": false,
  "nativeWriteAuthorized": false,
  "harnessJobControlAuthorized": false
}
```

## Acceptance & remaining external gates

```sh
python -m pip install cryptography==46.0.4
python -B -m unittest discover -s experiments/deepseek-harness -p 'test_signed_status_receipt.py' -v
python -B -m unittest discover -s experiments/deepseek-harness -p 'test_*.py' -v
```

The negative tests cover altered-but-rehashed bodies, attacker-generated
private keys, product identity substitution, bad signatures, revoked/expired/
future keys, duplicate/reused public keys, registry rollback, replay,
malformed Base64, unauthorized native grants and unrelated Jobs controls.

**Remaining NOT CONNECTED / NOT VERIFIED:** product-owned signer provisioning
and attestation, real product output authenticity, a durable atomic replay
database, trusted key registry distribution, rotation/revocation operating
procedures, published status dashboard or additional MCP API, authorized
product read-only status adapters, actual 3-product handshake, Windows native
qualification and production network isolation. The separate Harness
sandbox still must not mount native source or credentials.

**No new MCP tools, no Harness Jobs mirroring, no native product writes, and
PR #8 remains a Draft until separately authorized.**
