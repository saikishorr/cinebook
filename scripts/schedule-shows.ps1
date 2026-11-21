param([switch]$Rebuild)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$scheduleArgs = @((Join-Path $PSScriptRoot 'schedule_shows.py'))
if ($Rebuild) { $scheduleArgs += '--rebuild' }
& $pythonPath @scheduleArgs
if ($LASTEXITCODE -ne 0) { throw 'Weekly demo scheduling failed. Check the message above.' }
