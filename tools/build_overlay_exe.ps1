$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

& ".\.venv\Scripts\python.exe" -m PyInstaller `
  --noconfirm `
  --windowed `
  --name "Nihongo Wakarimasen" `
  --paths ".\src" `
  --collect-submodules "faster_whisper" `
  --collect-submodules "ctranslate2" `
  --collect-submodules "process_audio_capture" `
  --collect-submodules "recap_capture" `
  ".\tools\overlay_entry.py"

$InternalDir = Join-Path $ProjectRoot "dist\Nihongo Wakarimasen\_internal"
$NvidiaDir = Join-Path $ProjectRoot ".venv\Lib\site-packages\nvidia"
if (Test-Path $NvidiaDir) {
  Get-ChildItem -LiteralPath $NvidiaDir -Recurse -File -Filter "*.dll" |
    Where-Object { $_.FullName -like "*\bin\*" } |
    Copy-Item -Destination $InternalDir -Force
}

Write-Host "Built: $ProjectRoot\dist\Nihongo Wakarimasen\Nihongo Wakarimasen.exe"
