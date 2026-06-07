param(
    [switch]$Gpu,
    [switch]$Build,
    [switch]$GuiSmoke
)

$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$pitchstems = Join-Path $PSScriptRoot "..\.venv\Scripts\pitchstems.exe"

if (-not (Test-Path $python)) {
    $python = "py"
    $pythonArgs = @("-3.10")
} else {
    $pythonArgs = @()
}

Write-Host "Running Ruff..."
& $python @pythonArgs -m ruff check src tests

Write-Host "Running tests..."
& $python @pythonArgs -m pytest

Write-Host "Compiling source..."
& $python @pythonArgs -m compileall src

Write-Host "Checking installed package metadata..."
& $python @pythonArgs -m pip check

if (Test-Path $pitchstems) {
    Write-Host "Running doctor..."
    & $pitchstems --doctor
    if ($Gpu) {
        Write-Host "Running GPU doctor..."
        & $pitchstems --doctor --gpu
    }
} else {
    Write-Host "Skipping doctor: venv launcher not found."
}

if ($GuiSmoke) {
    Write-Host "Running GUI smoke test..."
    $previousQtPlatform = $env:QT_QPA_PLATFORM
    $previousGuiSmoke = $env:PITCHSTEMS_GUI_SMOKE
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:PITCHSTEMS_GUI_SMOKE = "project"
    try {
        @'
from pitchstems.app import main
raise SystemExit(main())
'@ | & $python @pythonArgs -
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
    }
}

if ($Build) {
    Write-Host "Building package..."
    & $python @pythonArgs -m build
}

Write-Host "All requested checks passed."
