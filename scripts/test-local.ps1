$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
& python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "TRISYNORA local conformance FAILED (exit $LASTEXITCODE)" }
Write-Host "TRISYNORA local tests passed; native product and GPU E2E remain NOT VERIFIED."
