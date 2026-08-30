[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$previewPython = Join-Path $repoRoot ".venv-ui-preview\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $previewPython -PathType Leaf)) {
    throw "UI preview environment not found. Run .\tools\ui-preview\setup.ps1 first."
}

Push-Location $repoRoot
try {
    & $previewPython -m unittest discover -s tests -p "test_ui_preview.py" -v
    if ($LASTEXITCODE -ne 0) {
        throw "UI preview smoke suite failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

Write-Host "UI preview smoke suite: PASS" -ForegroundColor Green
