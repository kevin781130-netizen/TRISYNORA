# H3 real-Take source preflight — isolated P1 gate (2026-11-01)

This is a **read-only preflight on an operator-exported COPY** of the H3 project snapshot and MP4. It does not authenticate native H3, decode MP4, call ComfyUI, change PointFlux or authorize a receiver. It is deliberately not a second Director or runtime.

## First real-machine step (once H3 has produced a Take)

Copy an approved H3 project snapshot and its matching MP4 to a separate trusted directory:
- `C:\\h3-export\\project\\snapshot.json`
- `C:\\h3-export\\render\\take.mp4`

Then run from this isolated TRISYNORA branch:

```powershell
py -3 tools/h3_take_source_gate.py --source-root C:\\h3-export --project-file project/snapshot.json --video render/take.mp4 --project-id project1 --take-id take1
```

Return code 0 is **ready_for_native_media_probe** ONLY. It proves the exported JSON's Take receipt, run record, completed render history, filename and recorded SHA256 agree with the actual selected file bytes. It does **not** independently prove the export was made by a trusted running H3 process; the snapshot is operator supplied.

Failure (exit 2) is fail-closed. No output files or mutations. Before real use ensure that the H3 branch actually persists these fields on the same Take record; never synthesize missing receipts to force PASS.

## Offline regression

```powershell
py -3 -m unittest tests.test_h3_take_source_gate -v
```

The test fixture uses bytes that are **NOT a playable MP4**. After this check, run TRISYNORA's existing `tools/pointflux_media_probe.py` with a real packaged MP4, requiring FFprobe/FFmpeg actual decode. Native H3 export and PointFlux Video Layer/import remain independent later gates.

No GitHub Actions, no cross-repository writes, no main modifications, no user GPU spend.
