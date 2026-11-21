param([switch]$Reset)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'backend\.env'))) {
    throw 'Create backend\.env from backend\.env.example and set DATABASE_URL and the Local mode values first.'
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install backend\requirements-dev.txt first (see START-HERE.md).'
}
$setupArgs = @((Join-Path $PSScriptRoot 'setup_local.py'))
if ($Reset) {
    $answer = Read-Host 'This deletes all CineBook data in the configured database. Type RESET to continue'
    if ($answer -cne 'RESET') { Write-Host 'Reset cancelled.'; return }
    $setupArgs += '--reset'
}
& $pythonPath @setupArgs
if ($LASTEXITCODE -ne 0) { throw 'Local database setup failed. See the message above.' }
