# TRISYNORA Execution Roadmap (Proposal, not completion claims)

## P0 — Contract foundation (this PR)

- [x] Constitutional zero-contamination policy and explicit ownership matrix drafted.
- [x] Read-only contract-first architecture and native format compatibility notes drafted.
- [x] Five neutral v1 schemas and positive/negative conformance examples added.
- [x] Offline boundary tests and opt-in CI workflow added.
- [ ] Review/merge this TRISYNORA-only PR.
- [ ] Record an actual local conformance test PASS; workflow file existence is not CI evidence.
- [ ] Agree on version v0.1.0 after review; do not auto-publish.

## P1 — Optional first real bridge: H3 ↔ PointFlux

- [ ] Choose exact source branch/revisions and freeze H3/PointFlux native interfaces.
- [ ] Add product-owned adapters via separate approved PRs **inside their own repos only**.
- [ ] H3 exports approved immutable video + manifest into package; PointFlux verifies hash and imports a copy.
- [ ] PointFlux supports independently timed Video Layer / media routing in its own hybrid composition (if missing at actual target HEAD).
- [ ] Preserve source H3 Take/Prompt/Camera/Project hashes and test stale re-import.
- [ ] Test all three products' standalone/offline paths; record before/after checksums.

## P2 — Optional Vera orchestration

- [ ] Reuse Vera's existing Fabric/PointFlux Motion Director contracts; avoid fourth Agent.
- [ ] Discover H3/PointFlux capabilities, show disabled/unverified routes honestly.
- [ ] Apply per-product consent, bounded retries, checkpoint/resume, independent evidence.
- [ ] Verify orchestration OFF keeps H3↔PointFlux direct path working.

## P3 — Optional advanced modules

- [ ] Asset Bible neutral references without importing H3's production state.
- [ ] PointFlux read-only visual QA invoked by H3, never H3 Take mutation.
- [ ] Optional ComfyUI workflow/media factory API; no Python implementation copied into PointFlux.
- [ ] Scoped GPU ownership/lease cooperation; no universal process kill.
- [ ] Optional audio TTS/music, subtitles, advanced media/timebase interchange, optional OTIO.
- [ ] One-prompt 60-second AI/video/motion/TTS/MP4 path with real entire-cut quality evidence.

## Rejection criteria (any phase)

Reject any work that requires a mandatory cross-repo install; shares mutable native state; grants authority through a manifest; bundles the other product's core source; introduces a global director/broker; mutates original approved media; or reports unexecuted GPU/browser/video tests as passed.

## PR template acceptance questions

Every interoperability PR must answer:

1. Which repository and native owner are affected?
2. Which new public schema/operation/version is used?
3. What code, private state, and credentials are **never** accessed?
4. What is the precise receiving-product approval gate?
5. How are source revision/hash, stale state, and derived artifacts tracked?
6. What happens when the adapter or another product is missing?
7. Which tests were actually executed, and what is NOT VERIFIED?
