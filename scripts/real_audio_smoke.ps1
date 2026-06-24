param(
    [Parameter(Mandatory = $true)]
    [string]$AudioPath,

    [string]$OutputDir = "",

    [ValidateSet("pitched", "all")]
    [string]$MidiPolicy = "pitched"
)

$ErrorActionPreference = "Stop"

$previousPythonIoEncoding = $env:PYTHONIOENCODING
$env:PYTHONIOENCODING = "utf-8"

try {
$resolvedAudio = (Resolve-Path -LiteralPath $AudioPath).Path
if (-not $OutputDir) {
    $OutputDir = Join-Path ([System.IO.Path]::GetTempPath()) ("pitchstems-real-audio-smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$resolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null
$resolvedExport = Join-Path $resolvedOutput "selected-export"
New-Item -ItemType Directory -Force -Path $resolvedExport | Out-Null

$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
    $pythonArgs = @()
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        $python = $pythonCommand.Source
        $pythonArgs = @()
    } else {
        $python = "py"
        $pythonArgs = @("-3.10")
    }
}

Write-Host "Running real-audio CLI smoke..."
& $python @pythonArgs -m pitchstems.cli $resolvedAudio --output-dir $resolvedOutput --midi-policy $MidiPolicy --no-zip
if ($LASTEXITCODE -ne 0) {
    throw "CLI real-audio smoke failed with exit code $LASTEXITCODE"
}

$manifest = Get-ChildItem -Path $resolvedOutput -Filter "pitchstems.project.json" -Recurse |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($null -eq $manifest) {
    throw "No pitchstems.project.json manifest was produced under $resolvedOutput"
}

Write-Host "Running offscreen GUI review/export smoke..."
$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousGuiSmoke = $env:PITCHSTEMS_GUI_SMOKE
$previousManifest = $env:PITCHSTEMS_REAL_AUDIO_SMOKE_MANIFEST
$previousExport = $env:PITCHSTEMS_REAL_AUDIO_EXPORT_DIR
$env:QT_QPA_PLATFORM = "offscreen"
$env:PITCHSTEMS_GUI_SMOKE = "real-audio"
$env:PITCHSTEMS_REAL_AUDIO_SMOKE_MANIFEST = $manifest.FullName
$env:PITCHSTEMS_REAL_AUDIO_EXPORT_DIR = $resolvedExport
try {
    & $python @pythonArgs -c "from pitchstems.app import main; raise SystemExit(main())"
    if ($LASTEXITCODE -ne 0) {
        throw "GUI real-audio smoke failed with exit code $LASTEXITCODE"
    }
} finally {
    if ($null -eq $previousQtPlatform) {
        Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    } else {
        $env:QT_QPA_PLATFORM = $previousQtPlatform
    }
    if ($null -eq $previousGuiSmoke) {
        Remove-Item Env:\PITCHSTEMS_GUI_SMOKE -ErrorAction SilentlyContinue
    } else {
        $env:PITCHSTEMS_GUI_SMOKE = $previousGuiSmoke
    }
    if ($null -eq $previousManifest) {
        Remove-Item Env:\PITCHSTEMS_REAL_AUDIO_SMOKE_MANIFEST -ErrorAction SilentlyContinue
    } else {
        $env:PITCHSTEMS_REAL_AUDIO_SMOKE_MANIFEST = $previousManifest
    }
    if ($null -eq $previousExport) {
        Remove-Item Env:\PITCHSTEMS_REAL_AUDIO_EXPORT_DIR -ErrorAction SilentlyContinue
    } else {
        $env:PITCHSTEMS_REAL_AUDIO_EXPORT_DIR = $previousExport
    }
}

Write-Host "Real-audio smoke passed."
Write-Host "Project: $($manifest.DirectoryName)"
Write-Host "Selected export: $resolvedExport"
} finally {
    if ($null -eq $previousPythonIoEncoding) {
        Remove-Item Env:\PYTHONIOENCODING -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONIOENCODING = $previousPythonIoEncoding
    }
}
