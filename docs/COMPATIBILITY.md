# Compatibility and current verified boundaries

## Existing factual interfaces (not TRISYNORA contracts)

| Owner | Existing source or branch | Current nature | Important limitation |
| --- | --- | --- | --- |
| PointFlux | `schemas/shot-exchange-v1.schema.json` on `feature/p1-g1-studio-browser-proof` (also earlier dual director exchange branch) | `pointflux-h3-shot-exchange/v1`, read-only scene/camera/timeline metadata | Not a media exchange or render authority |
| MiniMax-H3 | `feature/p0-pointflux-e2e-gate` | FastAPI import/get/explicit bind + stale review protection | Real cross-repo browser/GPU E2E PASS not established |
| Vera | `feat/pointflux-motion-director` | `vera motion` CLI/JSON bounded Motion Board compile/smoke/checkpoints/evidence | PointFlux domain result alone is not Vera final verification |
| MiniMax-H3 | `feat/production-ir-core-hardening`, `release/6.7.2-rc-hardware-acceptance` | Proposed/implemented work on story, continuity, assembly, release gates in separate branches | Not automatically available together on `main` |

Do **not** copy experimental branch APIs into TRISYNORA and claim they are stable. Inspect product source SHA and the exact installed version before an adapter declares a capability ready.

## Contract versioning

- New neutral envelopes use `trisynora.<family>/v1`.
- Native namespaced formats remain unchanged: existing PointFlux `pointflux-h3-shot-exchange/v1` is **not** redefined here.
- Adapters announce both `interop schema version` and `native format version` where relevant.
- No silent conversion of framerate, timebase, coordinate system, color space, clip duration, rights, or embedded media.
- Minor extensions may add optional fields only when all v1 readers explicitly tolerate them; current strict schemas instead require an explicit version bump for structural changes.
- Unknown required fields or unknown versions fail closed.

## Release decision matrix

| Scenario | Expected behavior |
| --- | --- |
| Vera absent, H3↔PointFlux reference exchange enabled | Allowed with explicit receiver approval |
| H3 absent, PointFlux standalone | Must operate normally |
| PointFlux absent, H3 standalone | Must operate normally |
| Both absent, Vera standalone | Must operate normally |
| Adapter disabled/unavailable/outdated | Feature unavailable, native product unaffected |
| Source SHA changed | Mark receiver reference stale, human review required |
| Insufficient local model/GPU/FFmpeg/browser | No PASS claim; report blocked/unverified |
| GitHub Actions quota exhausted | No CI PASS claim; use recorded local command/results |
| JSON says `approved=true` but no native approval | Deny mutation |

## Promotion gates

Before declaring `trisynora v1` production-ready: run schema conformance locally; demonstrate all three products standalone; validate reference-only H3 ↔ PointFlux with unchanged native hashes; pass a real single-media exchange; independently validate a full video artifact; record all versions, logs, and operator approval; prove bridge OFF still works. No such full three-project PASS is claimed in this foundation repository.
