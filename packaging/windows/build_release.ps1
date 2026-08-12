param(
    [switch]$UseExistingEnvironment,
    [switch]$BrowserIsolationTest,
    [switch]$SidebarTest,
    [switch]$AutonomousUxTest,
    [switch]$PrePublicationTest,
    [switch]$ReleaseCandidate,
    [switch]$ChartDarkFinalTest,
    [Alias("HKProductPreview")]
    [switch]$UsabilityMobilePreview,
    [ValidateSet("a", "b")]
    [string]$ReproducibilityRun
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$TestBuildName = "browser-isolation-test-v0.1.1"
$SidebarBuildRoot = Join-Path $ProjectRoot "build\ql-v011-sidebar"
$AutonomousUxBuildRoot = Join-Path $ProjectRoot "build-autonomous-ux-test"
$PrePublicationBuildRoot = Join-Path $ProjectRoot "build-v0.1.1-pre-publication-test"
$ReleaseCandidateBuildRoot = Join-Path $ProjectRoot "build-v0.1.1-rc1"
$ChartDarkFinalBuildRoot = Join-Path $ProjectRoot "build-chart-dark-final-test"
# Keep the virtual environment below the legacy Windows path-length limit. The user-facing
# dist/release directories and archive retain the descriptive preview name.
$UsabilityMobilePreviewBuildRoot = Join-Path $ProjectRoot "build\q21"
$ReproducibilityBuild = -not [string]::IsNullOrWhiteSpace($ReproducibilityRun)
$ReproducibilityBuildRoot = if ($ReproducibilityBuild) {
    Join-Path $ProjectRoot "build-repro-$ReproducibilityRun"
}
$SelectedTestModes = @(
    $BrowserIsolationTest,
    $SidebarTest,
    $AutonomousUxTest,
    $PrePublicationTest,
    $ReleaseCandidate,
    $ChartDarkFinalTest,
    $UsabilityMobilePreview,
    $ReproducibilityBuild
) |
    Where-Object { $_ }
if ($SelectedTestModes.Count -gt 1) {
    throw "Choose only one test build mode."
}
$BuildVenv = if ($UsabilityMobilePreview) {
    Join-Path $UsabilityMobilePreviewBuildRoot "venv"
} elseif ($ReproducibilityBuild) {
    Join-Path $ReproducibilityBuildRoot "venv"
} elseif ($ReleaseCandidate) {
    Join-Path $ReleaseCandidateBuildRoot "venv"
} elseif ($ChartDarkFinalTest) {
    Join-Path $ChartDarkFinalBuildRoot "venv"
} elseif ($PrePublicationTest) {
    Join-Path $PrePublicationBuildRoot "venv"
} elseif ($AutonomousUxTest) {
    Join-Path $AutonomousUxBuildRoot "venv"
} elseif ($SidebarTest) {
    Join-Path $SidebarBuildRoot "venv"
} elseif ($BrowserIsolationTest) {
    Join-Path $ProjectRoot "build\ql-v011-venv"
} else {
    Join-Path $ProjectRoot ".build-venv"
}
$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$BuildPython = if ($UseExistingEnvironment) {
    $ProjectPython
} else {
    Join-Path $BuildVenv "Scripts\python.exe"
}
$Requirements = Join-Path $ProjectRoot "requirements.lock"
$WorkPath = if ($UsabilityMobilePreview) {
    Join-Path $UsabilityMobilePreviewBuildRoot "pyinstaller"
} elseif ($ReproducibilityBuild) {
    Join-Path $ReproducibilityBuildRoot "pyinstaller"
} elseif ($ReleaseCandidate) {
    Join-Path $ReleaseCandidateBuildRoot "pyinstaller"
} elseif ($ChartDarkFinalTest) {
    Join-Path $ChartDarkFinalBuildRoot "pyinstaller"
} elseif ($PrePublicationTest) {
    Join-Path $PrePublicationBuildRoot "pyinstaller"
} elseif ($AutonomousUxTest) {
    Join-Path $AutonomousUxBuildRoot "pyinstaller"
} elseif ($SidebarTest) {
    Join-Path $SidebarBuildRoot "pyinstaller"
} elseif ($BrowserIsolationTest) {
    Join-Path $ProjectRoot "build\$TestBuildName\pyinstaller"
} else {
    Join-Path $ProjectRoot "build\windows"
}
$DistPath = if ($UsabilityMobilePreview) {
    Join-Path $ProjectRoot "dist-v0.2.1-usability-mobile-preview"
} elseif ($ReproducibilityBuild) {
    Join-Path $ProjectRoot "dist-repro-$ReproducibilityRun"
} elseif ($ReleaseCandidate) {
    Join-Path $ProjectRoot "dist-v0.1.1-rc1"
} elseif ($ChartDarkFinalTest) {
    Join-Path $ProjectRoot "dist-chart-dark-final-test"
} elseif ($PrePublicationTest) {
    Join-Path $ProjectRoot "dist-v0.1.1-pre-publication-test"
} elseif ($AutonomousUxTest) {
    Join-Path $ProjectRoot "dist-autonomous-ux-test"
} elseif ($SidebarTest) {
    Join-Path $ProjectRoot "dist\ql-v011-sidebar"
} elseif ($BrowserIsolationTest) {
    Join-Path $ProjectRoot "dist\$TestBuildName"
} else {
    Join-Path $ProjectRoot "dist\windows"
}
$ReleasePath = if ($UsabilityMobilePreview) {
    Join-Path $ProjectRoot "release-v0.2.1-usability-mobile-preview"
} elseif ($ReproducibilityBuild) {
    Join-Path $ProjectRoot "release-repro-$ReproducibilityRun"
} elseif ($ReleaseCandidate) {
    Join-Path $ProjectRoot "release-v0.1.1-rc1"
} elseif ($ChartDarkFinalTest) {
    Join-Path $ProjectRoot "release-chart-dark-final-test"
} elseif ($PrePublicationTest) {
    Join-Path $ProjectRoot "release-v0.1.1-pre-publication-test"
} elseif ($AutonomousUxTest) {
    Join-Path $ProjectRoot "release-autonomous-ux-test"
} elseif ($SidebarTest) {
    Join-Path $ProjectRoot "release-v0.1.1-sidebar-test"
} elseif ($BrowserIsolationTest) {
    Join-Path $ProjectRoot "release\$TestBuildName"
} else {
    Join-Path $ProjectRoot "release"
}
$SpecPath = Join-Path $PSScriptRoot "QuantLab.spec"
$ThirdPartyNoticeScript = Join-Path $PSScriptRoot "generate_third_party_notices.py"
$FrontendNoticeScript = Join-Path $PSScriptRoot "generate_frontend_notices.py"
$ReleaseCandidateChecklist = Join-Path $PSScriptRoot "RC1-TEST-CHECKLIST.md"
$ChartDarkFinalChecklist = Join-Path $PSScriptRoot "CHART-DARK-FINAL-CHECKLIST.md"
$UsabilityMobilePreviewChecklist = Join-Path $PSScriptRoot "USABILITY-MOBILE-PREVIEW-CHECKLIST.md"

if ($UsabilityMobilePreview) {
    $env:PIP_CACHE_DIR = Join-Path ([System.IO.Path]::GetTempPath()) "ql-v021-mobile-preview-pip"
} elseif ($ReproducibilityBuild) {
    $env:PIP_CACHE_DIR = Join-Path (
        [System.IO.Path]::GetTempPath()
    ) "ql-v011-repro-$ReproducibilityRun-pip"
} elseif ($ReleaseCandidate) {
    $env:PIP_CACHE_DIR = Join-Path ([System.IO.Path]::GetTempPath()) "ql-v011-rc1-pip"
} elseif ($ChartDarkFinalTest) {
    $env:PIP_CACHE_DIR = Join-Path ([System.IO.Path]::GetTempPath()) "ql-v011-chart-dark-final-pip"
} elseif ($PrePublicationTest) {
    $env:PIP_CACHE_DIR = Join-Path ([System.IO.Path]::GetTempPath()) "ql-v011-prepub-pip"
} elseif ($AutonomousUxTest) {
    # Keep pip wheel intermediates below the legacy Windows path-length limit.
    # This cache is never copied into the application or release archive.
    $env:PIP_CACHE_DIR = Join-Path ([System.IO.Path]::GetTempPath()) "ql-v011-ux-pip"
} elseif ($SidebarTest) {
    $env:PIP_CACHE_DIR = Join-Path $ProjectRoot "build\pip-cache-sidebar"
} elseif ($BrowserIsolationTest) {
    $env:PIP_CACHE_DIR = Join-Path $ProjectRoot "build\pip-cache-v011"
}

function Assert-NativeCommand([string]$Description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Remove-SafeProjectPath([string]$Target) {
    if (-not (Test-Path -LiteralPath $Target)) {
        return
    }
    $Resolved = (Resolve-Path -LiteralPath $Target).Path
    $Prefix = $ProjectRoot + [System.IO.Path]::DirectorySeparatorChar
    if (-not $Resolved.StartsWith($Prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside project: $Resolved"
    }
    Remove-Item -LiteralPath $Resolved -Recurse -Force
}

function Find-BasePython {
    if ($env:QUANTLAB_BUILD_PYTHON) {
        if (-not (Test-Path -LiteralPath $env:QUANTLAB_BUILD_PYTHON)) {
            throw "QUANTLAB_BUILD_PYTHON does not exist: $env:QUANTLAB_BUILD_PYTHON"
        }
        return (Resolve-Path -LiteralPath $env:QUANTLAB_BUILD_PYTHON).Path
    }
    if (Test-Path -LiteralPath $ProjectPython) {
        return (Resolve-Path -LiteralPath $ProjectPython).Path
    }
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $Resolved = (& py -3.12 -c "import sys; print(sys.executable)").Trim()
        if ($LASTEXITCODE -eq 0 -and $Resolved) {
            return $Resolved
        }
    }
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        return $PythonCommand.Source
    }
    throw "Python 3.12 x64 was not found. Set QUANTLAB_BUILD_PYTHON to python.exe."
}

function Find-Node {
    if ($env:QUANTLAB_NODE) {
        if (-not (Test-Path -LiteralPath $env:QUANTLAB_NODE -PathType Leaf)) {
            throw "QUANTLAB_NODE does not exist: $env:QUANTLAB_NODE"
        }
        return (Resolve-Path -LiteralPath $env:QUANTLAB_NODE).Path
    }
    $NodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($NodeCommand) {
        return $NodeCommand.Source
    }
    throw "Node.js was not found. Set QUANTLAB_NODE to node.exe."
}

$BasePython = Find-BasePython
$PythonVersion = (& $BasePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
$PythonBits = (& $BasePython -c "import struct; print(struct.calcsize('P') * 8)").Trim()
if ($PythonVersion -ne "3.12" -or $PythonBits -ne "64") {
    throw "Windows Release requires Python 3.12 x64; found Python $PythonVersion ($PythonBits-bit)."
}

$Node = Find-Node
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$TypeScriptCli = Join-Path $FrontendRoot "node_modules\typescript\bin\tsc"
$ViteCli = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
if (-not (Test-Path -LiteralPath $TypeScriptCli) -or -not (Test-Path -LiteralPath $ViteCli)) {
    throw "Frontend dependencies are missing. Run pnpm install --frozen-lockfile first."
}
Push-Location $FrontendRoot
try {
    & $Node $TypeScriptCli -b
    Assert-NativeCommand "Type-checking the React frontend"
    & $Node $ViteCli build
    Assert-NativeCommand "Building the React frontend"
} finally {
    Pop-Location
}

if ($UseExistingEnvironment) {
    if (-not (Test-Path -LiteralPath $ProjectPython -PathType Leaf)) {
        throw "The verified project environment does not exist: $ProjectPython"
    }
    & $BuildPython -c "import PyInstaller, quant_lab"
    Assert-NativeCommand "Checking the verified project build environment"
} else {
    Remove-SafeProjectPath $BuildVenv
    & $BasePython -m venv $BuildVenv
    Assert-NativeCommand "Creating the build virtual environment"

    $LockedInstallArguments = @("-m", "pip", "install", "--require-hashes")
    if ($env:QUANTLAB_WHEELHOUSE) {
        if (-not (Test-Path -LiteralPath $env:QUANTLAB_WHEELHOUSE -PathType Container)) {
            throw "QUANTLAB_WHEELHOUSE is not a directory."
        }
        $Wheelhouse = (Resolve-Path -LiteralPath $env:QUANTLAB_WHEELHOUSE).Path
        $LockedInstallArguments += @("--no-index", "--find-links", $Wheelhouse)
    }
    $LockedInstallArguments += @("-r", $Requirements)
    & $BuildPython @LockedInstallArguments
    Assert-NativeCommand "Installing locked build dependencies"

    # Setuptools writes these wheel intermediates into the project-level build directory.
    # Remove only those known transient paths so repeated builds remain deterministic.
    foreach ($Target in @(
        (Join-Path $ProjectRoot "build\lib"),
        (Join-Path $ProjectRoot "build\bdist.win-amd64")
    )) {
        Remove-SafeProjectPath $Target
    }
    & $BuildPython -m pip install --no-build-isolation --no-deps $ProjectRoot
    Assert-NativeCommand "Installing QuantLab into the build environment"
}
$Version = (& $BuildPython -c "from quant_lab import __version__; print(__version__)").Trim()
Assert-NativeCommand "Reading the QuantLab version"

foreach ($Target in @($WorkPath, $DistPath)) {
    Remove-SafeProjectPath $Target
}

& $BuildPython -m PyInstaller `
    --clean `
    --noconfirm `
    --workpath $WorkPath `
    --distpath $DistPath `
    $SpecPath
Assert-NativeCommand "Building QuantLab with PyInstaller"

$AppDirectory = Join-Path $DistPath "QuantLab"
if (-not (Test-Path (Join-Path $AppDirectory "QuantLab.exe"))) {
    throw "QuantLab.exe was not produced."
}
$ReadmeTemplate = [IO.File]::ReadAllText(
    (Join-Path $PSScriptRoot "README-WINDOWS.txt"),
    [Text.Encoding]::UTF8
)
$ReleaseReadme = $ReadmeTemplate.Replace("{{VERSION}}", $Version)
$Utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText(
    (Join-Path $AppDirectory "README-WINDOWS.txt"),
    $ReleaseReadme,
    $Utf8NoBom
)
Copy-Item (Join-Path $ProjectRoot "LICENSE") $AppDirectory -Force
& $BuildPython $ThirdPartyNoticeScript `
    --output (Join-Path $AppDirectory "THIRD-PARTY-NOTICES.txt") `
    --exclude "quantlab-stock-etf-backtester"
Assert-NativeCommand "Generating third-party notices"
& $BuildPython $FrontendNoticeScript `
    --frontend $FrontendRoot `
    --output (Join-Path $AppDirectory "THIRD-PARTY-NOTICES-FRONTEND.txt")
Assert-NativeCommand "Generating frontend third-party notices"

New-Item -ItemType Directory -Path $ReleasePath -Force | Out-Null
$ZipName = if ($UsabilityMobilePreview) {
    "QuantLab-v$Version-usability-mobile-preview-windows-x64.zip"
} elseif ($ReproducibilityBuild) {
    "QuantLab-v$Version-repro-$ReproducibilityRun-windows-x64.zip"
} elseif ($ReleaseCandidate) {
    "QuantLab-v$Version-rc1-windows-x64.zip"
} elseif ($ChartDarkFinalTest) {
    "QuantLab-v$Version-chart-dark-final-test-windows-x64.zip"
} elseif ($PrePublicationTest) {
    "QuantLab-v$Version-pre-publication-test-windows-x64.zip"
} elseif ($AutonomousUxTest) {
    "QuantLab-v0.1.1-autonomous-ux-test-windows-x64.zip"
} elseif ($SidebarTest) {
    "QuantLab-v0.1.1-sidebar-test-windows-x64.zip"
} elseif ($BrowserIsolationTest) {
    "QuantLab-v0.1.1-browser-isolation-test-windows-x64.zip"
} else {
    "QuantLab-v$Version-windows-x64.zip"
}
$ZipPath = Join-Path $ReleasePath $ZipName
$ChecksumPath = Join-Path $ReleasePath "SHA256SUMS.txt"
$ReleaseNotesSource = Join-Path $ProjectRoot "RELEASE-NOTES-v$Version.md"
$ReleaseNotesPath = Join-Path $ReleasePath "RELEASE-NOTES-v$Version.md"
$ChecklistPath = Join-Path $ReleasePath "RC1-TEST-CHECKLIST.md"
$ChartDarkChecklistPath = Join-Path $ReleasePath "CHART-DARK-FINAL-CHECKLIST.md"
$UsabilityMobilePreviewChecklistPath = Join-Path $ReleasePath "TEST-CHECKLIST.md"
if ($UsabilityMobilePreview -and (
    (Test-Path -LiteralPath $ZipPath) -or
    (Test-Path -LiteralPath $ChecksumPath) -or
    (Test-Path -LiteralPath $UsabilityMobilePreviewChecklistPath)
)) {
    throw "Refusing to overwrite an existing usability/mobile preview artifact in $ReleasePath."
}
if ($ReleaseCandidate -and (
    (Test-Path -LiteralPath $ZipPath) -or
    (Test-Path -LiteralPath $ChecksumPath) -or
    (Test-Path -LiteralPath $ChecklistPath)
)) {
    throw "Refusing to overwrite an existing RC1 artifact in $ReleasePath."
}
if ($ChartDarkFinalTest -and (
    (Test-Path -LiteralPath $ZipPath) -or
    (Test-Path -LiteralPath $ChecksumPath) -or
    (Test-Path -LiteralPath $ChartDarkChecklistPath)
)) {
    throw "Refusing to overwrite an existing chart dark final artifact in $ReleasePath."
}
if ($PrePublicationTest -and (
    (Test-Path -LiteralPath $ZipPath) -or
    (Test-Path -LiteralPath $ChecksumPath)
)) {
    throw "Refusing to overwrite an existing pre-publication artifact in $ReleasePath."
}
if ($ReproducibilityBuild -and (
    (Test-Path -LiteralPath $ZipPath) -or
    (Test-Path -LiteralPath $ChecksumPath)
)) {
    throw "Refusing to overwrite an existing reproducibility artifact in $ReleasePath."
}
if (
    -not $ReproducibilityBuild -and
    -not $ReleaseCandidate -and
    -not $ChartDarkFinalTest -and
    -not $PrePublicationTest -and
    -not $UsabilityMobilePreview -and
    (Test-Path $ZipPath)
) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path $AppDirectory -DestinationPath $ZipPath -CompressionLevel Optimal
$Hash = (Get-FileHash -Algorithm SHA256 $ZipPath).Hash.ToLowerInvariant()
"$Hash *$ZipName" | Set-Content -Encoding ascii -NoNewline $ChecksumPath
if (-not (Test-Path -LiteralPath $ReleaseNotesSource -PathType Leaf)) {
    throw "Release notes are missing: $ReleaseNotesSource"
}
Copy-Item -LiteralPath $ReleaseNotesSource -Destination $ReleaseNotesPath -Force
if ($ReleaseCandidate) {
    Copy-Item -LiteralPath $ReleaseCandidateChecklist -Destination $ChecklistPath
}
if ($ChartDarkFinalTest) {
    Copy-Item -LiteralPath $ChartDarkFinalChecklist -Destination $ChartDarkChecklistPath
}
if ($UsabilityMobilePreview) {
    Copy-Item -LiteralPath $UsabilityMobilePreviewChecklist -Destination $UsabilityMobilePreviewChecklistPath
}

Write-Host "Built $ZipPath"
Write-Host "SHA256 $Hash"
