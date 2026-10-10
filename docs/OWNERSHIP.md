# Ownership and anti-duplication matrix

TRISYNORA never takes ownership away from native products.

| Responsibility | Owner of record | Optional consumers | Prohibited duplication |
| --- | --- | --- | --- |
| General Agent lifecycle, provider routing, repair/checkpoint, final orchestration verification | **Vera** | H3 and PointFlux through scoped tasks | A new global Agent in TRISYNORA |
| H3 AI storyboards, Story Bible, identity continuity, ComfyUI typed workflow, AI generation, approvals / Take versions | **MiniMax-H3** | Vera and PointFlux through approved artifacts | Copying H3's Python graph engine into PointFlux core |
| Scene IR, Motion Board compiler, particles, GPU, Morph, FX/Studio, Remotion hybrid composition, frame judge | **PointFlux** | Vera and H3 through optional CLI/API | Copying PointFlux renderer or director into H3 |
| Neutral artifact/shot/job/capability/evidence envelopes and interoperability fixtures | **TRISYNORA** | All three | Any native editor, queue, storage, secrets store, or renderer |
| GPU residency for its own process | **Each owner** | Shared-resource coordination protocol (future) | Central process that kills other owners' GPU jobs |
| Operator consent to change a native project | **Receiving native product** | Vera may coordinate requests when explicitly enabled | An exchange JSON boolean that grants write access |
| Cross-product audit verdict (optional) | **Vera** | Any actor can view domain evidence | H3/PointFlux unilaterally claiming Vera SUCCESS |

## Repurpose rather than transplant

- H3 `workflow_graph.py` remains H3-owned. PointFlux may call an optional verified ComfyUI adapter; it must not copy the runtime into its core.
- H3 `asset_bible.py` and `continuity_lock.py` remain H3-owned; share a **neutral Asset Bible reference envelope**, not H3 project persistence semantics.
- PointFlux `src/visual/evidence/frameEvidence.mjs` and `src/visual/temporal/judge.mjs` remain PointFlux-owned. H3 requests **read-only QA** via a public command/API.
- Vera `agent_core/fabric/*` and `vera/trust/*` remain Vera-owned. Other products may emit neutral receipts but cannot import Vera internal authority classes as a hard dependency.
- H3 `neural_output.py` remains H3-owned. Other products request optional enhancement outputs, subject to GPU/permission controls, rather than vendoring DLSS/Magpie adapters.
- PointFlux `integrations/remotion` remains PointFlux-owned; H3 may deliver an approved video clip, not import Remotion implementation into H3.

## Ownership handoff rule

Each cross-product interaction is **producer exports → receiver validates → operator/receiver approves → receiver creates derived artifact**. The producer retains control of originals; the receiver retains control of its own imported reference and derived work. There is no shared canonical production database.
