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
