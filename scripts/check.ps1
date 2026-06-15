param(
    [switch]$Gpu,
    [switch]$Build,
    [switch]$GuiSmoke,
    [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$venvPitchstems = Join-Path $PSScriptRoot "..\.venv\Scripts\pitchstems.exe"

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

if (Test-Path $venvPitchstems) {
    $pitchstems = $venvPitchstems
} else {
    $pitchstemsCommand = Get-Command pitchstems -ErrorAction SilentlyContinue
    if ($null -ne $pitchstemsCommand) {
        $pitchstems = $pitchstemsCommand.Source
    } else {
        $pitchstems = $null
    }
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

function Test-GitRef {
    param([string]$Ref)

    & git rev-parse --verify --quiet $Ref *> $null
    return $LASTEXITCODE -eq 0
}

function Get-GitWhitespaceBase {
    foreach ($candidate in @("origin/main", "main")) {
        if (Test-GitRef $candidate) {
            return $candidate
        }
    }
    return $null
}

function Invoke-GitWhitespaceChecks {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "Skipping Git whitespace checks: git not found."
        return
    }

    Invoke-Checked "Checking working tree whitespace..." { & git diff --check }
    Invoke-Checked "Checking staged whitespace..." { & git diff --cached --check }

    $baseRef = Get-GitWhitespaceBase
    if ($null -eq $baseRef) {
        Write-Host "Skipping branch diff whitespace check: main ref not found."
        return
    }
    Invoke-Checked "Checking whitespace against $baseRef..." {
        & git diff --check $baseRef
    }
}

Invoke-GitWhitespaceChecks

Invoke-Checked "Running Ruff..." { & $python @pythonArgs -m ruff check src tests }

Invoke-Checked "Running Vulture..." { & $python @pythonArgs -m vulture src tests --min-confidence 80 }

Invoke-Checked "Running mypy..." { & $python @pythonArgs -m mypy }

Invoke-Checked "Running tests..." {
    & $python @pythonArgs -m pytest `
        --cov=pitchstems.editor_models `
        --cov=pitchstems.gui_editor_model `
        --cov=pitchstems.gui_jobs `
        --cov=pitchstems.gui_layout_policy `
        --cov=pitchstems.gui_pipeline_model `
        --cov=pitchstems.input_validation `
        --cov=pitchstems.preflight `
        --cov=pitchstems.pipeline `
        --cov=pitchstems.project_store `
        --cov=pitchstems.recent_projects `
        --cov=pitchstems.timeline_render_policy `
        --cov=pitchstems.time_format `
        --cov-report=term-missing `
        --cov-fail-under=90
}

Invoke-Checked "Compiling source..." { & $python @pythonArgs -m compileall src }

Invoke-Checked "Checking installed package metadata..." { & $python @pythonArgs -m pip check }

if ($SkipDoctor) {
    Write-Host "Skipping doctor: requested by check options."
} elseif ($null -ne $pitchstems -and (Test-Path $pitchstems)) {
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
