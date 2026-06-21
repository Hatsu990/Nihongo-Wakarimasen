$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

py -3.10 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-gpu.txt
& ".\.venv\Scripts\python.exe" -m pip install -e .

Write-Host ""
Write-Host "Setup complete."
Write-Host "Next:"
Write-Host "  1. .\.venv\Scripts\python.exe -m nihongo_wakarimasen --hotword-manager"
Write-Host "  2. .\tools\preload_local_model.ps1"
Write-Host "  3. .\tools\overlay_control.ps1 start"
