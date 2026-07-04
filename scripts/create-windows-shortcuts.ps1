param(
    [switch]$DesktopOnly,
    [switch]$StartMenuOnly
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcher = Join-Path $repoRoot ".venv\Scripts\pitchstems-gui.exe"
$icon = Join-Path $repoRoot "src\pitchstems\assets\pitchstems.ico"

if (-not (Test-Path $launcher)) {
    throw "Missing GUI launcher: $launcher. Run setup first so .venv\Scripts\pitchstems-gui.exe exists."
}
if (-not (Test-Path $icon)) {
    throw "Missing app icon: $icon. Run scripts\generate_app_icon.py first."
}

$shell = New-Object -ComObject WScript.Shell

function New-PitchStemsShortcut {
    param(
        [string]$ShortcutPath
    )
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $launcher
    $shortcut.WorkingDirectory = $repoRoot
    $shortcut.IconLocation = $icon
    $shortcut.Description = "PitchStems"
    $shortcut.Save()
    Write-Host "Created $ShortcutPath"
}

if (-not $StartMenuOnly) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    New-PitchStemsShortcut (Join-Path $desktop "PitchStems.lnk")
}

if (-not $DesktopOnly) {
    $programs = [Environment]::GetFolderPath("Programs")
    New-PitchStemsShortcut (Join-Path $programs "PitchStems.lnk")
}
