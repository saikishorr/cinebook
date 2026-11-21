$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup instructions in START-HERE.md first.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'backend\.env'))) { throw 'Create backend\.env first.' }
# Escape apostrophes for literal PowerShell paths; spaces are kept inside quotes.
$backendPath = (Join-Path $projectRoot 'backend').Replace("'", "''")
$frontendPath = (Join-Path $projectRoot 'frontend').Replace("'", "''")
$quotedPython = $pythonPath.Replace("'", "''")
$apiCommand = "Set-Location -LiteralPath '$backendPath'; & '$quotedPython' -m uvicorn app.main:app --reload --port 8000"
$webCommand = "Set-Location -LiteralPath '$frontendPath'; npm run dev"
$apiEncoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($apiCommand))
$webEncoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($webCommand))
# These visible windows are the requested interactive API and frontend terminals.
Start-Process powershell.exe -ArgumentList @('-NoExit', '-EncodedCommand', $apiEncoded)
Start-Process powershell.exe -ArgumentList @('-NoExit', '-EncodedCommand', $webEncoded)
