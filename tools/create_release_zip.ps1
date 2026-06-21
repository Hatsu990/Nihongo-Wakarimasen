$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ReleaseRoot = Join-Path $ProjectRoot "release"
$PackageName = "Nihongo-Wakarimasen"
$PackageDir = Join-Path $ReleaseRoot $PackageName
$ZipPath = Join-Path $ReleaseRoot "$PackageName.zip"
$OverlayDist = Join-Path $ProjectRoot "dist\Nihongo Wakarimasen"
$HotwordExe = Join-Path $ProjectRoot "dist\NihongoHotwordManager\NihongoHotwordManager.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $OverlayDist)) {
    throw "Overlay exe is missing. Run .\tools\build_overlay_exe.ps1 first."
}
if (-not (Test-Path $HotwordExe)) {
    throw "Hotword manager exe is missing. Run .\tools\build_hotword_manager_exe.ps1 first."
}

if (Test-Path $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

New-Item -ItemType Directory -Path $PackageDir | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PackageDir "config") | Out-Null

Copy-Item -Path (Join-Path $OverlayDist "*") -Destination $PackageDir -Recurse
Copy-Item -LiteralPath $HotwordExe -Destination (Join-Path $PackageDir "Name Dictionary.exe")
Copy-Item -LiteralPath ".\README.md" -Destination $PackageDir

Get-ChildItem -LiteralPath ".\config" -File |
    Where-Object {
        $_.Name -notlike "*user*" -and
        $_.Name -notlike "*credentials*" -and
        $_.Name -ne "stt_hotwords_ja.json"
    } |
    Copy-Item -Destination (Join-Path $PackageDir "config")

Get-ChildItem -LiteralPath $PackageDir -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $PackageDir -Recurse -File -Filter "*.pyc" |
    Remove-Item -Force

Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath
Write-Host "Release ZIP created: $ZipPath"
