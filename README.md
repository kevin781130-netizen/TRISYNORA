# TRISYNORA

**Three independent products. One optional creative interoperability language.**

TRISYNORA is the **contract-first interoperability specification** for three independently owned applications:

- [Vera](https://github.com/kevin781130-netizen/vera): AI agent orchestration, model/tool routing, checkpoints, permission boundaries, and independent verification.
- [MiniMax-H3](https://github.com/kevin781130-netizen/minimax-H3): AI film direction, storyboards, ComfyUI workflows, video takes, continuity, and selective regeneration.
- [PointFlux](https://github.com/kevin781130-netizen/PointFlux): motion graphics, particles, GPU rendering, morph, FX Studio, compositing, and audiovisual output.

> **最高憲法：三個專案絕對不互相污染。**
>
> All three products **MUST remain independently installable, runnable, editable, testable, and releasable**. Integration is opt-in, versioned, and replaceable. TRISYNORA is neither a fourth product runtime nor a master director nor a shared database.

## Authority order

1. **[CONSTITUTION.md](CONSTITUTION.md)** — mandatory non-contamination rules; overrides every roadmap or implementation proposal.
2. [docs/OWNERSHIP.md](docs/OWNERSHIP.md) — owner-of-record and prohibited duplication.
3. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — optional adapters and trust boundaries.
4. [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) — supported formats, compatibility gates, and existing bridges.
5. [docs/ROADMAP.md](docs/ROADMAP.md) — planned delivery sequence, not a declaration of completed functionality.
6. [docs/ADR-0001-contract-first.md](docs/ADR-0001-contract-first.md) — architectural decision record.

## Implemented contract and isolated tooling stages

TRISYNORA contains neutral exchange contracts, fixtures, **optional local command-line tools**, Git-based isolation checks, and a CI-tested synthetic video exchange rehearsal. It is **not** a fourth Agent, Director, native video editor or shared product runtime. It never installs or starts the three native products as part of its tests.

- **P0**: five versioned strict neutral JSON envelopes; synthetic conformance tests.
- **P1**: local H3-origin video *copy* and SHA-256 exchange package; PointFlux read-only, fail-closed receiver assessment.
- **Media gate**: optional FFprobe + FFmpeg verification and decode-to-null of real H.264 pilot MP4; success still **blocks** PointFlux native import.
- **G1**: opt-in read-only Git HEAD/SHA-256 audit of indexed and explicitly watched native files. Not a universal untracked-state proof.
- **G2**: complete H.264 exchange/decode/isolation rehearsal against **three disposable mock Git projects**, not real Vera/H3/PointFlux.
- **G3/G4**: frozen historic CI/PR evidence, strict Git file-diff scope, and a manual-only merge-readiness checklist.

The five new contract families are envelopes, **not replacements** for the products' native formats:

| Neutral envelope | Purpose |
| --- | --- |
| `schemas/v1/capability.schema.json` | Discover supported optional capabilities |
| `schemas/v1/asset.schema.json` | Exchange immutable asset references + digest |
| `schemas/v1/shot.schema.json` | Reference shots without overwriting native scenes/takes |
| `schemas/v1/job.schema.json` | Describe constrained cross-product requests; grants no authority |
| `schemas/v1/evidence.schema.json` | Carry domain-only results and inspectable evidence |

## Getting started

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The repository is public and its **read-only** GitHub Actions workflow has recorded successful offline contract and real MP4 tests. CI results only cover the exact tested commit; `green` does not mean native product import, production readiness, or owner-approved merge. GitHub Actions runs on each PR; tests can also run locally without any other product installed.

The media rehearsal requires `ffmpeg` and `ffprobe` on PATH. A missing decoder is **NOT VERIFIED**, never a video PASS.

### Optional read-only preflight

`tools/preflight_exchange.py` checks links between validated Asset, Shot, Job and Evidence manifests, and can optionally SHA-256-verify media bytes. It never submits jobs, opens another product's private data, or grants receiver authorization. Read [local acceptance and the preflight CLI examples](docs/LOCAL_ACCEPTANCE.md).

## Current acceptance and merge guidance

- [P1 packaging](docs/P1_H3_VIDEO_HANDOFF.md) · [Receiver preflight](docs/POINTFLUX_RECEIVER_ADAPTER_SPEC.md) · [Real MP4 media gate](docs/P1_REAL_MP4_GATE.md)
- [G1 scoped SHA-256 audit](docs/G1_ISOLATION_AUDIT.md) · [G2 synthetic bridge rehearsal](docs/G2_BRIDGE_REHEARSAL.md)
- [G3 freeze and product-release blockers](docs/G3_RELEASE_REVIEW.md) · [G4 seven-PR merge readiness review](docs/G4_MERGE_READINESS.md)

Offline acceptance commands (Git history required for G3/G4; install FFmpeg for video tests):

```bash
python -m unittest discover -s tests -v
python tools/bridge_rehearsal.py
python tools/g3_release_gate.py
python tools/g4_merge_review.py
```

**Non-goals:** No shared database; no native code vendoring or submodules; no cross-repository writes; no always-running broker or fourth Director; no automatic merges or PR retargets.

**Status:** contracts, real MP4 *synthetic-fixture* decoding, mock-three-product G2 rehearsal and pre-merge review are implemented and tested. **Native H3 export, PointFlux video import, Vera live orchestration and genuine three-product E2E are NOT VERIFIED.** The stacked PRs remain drafts pending human owner review. This Public repository has **no owner-approved distribution license yet**; do not presume MIT reuse or a production release.
