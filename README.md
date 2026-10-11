# TRISYNORA v1 — Evidence Contract Kernel

Seven **portable, strict JSON Schema 2020-12 contracts**, plus a read-only validator that checks lineage, per-bundle replay/idempotency, evaluation status consistency and (optionally) local SHA-256 evidence bytes. The validator does not invoke Vera, MiniMax H3 or PointFlux; they retain their own permission and execution authorities.

## Run

Requires Python 3.10+ and `jsonschema==4.26.0` (MIT; dependencies carry their own licenses).

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m trisynora.validator examples/demo-bundle.json
python -m trisynora.validator examples/demo-bundle.json --evidence-root /verified/assets
```

The last command requires real local files named in the bundle, and intentionally fails if the bytes are missing or different. **Do not treat schema-only validation as evidence verification.** Run the CLI with the approved local evidence directory to verify file digests.

## Seven contracts

`docs/contracts/{ProjectSpec,ShotSpec,ArtifactRecord,EvaluationRecord,HumanReview,DecisionRecord,RevisionEdge}.schema.json`

All carry `schema_version=trisynora/v1`, `record_type`, `record_id`, `event_id`, `tenant_id`, `project_id`, UTC-capable `produced_at`, producer metadata, and source provenance. Additional/unknown fields are rejected.

## Explicit trust and privacy boundaries

- A SHA-256 value in JSON is only a **claim** until the validator reads the operator-approved file bytes. Source provenance is not cryptographically authenticated by this package.
- This tool does not run artists' approvals or publish content. `release_approved` is **always false**; only a future authenticated service may make release decisions.
- The CLI **rejects all HumanReview events** without verified identity. Python callers may pass `trusted_human_reviewers={event_id: authenticated_reviewer_id}` only after a trusted auth boundary independently checks the person. The mapping is not authentication by itself.
- Input bundles are restricted to a single tenant/project. There is no shared cross-tenant training or query service.
- `rights.*` fields record the owner's consent; they do not grant permission by themselves or override consent withdrawal.
- `event_id` replay and identity are enforced **within one submitted bundle only**. Durable idempotency, append-only storage, consent revocation, and cross-bundle version migration belong to the next milestone.
- Validate `source.sha256` against real upstream data at adapter boundaries; this kernel does not retrieve external sources or trust LLM-supplied descriptions.
- JSON Schemas and basic validation are interoperability plumbing, not a private proprietary scoring system or anti-distillation mechanism.

## Rebuild schemas

`python make_schemas.py` writes the checked-in self-contained schemas. Review the diff and run tests before changing published v1 contracts. Never silently replace v1 with v2.

## Durable evidence ledger (Cut 2)

`trisynora.ledger.EvidenceLedger` is an embedded, append-only SQLite evidence journal.
It revalidates the entire project lineage under an atomic transaction, refuses
unverified artifact or Judge report bytes, blocks `HumanReview` until a separate
authenticated service exists, and supports replay-safe event IDs across process
restarts. Run `python -m unittest discover -s tests -v` for the full suite.

The hash chain detects uncoordinated modification of database rows, **not**
forgery by a privileged database administrator. It is not a signature or trusted
identity system. Store private evidence outside public repositories.


## PointFlux temporal Judge → Evidence Ledger (read-only)

Import **existing**, local PointFlux \`render-manifest.json\`, \`temporal-judgement.json\` and the associated MP4; the adapter **never calls PointFlux or any Agent**. Inputs must all be within the operator-approved evidence root, with the MP4 beside its render manifest.

\`\`\`sh
python -m trisynora.adapters.pointflux \
  --evidence-root /trusted/pointflux-output \
  --render-manifest render/render-manifest.json \
  --judgement judge/temporal-judgement.json \
  --artifact render/final.mp4 \
  --tenant-id organization1 --project-id campaign1 \
  --shot-id intro --project-name "Campaign 1" \
  --intent "Logo reveal" \
  --produced-at 2026-10-11T10:00:00Z \
  --ledger /trusted/trisynora/evidence.sqlite
\`\`\`

The adapter imports one ProjectSpec, ShotSpec, ArtifactRecord and EvaluationRecord, checks actual local artifact/report bytes, checks the shared PointFlux scene SHA-256 and frame/FPS compatibility, and enforces the required acceptance criteria. A repeated identical import is idempotent. JSON Schema validation and SHA-256 checks **do not authenticate** the producer, make the MP4 playable, certify aesthetic quality, authorize model training, or grant release/human approval. \`--produced-at\` is an operator-supplied recording timestamp: keep it identical when replaying the same import. The importer rejects standalone single-frame \`judgement.json\`; only the temporal v1 format is supported in this cut.

Tests (includes negative cases):
\`\`\`sh
python -m unittest discover -s tests -v
\`\`\`
