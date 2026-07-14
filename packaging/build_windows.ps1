# Build AICasters-Setup.exe on Windows.
#
# Prerequisites (one time):
#   - Python 3.11+ on PATH
#   - Inno Setup 6 (https://jrsoftware.org/isdl.php), ISCC.exe on PATH
#
# Usage (from the repo root):
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# Output: dist\installer\AICasters-Setup.exe

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)  # repo root

# Read the version from the package so it matches the app.
$version = (python -c "import ai_caster; print(ai_caster.__version__)").Trim()
Write-Host "Building AI Casters $version" -ForegroundColor Cyan

python -m venv .buildenv
& .buildenv\Scripts\python.exe -m pip install --upgrade pip
# Install the app with the production extras plus PyInstaller.
& .buildenv\Scripts\python.exe -m pip install -e ".[ui,capture,vision,ai,voice,obs,hotkeys,diagnostics]" pyinstaller

# Freeze the app.
& .buildenv\Scripts\pyinstaller.exe packaging\ai_caster.spec --noconfirm

# Build the installer.
ISCC.exe /DAppVersion=$version packaging\installer.iss

Write-Host "Done: dist\installer\AICasters-Setup.exe" -ForegroundColor Green
