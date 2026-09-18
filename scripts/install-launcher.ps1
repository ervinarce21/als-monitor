[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Launcher = (Resolve-Path (Join-Path $PSScriptRoot "als-monitor.ps1")).Path
$InstallDirectory = Join-Path $env:LOCALAPPDATA "Programs\ALSMonitor\bin"
$CommandPath = Join-Path $InstallDirectory "als-monitor.cmd"

New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null

$command = @"
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Launcher" %*
"@
Set-Content -LiteralPath $CommandPath -Value $command -Encoding ASCII

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathEntries = @($userPath -split ";" | Where-Object { $_ })
if ($InstallDirectory -notin $pathEntries) {
    $newPath = (@($pathEntries) + $InstallDirectory) -join ";"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
}
if ($InstallDirectory -notin ($env:Path -split ";")) {
    $env:Path = "$env:Path;$InstallDirectory"
}

Write-Host "Installed: $CommandPath"
Write-Host "Open a new terminal, then run: als-monitor"

