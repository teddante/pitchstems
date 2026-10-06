# Shared helpers for PitchStems PowerShell scripts. Dot-source with: . "$PSScriptRoot\common.ps1"

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

function Resolve-PitchStemsPython {
    # Prefer the project venv, then python on PATH, then the py launcher for 3.10.
    $venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return @{ Path = $venvPython; Args = @() }
    }
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        return @{ Path = $pythonCommand.Source; Args = @() }
    }
    return @{ Path = "py"; Args = @("-3.10") }
}
