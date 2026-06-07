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

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    Write-Host $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

Invoke-Checked "Running Ruff..." { & $python @pythonArgs -m ruff check src tests }

Invoke-Checked "Running tests..." { & $python @pythonArgs -m pytest }

Invoke-Checked "Compiling source..." { & $python @pythonArgs -m compileall src }

Invoke-Checked "Checking installed package metadata..." { & $python @pythonArgs -m pip check }

if (Test-Path $pitchstems) {
    Invoke-Checked "Running doctor..." { & $pitchstems --doctor }
    if ($Gpu) {
        Invoke-Checked "Running GPU doctor..." { & $pitchstems --doctor --gpu }
    }
} else {
    Write-Host "Skipping doctor: venv launcher not found."
}

if ($GuiSmoke) {
    $previousQtPlatform = $env:QT_QPA_PLATFORM
    $previousGuiSmoke = $env:PITCHSTEMS_GUI_SMOKE
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:PITCHSTEMS_GUI_SMOKE = "project"
    try {
        Invoke-Checked "Running GUI smoke test..." {
        @'
from pitchstems.app import main
raise SystemExit(main())
'@ | & $python @pythonArgs -
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
    }
}

if ($Build) {
    Invoke-Checked "Building package..." { & $python @pythonArgs -m build }
}

Write-Host "All requested checks passed."
