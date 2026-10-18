# PointFlux reference-to-evidence adapter (isolated prototype)

**Scope:** Convert an existing `pointflux-h3-shot-exchange/v1` JSON into the **existing TRISYNORA main-line** `ProjectSpec` + `ShotSpec` evidence *metadata* records. It does not replace PointFlux's native exchange schema, H3's own import/bind API, or the separate draft `trisynora.shot/v1` exchange-envelope family. Neither external product is invoked, installed, edited or bound.

This is not a 3D Camera/Rig/Motion converter, generated-media importer, H3 render controller, authenticated producer attestation or release gate. In particular **no ArtifactRecord, EvaluationRecord, HumanReview or DecisionRecord is fabricated**. Camera, timelines and asset references remain owned by native PointFlux/H3, not embedded in TRISYNORA's `ShotSpec` v1.

## Inputs and example

1. Export an exchange JSON with the existing isolated PointFlux `scripts/export-shot-exchange.mjs` branch.
2. Independently place the *original native Scene IR UTF-8 files* under an operator-approved local directory. Supply a small JSON `scene-map.json` mapping every exchanged `shotId` to its project-relative Scene IR path. Do not submit private native Scene IR to this repository.
3. In a standalone TRISYNORA checkout with Python 3.10+ and `requirements.txt` installed:

```sh
python -m trisynora.adapters.pointflux_reference \
  --exchange /operator/staging/pointflux-shot-handoff-v1.json \
  --scene-root /operator/approved/pointflux-scenes \
  --scene-map /operator/staging/scene-map.json \
  --tenant-id tenant_demo --project-name "Demo commercial" \
  --produced-at 2026-10-18T12:00:00+08:00 \
  --out /operator/staging/pointflux-reference-records.json
```

Example scene map: `{"shot_A":"shots/shot_A.pf.json"}`. The adapter **rejects** missing/mismatched mappings and mismatched scene SHA-256; `sourceSha256` is the digest of original UTF-8 Scene IR bytes, *not* the MP4, thumbnail or normalized JSON. The exchange file itself is independently hashed into ProjectSpec provenance. The output is **exclusive-create** and cannot be written under the scene root.

After conversion, `trisynora.validator.validate_bundle` validates records against published v1 schemas. **Do not append to EvidenceLedger or release anything** based on these metadata records alone. Any future authorized ledger import should perform independent file-byte verification and producer authentication at its trusted boundary.

## Deliberate compatibility constraints

- Only PointFlux-origin Scene IR `1.4`, `reference-only`, and `requiresExplicitBind=true`.
- Integer 1–120 FPS, <=60 seconds per shot, 1–30 shots. A mixed-FPS or mixed-resolution project is rejected rather than silently assigning a wrong `ProjectSpec.delivery`.
- Both `projectId` and `shotId` must be at least two characters; the TRISYNORA v1 record schema is stricter than the PointFlux ID pattern for one-character IDs. No automatic ID rewriting.
- Only project-relative local scene paths, no symlinks, URL fetches, shell, model calls, browser, GPU, media decoding, or writes to source repositories.
- Source hashes are byte-verified **against operator-supplied local files**. The adapter independently re-derives the **static Camera, output/FPS, timeline event frames, and source/target asset references** from those Scene IR bytes and rejects mismatches. This is not a replacement for PointFlux's native Scene IR schema/semantic validator, and it does not prove the producer's identity, H3/PF 3D coordinate equivalence, asset file existence, license, artistic quality, or successful rendering.
- `rights.*` are always false; `producer` is `operator-import`; evidence is not signed. Explicit user H3 bindings and native review authority remain unchanged.
- Repeating the identical exchange, tenant and timestamp makes deterministic record IDs. Changing the timestamp for an identical exchange is not a valid ledger replay; callers must preserve recording time.

## Tests

```sh
python -m unittest discover -s tests -p 'test_pointflux_reference_adapter.py' -v
```

The **10 offline tests** cover deterministic metadata mapping, Scene IR SHA-256 byte integrity, rejecting tampered Camera/Timeline/output/asset projections, forged digest, traversal, unauthorized handoff, unknown fields, nonfinite JSON, missing maps, one-character IDs and mixed delivery. An isolated source-equivalent validation run with the available `jsonschema` library passed 10/10 tests; **the full repository's native test suite and real PointFlux CLI/H3 service integration have not been executed**. These tests do **not** validate an actual H3 browser session, ComfyUI, real AI frames or an end-to-end PointFlux-H3-PointFlux run.

**Status:** draft branch only. Do not merge to `main`, deploy, auto-run GitHub Actions, or alter existing TRISYNORA constitutional PRs without owner review. Follow-up should use a separate product-owned PR and real local E2E after contract approval.
