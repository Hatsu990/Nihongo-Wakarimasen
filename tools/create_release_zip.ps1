$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ReleaseRoot = Join-Path $ProjectRoot "release"
$PackageName = "Nihongo-Wakarimasen"
$PackageDir = Join-Path $ReleaseRoot $PackageName
$ZipPath = Join-Path $ReleaseRoot "$PackageName.zip"

Set-Location $ProjectRoot

if (Test-Path $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

New-Item -ItemType Directory -Path $PackageDir | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PackageDir "config") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PackageDir "src") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PackageDir "tools") | Out-Null

Copy-Item -LiteralPath ".\.gitignore" -Destination $PackageDir
Copy-Item -LiteralPath ".\README.md" -Destination $PackageDir
Copy-Item -LiteralPath ".\pyproject.toml" -Destination $PackageDir
Copy-Item -LiteralPath ".\requirements.txt" -Destination $PackageDir
Copy-Item -LiteralPath ".\requirements-gpu.txt" -Destination $PackageDir
Copy-Item -LiteralPath ".\setup.ps1" -Destination $PackageDir

Copy-Item -LiteralPath ".\src\nihongo_wakarimasen" -Destination (Join-Path $PackageDir "src") -Recurse
Get-ChildItem -LiteralPath ".\config" -File |
    Where-Object {
        $_.Name -notlike "*user*" -and
        $_.Name -notlike "*credentials*" -and
        $_.Name -ne "stt_hotwords_ja.json"
    } |
    Copy-Item -Destination (Join-Path $PackageDir "config")

$toolFiles = @(
    "overlay_control.ps1",
    "hotword_manager.ps1",
    "hotword_manager_entry.py",
    "build_hotword_manager_exe.ps1",
    "preload_local_model.py",
    "preload_local_model.ps1"
)
foreach ($toolFile in $toolFiles) {
    Copy-Item -LiteralPath (Join-Path ".\tools" $toolFile) -Destination (Join-Path $PackageDir "tools")
}

Get-ChildItem -LiteralPath $PackageDir -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $PackageDir -Recurse -File -Filter "*.pyc" |
    Remove-Item -Force

Compress-Archive -Path $PackageDir -DestinationPath $ZipPath
Write-Host "Release ZIP created: $ZipPath"
