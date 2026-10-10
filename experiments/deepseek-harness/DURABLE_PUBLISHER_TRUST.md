# Eleventh knife — root-signed publisher registry + persistent replay ledger

**A separate TRISYNORA security prototype.** The native Vera, MiniMax-H3 and PointFlux repositories remain untouched. No native publisher, signing key, product jobs or real model credentials are connected. The same three MCP tools remain the only exposed bridge surface.

## Threat addressed

The previous Ed25519 receipt verifier required a caller-provided publisher trust registry and a caller-provided replay floor. Both could be rolled back between process restarts if a caller supplied stale values. A key rotation could also inadvertently reset the sequence if a new key had its own sequence counter. A revoked key would remain usable if the consumer kept accepting an old registry.

The eleventh knife adds two *separate* layers:

- `durable_publisher_trust.py` authenticates the **entire publisher-key registry** using a separately provisioned **operator/root Ed25519 public key**. The root private key is never accessed, created or stored by this verifier, and no registry or publisher key is trusted merely because it appears beside a receipt. The registry is a signed, strict-format object, with explicit publisher product/instance/key, validity, and revoked state. The signature is bound to the fixed domain `TRISYNORA:PUBLISHER-REGISTRY:ED25519:V1\0`.
- The consumer stores a verified trust-registry epoch and SHA-256 digest and a **per-(product, instance) high-water sequence** in an isolated SQLite file. `BEGIN IMMEDIATE` serializes checks plus state updates, `synchronous=FULL` and normal SQLite transaction commit make accepted sequences durable across orderly process restarts. Updates using the same epoch but different registry contents fail; older epochs fail even with a valid old operator signature. This includes key revocation: once the newer signed revocation epoch is installed, an older registry cannot undo it. High-water sequence **survives a publisher-key rotation**, rejecting recycled earlier sequence values under a new key.

## Signed trust-registry envelope

```json
{
  "schema": "trisynora.signed-publisher-registry/v1",
  "registry": {
    "schema": "trisynora.product-publisher-trust/v1",
    "epoch": 9,
    "anchors": [
      {
        "product": "vera",
        "instanceId": "ExampleApprovedInstance",
        "keyId": "ExampleApprovedKey",
        "publicKeyBase64": "<32-byte public key, canonical Base64>",
        "notBefore": "2026-10-11T00:00:00Z",
        "notAfter": "2026-10-12T00:00:00Z",
        "revoked": false
      }
    ]
  },
  "signature": {
    "algorithm": "Ed25519",
    "value": "<64-byte operator signature, canonical Base64>"
  }
}
```

**Illustration only**: the example is NOT signed and MUST NOT be accepted. A real registry must be signed by an independently authorized operator root private key, and verified against a root public key separately provisioned to the consumer. The verifier deliberately contains **no signer** or private signing key. Cryptographic implementation uses the pinned upstream `cryptography==46.0.4`.

## Explicit API contracts

```python
from durable_publisher_trust import install_registry, verify_and_commit

# The registry/root must come from the independently approved operator.
# The ledger path must be an absolute path OUTSIDE every Git checkout.
install_registry(
    operator_signed_registry_blob,
    pinned_root_public_key=operator_root_public_bytes,
    state_path=isolated_absolute_sqlite_path,
    now=trusted_utc_clock,
)

# Atomic verify -> check durable issuer sequence -> commit. Read-only to
# NATIVE products; writes only the explicitly selected isolated ledger.
verdict = verify_and_commit(
    publisher_signed_receipt,
    signed_registry=operator_signed_registry_blob,
    pinned_root_public_key=operator_root_public_bytes,
    state_path=isolated_absolute_sqlite_path,
    now=trusted_utc_clock,
    expected_product="vera",
)
```

The first method can install a newer revoked registry **without waiting for another publisher receipt**. SQLite stores the trust root's SHA-256 fingerprint, signed registry epoch/digest, and independent monotonic sequence floor for each (product, instance). A different root is rejected even if it self-signs a higher epoch. The root itself cannot silently rotate; changing root trust requires a future separately reviewed out-of-band ceremony.

Only the operator-signed registry may authorize a publisher key. A publisher's own receipt remains independently verified through the **existing** signed-status-receipt Ed25519 and ninth-knife bounded status validator. Both cryptographic checks are required. No trust-on-first-use, no publisher key extracted from untrusted receipt as its own anchor, no shared jobs, no native execution.

**Verdict remains explicitly non-authoritative for native runtimes.** A successful test emits `durable-issuer-replay-accepted`, `rootSignedRegistryVerified=true`, `registryEpochRollbackProtected=true`, and `durableReplayCommitPerformed=true`. It also emits `nativeProductsConnected=false`, `nativeProductRuntimeVerified=false`, `usableAsAuthoritativeNativeStatus=false`, `harnessJobControlAuthorized=false`. This proves only the supplied, pinned test signer and the isolated ledger's operation—not that any installed Vera, H3 or PointFlux exporter exists.

## Acceptance

Run under the same pinned cryptography package as the tenth knife:

```sh
python -B -m unittest discover -s experiments/deepseek-harness -p "test_durable_publisher_trust.py" -v
python -B -m unittest discover -s experiments/deepseek-harness -p "test_*.py" -v
```

The regression must cover verified and revoked manifests, wrong operator root, signed-but-stale registry, same-epoch substitution, publisher key rotation with shared issuer sequence, two concurrent clients racing to accept the same receipt (one must fail), after-reopen replay rejection, invalid receipt/native grants, an external absolute ledger directory, and all earlier status/MCP isolation tests.

## Operational and security limits

- The caller must independently pin a trustworthy operator root and validate the current registry distribution. **Revocation is only effective once the authenticated new epoch has actually been installed**. A completely offline consumer cannot infer that a newer revocation exists.
- The SQLite path must be selected and owned by an OS-isolated trusted operator, outside ALL Git worktrees, with no native product mounts/credentials. Path checks reject ordinary symlinks and hardlink aliases but **are not a complete defense against a hostile concurrent local filesystem writer**. Restrict directory permissions and sandbox the process separately.
- This is a local SQLite proof with transaction serialization, NOT proof against power loss, storage corruption, disk rollback/restore from old backups, tampering by an actor with database write access, or distributed multi-machine replication/consensus. A database backup can still roll back both high-water and epoch unless an external monotonic anchor is added.
- No actual product-owned signer provisioning, native source attestation, OS key storage, production trust-anchor distribution, Windows deployment, or live product status API has been verified. The root itself has no self-updating authorization channel.
- Adding a read-only status MCP tool or a native producer adapter still requires a separate product-owner-approved PR, signed key provisioning and actual integration E2E.
- **Do not add native command, cancel, schedule, retry, import, approve, apply or write authorization to the status interface. Harness Jobs remain internal to Harness only.**
