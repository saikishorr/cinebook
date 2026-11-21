# Import the movies now playing in Pune from TMDB and schedule shows for them.
# Needs TMDB_API_KEY in backend\.env. Add -DryRun to only preview the list.
param([switch]$DryRun, [int]$Limit = 40)
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$arguments = @((Join-Path $root "scripts\import_tmdb.py"), "--limit", $Limit)
if ($DryRun) { $arguments += "--dry-run" }
& $python @arguments
