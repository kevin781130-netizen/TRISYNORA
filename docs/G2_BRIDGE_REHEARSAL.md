# G2 — Full bridge rehearsal with 3 synthetic product roots

**Highest constitution:** Vera, MiniMax-H3 and PointFlux must never be modified, installed as mandatory dependencies, run as a combined application or share mutable state. This tool uses **three disposable mock Git repositories**, NOT any of the owner's actual product sources.

## Purpose

P0 and P1 independently validate exchange envelopes, a read-only H3-origin video handoff, a PointFlux receiver proposal, real H.264 stream decoding, and Git-indexed/explicitly watched SHA-256 comparison. G2 combines those existing real pieces in one **offline rehearsal**:

```text
temporary mock H3 ── (synthetic approved-take fixture, mocked native snapshot)
        │
        └── independent operator-export COPY of a generated real MP4
                     │
                     ▼
           TRISYNORA pack → ready.json
                     │        immutable Asset + Shot references
                     ▼
             receiver assess (always blocked)
                     │
                     ▼
             ffprobe + ffmpeg full decode to null
                     │
                     ▼
       G1 verify ALL THREE synthetic Git repos against pre-run SHA
                     │
                     ▼
          rehearsal-pass, native E2E = false
```

All files are created inside one fresh `tempfile.TemporaryDirectory`, cleaned up at completion. The command does not accept real source repo paths and never calls native product commands. It creates and commits **only synthetic fixtures**.

## Execute (Windows / Linux / macOS)

Python, Git, `ffmpeg`, `ffprobe`, and `jsonschema` must be available.

```powershell
python -m pip install -r requirements-dev.txt
python tools/bridge_rehearsal.py
```

On test success, the JSON output contains:

- `status=synthetic-bridge-rehearsal-pass`
- `sourceType=temporary-synthetic-git-products-only`
- `media.fullFFmpegDecodeVerified=true`
- `isolation.unchangedWithinScope=true`
- `pointfluxNativeVideoImported=false`
- `receiverAuthorizationGranted=false`
- `nativeProductsActuallyRun=false`
- `realThreeProjectE2EVerified=false`

Process exit codes: `0` synthetic rehearsal PASS; `2` validation rejected (including changed native fixture); `4` required Git/FFmpeg tooling unavailable → NOT VERIFIED.

The real generated fixture is a **1-second, 128×72, 30 fps H.264 MP4**. It is a technical codec sample, **not** output from the real MiniMax-H3 Director or a rendered PointFlux timeline.

## G2 negative-proof matrix

The dedicated `tests/test_bridge_rehearsal.py` exercises:

1. A complete decoded reference-only handoff with a three-source SHA clean outcome.
2. H3 approved Take mutation blocking release.
3. PointFlux native project mutation blocking release.
4. Vera Git-indexed source mutation blocking release.
5. Operator export media mutation blocking release.
6. Staged media and digest-locked Shot manifest tampering fail closed.
7. Tampered baseline JSON rejected against the separately pinned digest.
8. Unavailable FFmpeg, FFprobe, or Git marked NOT VERIFIED.
9. CLI emits sanitized JSON with no product access, credentials, native paths or false `imported=true` status.

A full-codebase test suite plus a **separate CI command** `python tools/bridge_rehearsal.py` are both required. G2 may only be marked PASS if the actual GitHub Actions job and standalone rehearsal command finish successfully, and the *real MP4 decoder* test was not skipped.

## What G2 DOES NOT prove

This is NOT a live three-product E2E and must not be marketed as one. It does **not** verify:

- Real H3 execution, user-approved AI Takes or real H3 output.
- A PointFlux native video layer, receiver write approval, compositing, native import, WebGPU, color pipeline, multi-track rendering, visual quality.
- Vera orchestration, permission policy, retry/checkpoint or final independent verification.
- Real native repositories remain unchanged during a live integration operation.
- Untracked files not on G1's explicit watchlist, processes, GPU memory, databases or remote state.

G2 is an **integration rehearsal of TRISYNORA-owned tools** with disposable samples. Next needed: separately authorized, product-owned PointFlux Video Layer/Adapter implementation, real media acceptance and independent product regression, with the bridge OFF and ON.

## PRs and approval

This is a stacked **Draft PR #6** on top of PR #5, which is based on #4 → #3 → #2 → #1. No changes to the actual three source projects and **no automatic merges**. Human owner review of `CONSTITUTION.md` remains mandatory.
