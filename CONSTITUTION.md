# TRISYNORA 最高憲法 — Zero Cross-Project Contamination

**Constitutional priority:** This document is the highest binding project policy. Architecture, implementation, adapters, prompts, agents, documentation, and schedule must conform. If a request conflicts with this constitution, the integration must stop and ask for an explicit constitutional change; it must never silently bypass a rule.

## Article 1 — Absolute product autonomy

Vera, MiniMax-H3, and PointFlux are three **independent products**. Each MUST install, start, operate its own core features, persist its own projects, test, and release without TRISYNORA or either of the other products installed, online, or authenticated. An integration failure MUST degrade only the optional integration feature.

## Article 2 — Single-owner source, state, and truth

Each product alone owns its native code, internal APIs, models, workflows, scene/shot/take state, asset store, user data, settings, and native project format. Other products and TRISYNORA MUST NOT mutate those stores directly. No shared mutable database, writable directory, filesystem symlink, common runtime lockfile, or in-process private module import may be a condition of interoperability.

## Article 3 — Contracts, not transplanting engines

TRISYNORA owns **neutral interchange contracts and conformance fixtures**, never the implementation of an Agent, Director, ComfyUI runtime, GPU renderer, media compositor, or video generator. Product-specific adapters stay inside their respective owner repository (or an independently distributed optional package with an explicit maintained owner). No copy-paste, vendoring, git submodule, or repository-wide merge of an entire product to implement an integration. Where code reuse is justified, use a separately versioned, minimal utility or a documented CLI/API.

## Article 4 — Explicit, narrow, revocable consent

Cross-product operations default to **disabled and read-only**. Importing reference metadata never authorizes rendering, deleting, rewriting a prompt/take, replacing a project, or changing another product's settings. Every operation that creates or changes data must be approved under the *receiving product's* own authority policy and constrained to that product's approved workspace. A field `approved: true` in untrusted JSON is never an authorization token.

## Article 5 — Non-destructive exchange

Exchange source artifacts are immutable, content-addressed (SHA-256), versioned, and attributable to one originating product/project/revision. Consumers receive a copy or a read-only reference and create **new derived outputs under their own ownership**. No exchange overwrites existing native shots, prompts, approved AI takes, motion scenes, timelines, or published outputs. A changed source digest invalidates previous bindings (stale/needs-review), never silently updates them.

## Article 6 — Zero trust at every boundary

Treat any manifest, file, URI, media stream, prompt, tool output, model response, and job result received from another product as untrusted. Validate exact schema, version, digest, media type, size, path containment, capability, and receiver-side authorization *before* any action. Reject path traversal, arbitrary URLs, local drive paths from external manifests, shell execution, undeclared scripts/models, and unresolved coordinate/timebase conversions. Fail closed; preserve native state.

## Article 7 — No cross-product control-plane duplication

Vera is authoritative for cross-product orchestration, retry policy, checkpointing, operator approval, and final *cross-product* verification **only when the user explicitly enables Vera orchestration**. H3 retains its own Director and local ComfyUI workflow controller; PointFlux retains its own Studio, FX Director, and renderer. Neither subordinate runtime may silently become another product's global Agent or overwrite Vera's final verdict. H3 ↔ PointFlux direct exchange remains possible without Vera.

## Article 8 — Resource and privacy isolation

Each product keeps its own secrets, API keys, credentials, logs, model weights, user media, and runtime configuration. TRISYNORA MUST NOT collect or redistribute them. Adapters request scoped access at run time, prefer localhost and least-privilege credentials, redact logs, enforce bounded CPU/GPU budgets, and use explicit GPU handoff or serialization when sharing hardware. No adapter may forcibly terminate another product's work or assume exclusive hardware ownership.

## Article 9 — Verifiable independent success

Domain-specific PASS (e.g. one PointFlux visual judge or H3 completed queue) is **evidence only**, not proof of full end-to-end delivery. A combined PASS requires independently executed tests, persisted hashes, explicit product revisions, full artifact validation, operator review when required, and no outstanding blocker. Missing runtime, skipped test, unavailable GPU/model/browser, or blocked CI MUST be recorded as NOT VERIFIED, not PASS.

## Article 10 — Compatibility and opt-in upgrades

Every public contract is versioned. Breaking changes require a new major schema, published migration/compatibility matrix, and adapter opt-in. Pinned previous versions stay supported according to documented policy. No consumer is forced to synchronize product release cycles. Unknown versions MUST be rejected explicitly rather than guessed or transformed.

## Article 11 — Repo write firewall

**No TRISYNORA task, workflow, token, Agent, test, or PR may directly modify Vera, MiniMax-H3, or PointFlux by default.** Product changes require (1) an explicit, separate request naming the target repository, (2) a target-owned branch/PR, (3) independent review and tests, and (4) that repository's own approval to merge. In the foundation phase, TRISYNORA automation MUST have no write credentials to any of the three source repositories.

## Article 12 — Reversibility, auditability, and change control

Integration must support a complete OFF switch and removal without breaking native functionality or corrupting native data. Every derived artifact records its provenance. Any constitutional amendment requires a dedicated PR explicitly labelled `constitutional-change`, an impact assessment against all three products, proof of isolation, and **human owner review** before merge. Normal feature PRs cannot weaken this constitution by implication.

## Mandatory acceptance gates

An integration cannot be declared complete unless all gates pass:

- **G0 Standalone:** all three products' native operations remain independent of other products and TRISYNORA.
- **G1 Read-only source:** producer's code, native projects, approved takes, and output hashes are unchanged after exchange.
- **G2 Off switch:** disabled/missing/unhealthy adapters leave native user workflows functional.
- **G3 Isolation:** no common mutable DB, no foreign private implementation import, no unapproved external writes, no shared secrets.
- **G4 Contract:** version, media provenance, digest, paths, frame-rate/timebase, limits, and declared capabilities validate.
- **G5 Approval:** explicit receiver-owned permission gate for each mutation; no metadata-as-authority shortcut.
- **G6 Recovery:** failed/partial runs are bounded, idempotent where specified, reversible where possible, and never silently re-submit expensive GPU jobs.
- **G7 Evidence:** actual local runtime outputs and tests are recorded; missing evidence is stated honestly.
- **G8 Non-duplication:** no fourth Director/Agent/GPU engine and no replacement of the product's own native workflow.

**Constitutional invariant: Independent-by-default, interoperable-by-consent, immutable-at-the-boundary.**
