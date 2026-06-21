$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

& ".\.venv\Scripts\python.exe" -m PyInstaller `
  --noconfirm `
  --windowed `
  --name "NihongoHotwordManager" `
  --paths ".\src" `
  ".\tools\hotword_manager_entry.py"

Write-Host "Built: $ProjectRoot\dist\NihongoHotwordManager\NihongoHotwordManager.exe"
