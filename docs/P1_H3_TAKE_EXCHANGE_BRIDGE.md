# H3 Take → TRISYNORA P1 staging bridge (2026-11-01)

## Status and limits
This is an **operator-controlled bridge for exported copies**. It is NOT a native H3 exporter or PointFlux importer. It does not start ComfyUI, perform AI inference, write into H3/PointFlux, approve a Take, or grant receiver authority.

The script combines three existing independent gates:
1. `h3_take_source_gate.check`: unique Take, matching prompt/run/completed-history receipt, output filename and actual source media SHA-256.
2. Real `ffprobe`: derive codec, rational FPS and counted frames **from media**, not user declarations; verify sources have not changed.
3. Existing P1 `pack` + `pointflux_media_probe.verify_playable`: isolated reference-only copy, byte-check, real FFprobe/FFmpeg full decode, always blocked from PointFlux native import.

Required source snapshot fields are those currently checked in `tools/h3_take_source_gate.py`. A missing `source_media_sha256`, completed history or Take receipt is **BLOCKED**, not manufactured from the MP4.

## Run on a machine with FFmpeg, FFprobe and Python dependencies

With an operator-exported **copy**, in separate staging locations:

- `C:\h3-export\project\snapshot.json`
- `C:\h3-export\render\take.mp4`

Run from an isolated TRISYNORA checkout of this branch:

```powershell
py -3 -m pip install -r requirements-dev.txt
py -3 tools/h3_take_exchange_bridge.py --source-root C:\h3-export --project-file project/snapshot.json --video render/take.mp4 --project-id p1 --take-id take1 --target-project-id PFdemo --out C:\handoff-staging\take1-new
```

The destination must be a **new** directory outside the H3 source and TRISYNORA source. Source files remain untouched. This is an example: replace project/take IDs with the real exported IDs.

Exit status:
- **3** = Take/source bytes/real MP4 decode gate passed; PointFlux import intentionally **BLOCKED**. Output `staged_verified_receiver_blocked`.
- **2** = Fail closed on missing or inconsistent Take, unsafe paths, MP4 mismatch, or violated receiver contract.
- **4** = FFmpeg/FFprobe missing or timed out: **NOT VERIFIED**.

Pilot media constraints inherited from the existing P1 probe: single H.264/yuv420p video stream, no audio stream, <=128 MiB, <=60 seconds, dimensions within the receiver pilot range. The operator-supplied snapshot does not cryptographically prove it was created by a real H3 process. A generated test video is not H3 inference.

On post-pack verification failure, the **new, reference-only** package may remain for diagnosis. Its existence must never be interpreted as acceptance.

## Tests

```powershell
py -3 -m unittest tests.test_h3_take_source_gate tests.test_h3_take_exchange_bridge -v
```

Local isolated developer test (Python 3.13.5, real FFmpeg/FFprobe) resulted in **14/14** (8 source checks + 6 bridge checks). The bridge unit tests mock the P1 packer and receiver; they do not prove full-repository regression or a real H3-to-PointFlux product integration. Full checkout and native-machine qualification remain **NOT_RUN**.

No GitHub Actions, no changes to main, no cross-repository writes, no GPU/paid model charges.
