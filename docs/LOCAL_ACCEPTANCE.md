# Local acceptance and evidence

This repository has **no central runtime**. The three native product repositories must not be cloned into this tree or mutated by TRISYNORA's checks.

## Contract conformance (all five neutral formats)

Install Python 3.12 and a local schema validator, then run:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

The suite checks five schemas and synthetic fixtures; rejects unknown versions, unsafe paths, fake evidence authorization, and implicit binds; and separately probes actual package bytes. Running this suite needs **no** Vera/H3/PointFlux installation or credentials.

## Standalone package-byte verification

Prepare an isolated *copy* of a source artifact outside any native product repository or storage. Write a real `asset.json` whose declared SHA-256 and byte size match the copied artifact; then run:

```powershell
python tools/verify_asset_package.py --root C:\\work\\exchange-package --manifest asset.json
```

Verifier guards: strict schema; reject duplicate/nonfinite JSON; package-relative only; no symlinks; no arbitrary URLs; strict file containment; 1 MiB manifest cap; 10 GiB default media cap; require actual file size and streaming SHA-256 match. This verifier writes **nothing** and grants **no** authorization. Success is only `asset-bytes-verified` — it cannot establish codec authenticity, licensed usage, visual quality, camera transforms, user approval or three-product E2E. Native receivers must use secure staging and prevent malicious concurrent filesystem mutations.

## GitHub Actions status is NOT the test result

The first PR workflow, [run #38071874703](https://github.com/kevin781130-netizen/TRISYNORA/actions/runs/38071874703), reported `failure`; GitHub exposed **no steps**, and the job log endpoint returned `BlobNotFound`. This does not establish a test failure cause and must not be reported as PASS.

Record exactly what runs and where. In a native product E2E phase, compare *source* and *approved Take* SHA before/after; when execution is unavailable, mark the corresponding gate **NOT VERIFIED**.

## Windows PowerShell helper

```powershell
.\\scripts\\test-local.ps1
```

The helper installs no dependency and invokes the existing test suite; run `python -m pip install -r requirements-dev.txt` separately, then rerun.

## Cross-envelope dry-run (P0)

`tools/preflight_exchange.py` performs a **read-only** coherence check across the five neutral envelopes. It detects duplicate identities, unsafe or duplicate manifest paths, missing Asset links from Shot/Job, Evidence pointing at an unknown Job/digest, and Evidence issuer mismatched with the Job's target product.

Example with a receiver-owned, isolated staging directory (file references use `/` even on Windows):

```powershell
python tools/preflight_exchange.py --root C:\work\exchange-package --capability manifests/capability.json --asset manifests/asset.json --shot manifests/shot.json --job manifests/job.json --evidence manifests/evidence.json
```

Add `--verify-bytes` to also read and SHA-256-verify every declared Asset media file. Its output `status=manifest-links-consistent` means **only** that the supplied metadata links are structurally coherent. It always emits `receiverAuthorized=false` and `crossProductE2EVerified=false`. It does not transmit media, call another project, create a fourth runtime, or grant write rights.

The standalone examples under `examples/v1/` are separate **synthetic contract fixtures**, not a coherent production package. The Evidence example uses a deliberately unrelated synthetic digest, so supply truthful connected manifests for a full preflight demonstration.

## Actual execution evidence — 2026-10-11 Asia/Taipei

- **Local conformance: PASS, 36 tests, 0 failures.** Executed `python -m unittest discover -s tests -v` in an isolated Python 3.13.5 + `jsonschema 4.26.0` environment with exact GitHub-byte-matching **5 v1 schemas, 5 v1 examples, existing verifier and all four test modules**, and both new preflight tool/test files.
- Verified Git blob equality of the 10 JSON schemas/examples and the Python modules. For example `tools/preflight_exchange.py` SHA `dbea7a60b54474cf7402d9ee51b3ed4e1bfa83b3` and `tests/test_preflight_exchange.py` SHA `b5623d1244cf38e45e281d9a3f8deebff7642d1c`.
- **Isolation limitation:** The local test snapshot used a 3-line `CONSTITUTION.md` stand-in only for its keyword-presence test (three required literal phrases). Those same three phrases were independently confirmed present in the real GitHub `CONSTITUTION.md` (blob SHA `be0e6dacd340270c4eeb97cfb81d038a16dfb817`). The result is a **verified contract-tool and schema-suite test**, not a byte-identical checkout of the entire repo or an actual product isolation test.
- **GitHub Actions: FAILURE (not CI PASS)** on runs [38071874703](https://github.com/kevin781130-netizen/TRISYNORA/actions/runs/38071874703), [38072578206](https://github.com/kevin781130-netizen/TRISYNORA/actions/runs/38072578206), [38072724951](https://github.com/kevin781130-netizen/TRISYNORA/actions/runs/38072724951), [38073201938](https://github.com/kevin781130-netizen/TRISYNORA/actions/runs/38073201938). GitHub exposed no job step details and log retrieval was not available. **Failure cause unconfirmed**; do not attribute it to source or billing without evidence.
- **NOT VERIFIED:** GitHub-hosted CI success; true H3/PointFlux/Vera standalone regression; native video/codecs, permissions, receiver-owned mutation gates, GPU/browser/ComfyUI execution, real-world media handoff, or full three-product E2E.

Do not merge or release `v0.1.0` until a complete checkout validates locally or CI provides reliable logs, and the owner approves the constitutional boundaries.
