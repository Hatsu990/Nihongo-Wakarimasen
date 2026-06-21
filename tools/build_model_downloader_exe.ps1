$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistRoot = Join-Path $ProjectRoot "dist\Download Local Model"
$OverlayDist = Join-Path $ProjectRoot "dist\Nihongo Wakarimasen"
Set-Location $ProjectRoot

& ".\.venv\Scripts\python.exe" -m PyInstaller `
  --noconfirm `
  --console `
  --name "Download Local Model" `
  --paths ".\src" `
  --collect-submodules "faster_whisper" `
  --collect-submodules "ctranslate2" `
  ".\tools\model_downloader_entry.py"

if (-not (Test-Path $OverlayDist)) {
  throw "Overlay dist is missing. Run .\tools\build_overlay_exe.ps1 first."
}

Copy-Item -LiteralPath (Join-Path $DistRoot "Download Local Model.exe") -Destination $OverlayDist -Force
Write-Host "Built: $OverlayDist\Download Local Model.exe"
