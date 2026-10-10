# P1 — H3 → PointFlux video handoff prototype

**Scope:** an independently executable TRISYNORA local copy/inspect prototype. This is **not a native H3 exporter or PointFlux importer**; neither product is installed, invoked, modified, or given write access.

## Constitutional guarantees

- Only the explicitly named source video and project snapshot are read from a caller-supplied source folder.
- A **fresh, exclusive output package** is created outside both the source tree and TRISYNORA. Existing destinations are never overwritten.
- SHA-256 digests of the video and native snapshot are checked before/after packaging. Only the explicitly selected video bytes are copied; the native snapshot is not copied.
- Output Asset and Shot envelopes are both **reference-only**. Receiver authorization is false and an explicit native bind/approval remains mandatory.
- No database, director, ComfyUI process, network, remote file write, GPU, PointFlux renderer, or cross-product Agent is started.
- Inspection validates immutable package references, readiness marker, manifest SHA-256 and copied media bytes.

## Operator-controlled source and destination

Prepare:

    C:\h3-export\render\take.mp4
    C:\h3-export\project\snapshot.json
    C:\handoff-staging\

The source may be an independently exported copy of H3 artifacts. Do not place the destination inside any native project. Use a trusted local filesystem directory for staging.

From TRISYNORA checkout on Windows:

    python tools/p1_video_handoff.py pack --source-root C:\h3-export --video render/take.mp4 --native-file project/snapshot.json --out C:\handoff-staging\take001 --project-id H3demo --revision export-r1 --shot-id H3Shot001 --artifact-id asset_H3demo_001 --native-format minimax-h3/export-snapshot --fps-num 30000 --fps-den 1001 --frames 1800

Independent receiver-style validation:

    python tools/p1_video_handoff.py inspect --root C:\handoff-staging\take001

Outputs:

    take001/
      .ready.json
      assets/asset_H3demo_001.mp4
      manifests/asset.json
      manifests/shot.json

The package is not an H3-native or PointFlux-native editable project. The original PointFlux shot-exchange/v1 remains unchanged. This format is an optional new neutral envelope; it does not redefine or replace native video or Scene IR semantics.

## Tests and limits

Run after installing local Python dependencies:

    python -m pip install -r requirements-dev.txt
    python -m unittest discover -s tests -v

P1 tests use **synthetic non-video bytes** to verify reference packaging and tamper resistance. A passing test does NOT prove a valid MP4 codec, stream metadata, frame count, native project schema, identity provenance, operator approval, intellectual-property clearance, receiver import, camera conversion, or full video E2E.

There is no signed/authenticated publisher. This runs only in an **operator-controlled local filesystem** and is not designed for hostile concurrent filesystem mutation. The media format and fps/frame values are declarative until separately verified by the product-owned receiver using ffprobe or an equivalent.

The Phase 1 plan after this prototype passes is to add a separately approved **PointFlux-owned import adapter** that validates this package, checks media streams and asks native PointFlux approval before adding a derived video layer. H3 adapter changes are an independent later PR requiring separate owner authorization.

## PR dependency

This branch is intentionally based on draft Foundation PR #1 (docs/constitution-v1). Human review must approve Foundation before merging P1 to main. A passing TRISYNORA-only test may never authorize modifying Vera, H3, or PointFlux.
