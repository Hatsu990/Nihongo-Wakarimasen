param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status",
    [string]$CaptureProcess = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$PidPath = Join-Path $Root "logs\overlay.pid"
$StdoutPath = Join-Path $Root "logs\overlay_stdout.log"
$StderrPath = Join-Path $Root "logs\overlay_stderr.log"

function Import-UserEnv($Name) {
    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        $value = [Environment]::GetEnvironmentVariable($Name, "User")
        if ($value) {
            [Environment]::SetEnvironmentVariable($Name, $value, "Process")
        }
    }
}

function Get-OverlayProcess {
    if (-not (Test-Path $PidPath)) {
        return Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -like "*nihongo_wakarimasen*" -and
                $_.CommandLine -like "*--overlay*"
            } |
            Select-Object -First 1
    }
    $savedPid = Get-Content $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $savedPid) {
        return $null
    }
    try {
        return Get-Process -Id ([int]$savedPid) -ErrorAction Stop
    }
    catch {
        return Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -like "*nihongo_wakarimasen*" -and
                $_.CommandLine -like "*--overlay*"
            } |
            Select-Object -First 1
    }
}

function Get-OverlayPid($Process) {
    if ($null -eq $Process) {
        return $null
    }
    if ($Process.PSObject.Properties.Name -contains "ProcessId") {
        return [int]$Process.ProcessId
    }
    return [int]$Process.Id
}

if ($Action -eq "status") {
    $process = Get-OverlayProcess
    if ($process) {
        Write-Output "overlay running: pid=$(Get-OverlayPid $process)"
    }
    else {
        Write-Output "overlay stopped"
    }
    exit 0
}

if ($Action -eq "stop") {
    $process = Get-OverlayProcess
    if ($process) {
        $pidValue = Get-OverlayPid $process
        Stop-Process -Id $pidValue -Force
        Write-Output "overlay stopped: pid=$pidValue"
    }
    else {
        Write-Output "overlay already stopped"
    }
    if (Test-Path $PidPath) {
        Remove-Item -LiteralPath $PidPath -Force
    }
    exit 0
}

if ($Action -eq "start") {
    $process = Get-OverlayProcess
    if ($process) {
        Write-Output "overlay already running: pid=$(Get-OverlayPid $process)"
        exit 0
    }

    Import-UserEnv "OPENAI_API_KEY"
    Import-UserEnv "PAPAGO_CLIENT_ID"
    Import-UserEnv "PAPAGO_CLIENT_SECRET"
    Import-UserEnv "NAVER_CLIENT_ID"
    Import-UserEnv "NAVER_CLIENT_SECRET"

    $env:NW_STT_PROVIDER = "local"
    $env:NW_WHISPER_MODEL = "kotoba-tech/kotoba-whisper-v2.0-faster"
    $env:NW_WHISPER_DEVICE = "cuda"
    $env:NW_WHISPER_COMPUTE_TYPE = "float16"
    $env:NW_STT_BEAM_SIZE = "5"

    $args = @(
        "-m", "nihongo_wakarimasen",
        "--overlay",
        "--stt-provider", "local",
        "--capture-interval", "0.25",
        "--overlap-stt",
        "--overlap-window", "5.5",
        "--overlap-step", "1.5",
        "--beam-size", "5",
        "--papago-timeout", "4"
    )
    if ($CaptureProcess) {
        $args += @("--capture-process", $CaptureProcess)
    }

    $process = Start-Process `
        -FilePath $Python `
        -ArgumentList $args `
        -WorkingDirectory $Root `
        -PassThru `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath

    Set-Content -Path $PidPath -Value $process.Id
    Write-Output "overlay started: pid=$($process.Id)"
}
