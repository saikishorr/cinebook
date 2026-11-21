param([string]$Username = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$adminArgs = @((Join-Path $PSScriptRoot 'create_admin.py'))
if ($Username) { $adminArgs += @('--username', $Username) }
& $pythonPath @adminArgs
if ($LASTEXITCODE -ne 0) { throw 'Admin creation failed. Check the message above; passwords are never logged.' }
