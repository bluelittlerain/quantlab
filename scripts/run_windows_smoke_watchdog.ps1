param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [int]$Port = 32117,
    [ValidateRange(1, 120)]
    [int]$TimeoutSeconds = 120,
    [string]$ArtifactDirectory = ""
)

$ErrorActionPreference = "Stop"

function Test-LocalPortListening([int]$PortNumber) {
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Connect = $Client.ConnectAsync("127.0.0.1", $PortNumber)
        if (-not $Connect.Wait(300)) {
            return $false
        }
        return $Client.Connected
    } catch {
        return $false
    } finally {
        $Client.Dispose()
    }
}

function Read-AppendedUtf8([string]$Path, [long]$Offset) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    $Stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        if ($Offset -gt $Stream.Length) {
            $Offset = 0
        }
        $null = $Stream.Seek($Offset, [System.IO.SeekOrigin]::Begin)
        $Reader = [System.IO.StreamReader]::new(
            $Stream,
            [System.Text.Encoding]::UTF8,
            $true
        )
        try {
            return $Reader.ReadToEnd()
        } finally {
            $Reader.Dispose()
        }
    } finally {
        $Stream.Dispose()
    }
}

$ExecutablePath = (Resolve-Path -LiteralPath $Executable).Path
if (-not $ArtifactDirectory) {
    $ArtifactDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "quantlab-smoke-watchdog"
}
New-Item -ItemType Directory -Path $ArtifactDirectory -Force | Out-Null

$StdoutLog = Join-Path $ArtifactDirectory "smoke-stdout.log"
$StderrLog = Join-Path $ArtifactDirectory "smoke-stderr.log"
$ApplicationLog = Join-Path $env:LOCALAPPDATA "QuantLab\logs\QuantLab.log"
$ApplicationLogOffset = if (Test-Path -LiteralPath $ApplicationLog) {
    (Get-Item -LiteralPath $ApplicationLog).Length
} else {
    0
}
Remove-Item -LiteralPath $StdoutLog -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $StderrLog -Force -ErrorAction SilentlyContinue

if (Test-LocalPortListening $Port) {
    throw "Smoke-test port $Port is already in use."
}

$OriginalPort = $env:QUANTLAB_PORT
$Process = $null
$ProcessStarted = $false
$StdoutTask = $null
$StderrTask = $null
$ExitCode = -1
$TimedOut = $false
$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$ProcessDeadlineSeconds = [Math]::Max(1, $TimeoutSeconds - 10)
try {
    $env:QUANTLAB_PORT = [string]$Port
    $StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $StartInfo.FileName = $ExecutablePath
    $StartInfo.Arguments = "--smoke-test"
    $StartInfo.WorkingDirectory = Split-Path -Parent $ExecutablePath
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $Process = [System.Diagnostics.Process]::new()
    $Process.StartInfo = $StartInfo
    if (-not $Process.Start()) {
        throw "Unable to start the smoke-test process."
    }
    $ProcessStarted = $true
    $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
    $StderrTask = $Process.StandardError.ReadToEndAsync()
    Write-Output "WATCHDOG_ROOT_PID=$($Process.Id)"

    while (
        -not $Process.HasExited -and
        $Stopwatch.Elapsed.TotalSeconds -lt $ProcessDeadlineSeconds
    ) {
        Start-Sleep -Milliseconds 200
        $Process.Refresh()
    }
    if (-not $Process.HasExited) {
        $TimedOut = $true
        & taskkill.exe /PID $Process.Id /T /F | Out-Null
        $null = $Process.WaitForExit(10000)
    } else {
        $Process.WaitForExit()
        $ExitCode = $Process.ExitCode
    }
} finally {
    $Stopwatch.Stop()
    if ($ProcessStarted -and -not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F | Out-Null
        $null = $Process.WaitForExit(5000)
    }
    $env:QUANTLAB_PORT = $OriginalPort
    $Stdout = if ($StdoutTask -and $StdoutTask.Wait(2000)) { $StdoutTask.Result } else { "" }
    $Stderr = if ($StderrTask -and $StderrTask.Wait(2000)) { $StderrTask.Result } else { "" }
    [System.IO.File]::WriteAllText($StdoutLog, $Stdout, [System.Text.Encoding]::UTF8)
    [System.IO.File]::WriteAllText($StderrLog, $Stderr, [System.Text.Encoding]::UTF8)
    if ($Process) {
        $Process.Dispose()
    }
}

if ($TimedOut) {
    $ExitCode = 124
}
$PortReleased = -not (Test-LocalPortListening $Port)
$SmokeLog = Read-AppendedUtf8 $ApplicationLog $ApplicationLogOffset
$RequiredMarkers = @(
    "SMOKE_START",
    "SERVICE_PID",
    "HTTP_READY",
    "CLEANUP_START",
    "SERVICE_STOPPED",
    "PORT_RELEASED",
    "SMOKE_SUCCESS"
)
$MissingMarkers = @($RequiredMarkers | Where-Object { $SmokeLog -notmatch [regex]::Escape($_) })

Write-Output "WATCHDOG_ELAPSED_MS=$($Stopwatch.ElapsedMilliseconds)"
Write-Output "WATCHDOG_EXIT_CODE=$ExitCode"
Write-Output "WATCHDOG_TIMED_OUT=$($TimedOut.ToString().ToLowerInvariant())"
Write-Output "WATCHDOG_PORT_RELEASED=$($PortReleased.ToString().ToLowerInvariant())"
Write-Output "WATCHDOG_MISSING_MARKERS=$($MissingMarkers -join ',')"
Write-Output "SMOKE_LOG_TAIL_START"
($SmokeLog -split "\r?\n" | Select-Object -Last 100) | Write-Output
Write-Output "SMOKE_LOG_TAIL_END"

if ($TimedOut -or $ExitCode -ne 0 -or -not $PortReleased -or $MissingMarkers.Count -gt 0) {
    exit 1
}
exit 0
