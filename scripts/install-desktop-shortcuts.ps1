[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Launcher = (Resolve-Path (Join-Path $PSScriptRoot "als-monitor.ps1")).Path
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shell = New-Object -ComObject WScript.Shell

function New-ALSShortcut {
    param(
        [string]$Name,
        [string]$Service,
        [string]$Description
    )

    $shortcutPath = Join-Path $Desktop "$Name.lnk"
    $shortcut = $Shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`" $Service"
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.Description = $Description
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,21"
    $shortcut.Save()
    Write-Host "Created: $shortcutPath"
}

New-ALSShortcut "ALS Eye Tracker" "eye" "Run the ALS eye-tracking service"
New-ALSShortcut "ALS Grip Monitor" "grip" "Run the ALS grip-monitor service"
New-ALSShortcut "ALS Shoulder Monitor" "shoulder" "Run the ALS shoulder-monitor service"
New-ALSShortcut "ALS Speech Analysis" "speech" "Run the ALS speech-analysis service"
New-ALSShortcut "NEXA UI" "ui" "Run the NEXA user interface"

Write-Host "Windows desktop shortcuts installed successfully."

