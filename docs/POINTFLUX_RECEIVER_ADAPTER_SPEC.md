# PointFlux receiver — P1 contract and dry-run gate

**Status: prototype only.** The receiver-side CLI is implemented **inside TRISYNORA**, not inside PointFlux. It is an offline *assessment* tool that consumes the H3-origin exchange package created by P1 and **refuses to import it** until the native PointFlux owner supplies its own adapter and approval path.

## Grounded PointFlux capability audit

A read-only inspection of `kevin781130-netizen/PointFlux` **main** found:

- Git tree SHA `0cd03bbfc7900ec06145f63aa311a159cd339641`.
- `integrations/remotion/src/types.ts` blob SHA `61130cd1f4e1a6da7cd2049a82091bc5a3feff76`: `HybridLayer` enumerates PointFlux, text, image, solid, caption, chart, template, svg-morph, and audio, but **no video layer**.
- `integrations/remotion/src/HybridComposition.tsx` blob SHA `5b9ff49bf59c55d591373d94a96332d0a9237481`: no `video` case in `LayerBody`.
- `src/assets/mediaAssets.mjs` blob SHA `c1456ee1c6afeb97613c929e3d424dd64e03691c`: current verified asset loader handles font/image size policies; not a generic video import verification engine.

This audit is **version-scoped**; later PointFlux branches may differ. It is not a claim about every repository branch. A P1 handoff package containing `.mp4` cannot be represented as an editable native video layer in the audited main implementation without PointFlux-owned work.

## Receive flow and authority

```text
H3 owned app    operator-controlled export copy         PointFlux owned app
  (untouched)    source snapshot + video                  (untouched)
                         |
                         v
             TRISYNORA P1 pack + SHA
                         |
                 immutable exchange folder
                         |
                         v
           TRISYNORA receiver dry-run (read-only)
                         |
                  status: blocked
                         |
           future separate PointFlux-owned PR
                         |
           native probe, scoped permission, staged copy,
           video-layer implementation, QA, derived output
```

No shared database, cross-repo imports, direct mutation of a native H3 Take, reimplementation of PointFlux's Studio/Director/Remotion, or global Agent. H3 ↔ PointFlux must work without Vera; Vera orchestration remains optional.

The dry-run validates the existing P1 `ready.json`, `asset.json`, `shot.json`, their SHA-256 receipts, exact copied media bytes, source product `minimax-h3`, one video asset, reference-only mode, explicit bind, and receiver-local pilot bounds:

- Frame rate: exact positive rational, **1–120 fps** (prototype policy, not a claim of native PointFlux support).
- Source duration: **at most 60 seconds** (prototype pilot policy).
- No timebase conversion, clipping, camera transform or frame-rate rounding is executed.
- Target project ID is only a syntactically valid *identifier*; this tool NEVER locates or opens the native target project.
- Source native project snapshot hash is **declared provenance**, not verification of actual native source bytes by the receiver.
- No FFprobe, MP4 codec verification, user rights check, operator permission, model invocation or GPU work. Synthetic media from unit tests is not an actual playable video.

## Windows dry-run

First create an isolated local exchange package using `tools/p1_video_handoff.py pack` as documented in `docs/P1_H3_VIDEO_HANDOFF.md`. Then:

```powershell
python tools/pointflux_receiver_dry_run.py --package C:\\handoff-staging\\take001 --target-project-id PFdemo --target-fps-num 30000 --target-fps-den 1001
```

**Expected status is `blocked`, process exit code `3`.** That is a deliberately safe result, not a crash: metadata and copied bytes may be consistent, but *native PointFlux video import and approval are not available*. For invalid packages, the result is `rejected` with exit code `2`.

The JSON response contains a bounded, sanitized, read-only description of producer, destination identifier, source Shot and Asset digest, timebase, and explicit blocking reasons. No source/destination OS file paths, secret tokens, media bytes or native project data are printed. No file or database is created or changed by this dry-run.

## PointFlux-owned adapter interface — future / not implemented

A **separate** explicit owner-approved PR inside PointFlux may later implement:

1. `inspect_trisynora_package` (read-only validation on a PointFlux-controlled import staging copy).
2. Real codec/frame-count/stream inspection via the PointFlux-approved FFprobe/decoder path and media policy (no arbitrary shell).
3. Versioned capability announcement including compatible video layer, FPS/timebase, dimensions, codecs, duration and data rights (no metadata-as-authorization).
4. Explicit user binding of a new **derived video reference** inside the receiver's native Studio project; no overwrite of existing timeline, imported shot or approved H3 Take.
5. Operator approval for any native write; read-only checks always available with that approval OFF.
6. Optional renderer-side video layer support implemented in PointFlux's own Remotion boundary, never by vendoring H3 or adding a fourth Director.
7. Stale detection after producer digest changes; irreversible writes forbidden; rollback/cleanup scoped to PointFlux-created derived artifacts.
8. Before/after SHA checks of H3 source and native PointFlux project, with OFF-switch regression and real MP4 frame/codec/QA tests.
9. Only then could an independent Vera orchestration adapter be considered, and it cannot claim final PASS from a single product's domain receipt.

## Gate matrix

| Gate | This PR | Future acceptance |
| --- | --- | --- |
| TRISYNORA receiver reference and digest validation | Tested in GitHub Actions | Still verify packaged real media bytes |
| Cross-envelope timebase and link preflight | Tested using synthetic fixtures | Native receiver stream/timebase accuracy |
| H3 originals unchanged in synthetic staging | Tested by file-before/after SHA | Actual H3 Take/project hashes |
| Receiver import and native video layer | **Blocked** by design | Separate PointFlux-owned PR and native approval |
| ComfyUI, Remotion MP4 render, FFmpeg, GPU and visual QA | **Not verified** | Independent real execution |
| Three products standalone with bridge OFF | **Not verified** | Explicit independent native regression runs |

No merging a stacked draft PR before the constitutional Foundation PR has been reviewed and approved.
