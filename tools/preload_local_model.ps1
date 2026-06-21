$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

& ".\.venv\Scripts\python.exe" ".\tools\preload_local_model.py"
