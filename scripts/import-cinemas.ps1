param([switch]$Offline, [switch]$DryRun, [switch]$Relayout, [ValidateSet('curated','osm')][string]$Source = 'curated')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$importArgs = @((Join-Path $PSScriptRoot 'import_cinemas.py'))
$importArgs += @('--source', $Source)
if ($Offline) { $importArgs += '--offline' }
if ($DryRun) { $importArgs += '--dry-run' }
if ($Relayout) { $importArgs += '--relayout' }
& $pythonPath @importArgs
if ($LASTEXITCODE -ne 0) { throw 'Cinema import failed. Check the curated/layout JSON files and database settings.' }
