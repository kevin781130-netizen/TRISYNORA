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

## Phase 0 scope

This repository contains **only documentation, neutral versioned exchange contracts, examples, and offline conformance tests**. It does **not** install or start Vera, MiniMax-H3, PointFlux, ComfyUI, browsers, GPU models, FFmpeg, or cloud providers.

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

The tests are designed to work locally even when GitHub Actions cannot run. CI is advisory until a **real, recorded PASS** exists; an unexecuted workflow is not proof.

### Optional read-only preflight

`tools/preflight_exchange.py` checks links between validated Asset, Shot, Job and Evidence manifests, and can optionally SHA-256-verify media bytes. It never submits jobs, opens another product's private data, or grants receiver authorization. Read [local acceptance and the preflight CLI examples](docs/LOCAL_ACCEPTANCE.md).

## Non-goals (deliberate)

No shared database; no git submodules or vendored product engines; no implicit cross-repository imports; no always-running central broker; no fourth director UI; no automatic merges or writes to source projects; no unverified claims of three-project E2E video production.

**Status:** planning and contract foundation. No native product integration or production-grade cross-repository E2E is claimed by this repository.
