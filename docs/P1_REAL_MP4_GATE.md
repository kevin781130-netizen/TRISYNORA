# P1 Video Media Gate — real MP4 verification, no native import

**Constitutional priority:** Vera, MiniMax-H3 and PointFlux remain completely independent. This tool exists only in TRISYNORA. It does **not** implement any native adapter, VideoLayer, Director, AI generation, write authorization or PointFlux scene mutation.

## Problem solved

P1 package and receiver contract tests proved metadata and copied bytes were consistent, but the video samples were deliberately fake MP4 bytes. Byte hashes do not prove that media is playable or that actual stream FPS and frame count match the declared Shot.

This branch introduces a **separate optional media gate** that reads **only an isolated TRISYNORA exchange package**, operates on a pre-validated H3 package, and performs:

1. Strict P1 package/receiver preflight: source origin, SHA-256, receipt, reference-only handoff and one video asset.
2. `ffprobe`: actual container format, single H.264 stream (no additional audio/subtitle/video streams), yuv420p format, 64–1920 × 64–1080 dimensions, counted frames, exact rational average FPS, exact declared frame count.
3. `ffmpeg`: decode full video stream to `-f null -` without writing a video file, with shell execution **disabled**, file-only protocol, bounded timeout, capped source size (128 MiB), and capped duration through receiver pilot validation (60 s).
4. Re-hash media after decoding to detect changes during validation.
5. Return a data-only verdict, **always `status=blocked` even if all media tests pass**: PointFlux native video layer, native project import, user approval, and full render are still not implemented.

## Operator CLI (Windows)

First create an isolated H3 video exchange package as documented in `docs/P1_H3_VIDEO_HANDOFF.md`. Install **ffprobe and ffmpeg** on the operator host and ensure both are available through `PATH`.

```powershell
python tools/pointflux_media_probe.py --package C:\handoff-staging\take001 --target-project-id PFdemo
```

Exit codes:

| Code | Meaning |
| --- | --- |
| `3` | Package + true MP4 stream/decoded frame checks passed; PointFlux native import remains **blocked** |
| `2` | Contract/media mismatch, corrupted stream or disallowed codec, reject |
| `4` | Media tool missing or timed out: **NOT VERIFIED**, never PASS |

Expected output on success **as a media gate only** includes `ffprobeStreamMetadataChecked=true`, `fullVideoDecodeSucceeded=true`, `receiverAuthorized=false`, `pointfluxImported=false`, and `crossProductE2EVerified=false`. The command does not contact or edit either H3 or PointFlux.

### Codec policy for this pilot

Accepts H.264, MP4 container, yuv420p, **exactly one video stream and no others**, source ≤128 MiB, dimensions 64–1920 by 64–1080, declared source 1–120 fps, max 60-second Shot. Audio, HEVC, AV1, variable-FPS, 4K and other legitimate media may be supported later through explicit separate versioned capability negotiations; no automatic widening of this narrow pilot.

For example, a video with container metadata reporting 29 frames while a Shot declares 30 is **rejected**, not silently stretched, rounded or re-encoded. Source media is only inspected in the independent exchange directory. The final PointFlux adapter would need an independently approved Video Layer, decoder, controlled workspace import, receipt, and reversible native state change, all in PointFlux-owned code.

## Tests and evidence

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The suite contains negative/positive unit cases for the probe parser, fake binary output, damaged media, absent binaries, and **one real H.264 MP4 integration test**. The real test uses `ffmpeg` to **generate a temporary 1-second 128×72 / 30 fps H.264 sample outside all native projects**, packages it in a synthetic H3 export staging folder, validates actual stream metadata, and decodes it with the real `ffmpeg` executable; no synthetic fake is counted as a playable-media PASS.

When FFmpeg or FFprobe is missing, the integration test marks itself **SKIPPED**. In that case a passing unit-test suite **must not** be described as a successful real video decode. Inspect the actual GitHub Actions run output and assert the real case did not skip. No shell command is accepted from a manifest, and no executable is bundled in the repository.

## GitHub / branch dependency

This is a **stacked Draft PR** based on `feat/p1-pointflux-receiver-contract` (PR #3), which depends on PR #2, which depends on the constitution PR #1. Each PR is independently reviewable, with no automatic merging or writing into Vera, H3 or PointFlux.

**Limitations:** This gate does not authenticate actual H3 export ownership, license rights, source project authenticity, audio, real PointFlux compatibility, native import, or visual quality. It also assumes a trusted isolated local filesystem; malicious concurrent filesystem changes require a stronger receiver-owned secure staging system.
