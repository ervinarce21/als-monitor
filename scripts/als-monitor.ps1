[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Service,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ServiceArguments
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SourcePath = Join-Path $ProjectRoot "src"

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$SourcePath;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $SourcePath
}

function Find-ProjectPython {
    $candidates = @()
    if ($env:ALS_MONITOR_PYTHON) {
        $candidates += [pscustomobject]@{
            Executable = $env:ALS_MONITOR_PYTHON
            Prefix = @()
            Label = "ALS_MONITOR_PYTHON"
        }
    }
    if ($env:VIRTUAL_ENV) {
        $candidates += [pscustomobject]@{
            Executable = (Join-Path $env:VIRTUAL_ENV "Scripts\python.exe")
            Prefix = @()
            Label = "active virtual environment"
        }
    }
    $candidates += [pscustomobject]@{
        Executable = "python"
        Prefix = @()
        Label = "python"
    }
    $candidates += [pscustomobject]@{
        Executable = "py"
        Prefix = @("-3")
        Label = "py -3"
    }

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Executable -ErrorAction SilentlyContinue)) {
            continue
        }
        $checkArguments = @($candidate.Prefix) + @(
            "-c", "import sqlite3, numpy; print('ok')"
        )
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $null = & $candidate.Executable @checkArguments 2>$null
            $checkExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorAction
        }
        if ($checkExitCode -eq 0) {
            return $candidate
        }
    }

    Write-Host -ForegroundColor Red @"
No usable Python installation was found. The selected Python must be able to
import sqlite3 and numpy. Your Anaconda installation may have a broken DLL.

Test it with:
  py -3 -c "import sqlite3, numpy; print('Python OK')"

Install or repair Python, install numpy, or set ALS_MONITOR_PYTHON to a working
python.exe path.
"@
    return $null
}

function Invoke-ProjectPython {
    param([string[]]$Arguments)

    $python = Find-ProjectPython
    if ($null -eq $python) {
        return 1
    }
    $allArguments = @($python.Prefix) + $Arguments
    & $python.Executable @allArguments
    return $LASTEXITCODE
}

function Show-LauncherHelp {
    @"
Usage: als-monitor SERVICE [OPTIONS]

Services:
  ui        Run the NEXA user interface
  eye       Run the eye-tracking test (Raspberry Pi camera required)
  preview   Run the eye-camera preview (Raspberry Pi camera required)
  grip      Run the load-cell grip monitor
  shoulder  Run the shoulder-angle monitor
  speech    Run speech-analysis commands
  help      Show this help

Run without a service to open the NEXA user interface.
"@
}

if (-not $Service) {
    $Service = "ui"
}

Push-Location $ProjectRoot
try {
    $pythonArguments = switch ($Service.ToLowerInvariant()) {
        { $_ -in "ui", "nexa", "nexa-ui" } {
            @((Join-Path $ProjectRoot "nexa_ui\app.py")) + $ServiceArguments
            break
        }
        { $_ -in "eye", "eye-tracker" } {
            @("-m", "als_monitor.eye_tracker") + $ServiceArguments
            break
        }
        { $_ -in "preview", "eye-preview" } {
            @("-m", "als_monitor.eye_tracker.preview") + $ServiceArguments
            break
        }
        { $_ -in "grip", "grip-monitor" } {
            @("-m", "als_monitor.grip_monitor") + $ServiceArguments
            break
        }
        { $_ -in "shoulder", "shoulder-monitor" } {
            @("-m", "als_monitor.shoulder_monitor") + $ServiceArguments
            break
        }
        { $_ -in "speech", "speech-analysis" } {
            Write-Host "Starting NEXA speech analysis..."
            if ($ServiceArguments.Count -eq 0) {
                @("-m", "als_monitor.speech_analysis", "menu")
            } else {
                @("-m", "als_monitor.speech_analysis") + $ServiceArguments
            }
            break
        }
        { $_ -in "help", "-h", "--help" } {
            Show-LauncherHelp
            exit 0
        }
        default {
            Show-LauncherHelp
            throw "Unknown service: $Service"
        }
    }

    $exitCode = Invoke-ProjectPython -Arguments $pythonArguments
    exit $exitCode
} finally {
    Pop-Location
}
