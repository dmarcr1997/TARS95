[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$venvPath = Join-Path $repoRoot ".venv-ui-preview"
$requirementsPath = Join-Path $PSScriptRoot "requirements.txt"
$previewPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    throw "Preview requirements were not found at $requirementsPath"
}

$pythonVersion = & $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to run '$Python'. Install Python 3.10 or newer, then retry."
}

$parsedVersion = [version]$pythonVersion
if ($parsedVersion -lt [version]"3.10") {
    throw "UI preview requires Python 3.10 or newer; found $pythonVersion."
}

Write-Host "TARS/95 UI preview setup" -ForegroundColor Cyan
Write-Host "Repository : $repoRoot"
Write-Host "Python     : $pythonVersion"
Write-Host "Environment: $venvPath"

if (-not (Test-Path -LiteralPath $previewPython -PathType Leaf)) {
    Write-Host "Creating isolated preview environment..."
    & $Python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Python could not create the preview environment."
    }
}
else {
    Write-Host "Using the existing preview environment."
}

$importCheck = "import flask, flask_socketio, numpy, PIL, pygame, OpenGL, qrcode"
& $previewPython -c $importCheck *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Preview dependencies are already installed." -ForegroundColor Green
    Write-Host "Python executable: $previewPython"
    exit 0
}

Write-Host "Installing preview-only dependencies..."
& $previewPython -m pip install --disable-pip-version-check --requirement $requirementsPath
if ($LASTEXITCODE -ne 0) {
    throw "Preview dependencies could not be installed."
}

& $previewPython -c "$importCheck; print('Preview imports: OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Preview dependency verification failed."
}

Write-Host ""
Write-Host "UI preview environment is ready." -ForegroundColor Green
Write-Host "Python executable: $previewPython"
