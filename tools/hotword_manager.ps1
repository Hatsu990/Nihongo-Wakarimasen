$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

& ".\.venv\Scripts\python.exe" -m nihongo_wakarimasen --hotword-manager
