# Phase 2 - one-time setup of the demo SMS settings.
# Run from the project folder:  .\scripts\setup-demo-sms.ps1
# Asks for the demo phone numbers and the Demo Phone access code, then writes them to
# backend\.env and worker\.env (both git-ignored). Existing lines are kept; only these keys change.
# Nothing you type is printed back. Run it again at any time to change the values.
if (-not (Test-Path backend)) { Write-Host "Run this from the project folder."; return }

$raw = Read-Host "Demo phone numbers, comma-separated (e.g. +919812345678, 9876543210)"
$list = @($raw.Split(",") | ForEach-Object { $_.Trim() -replace "[\s-]", "" } | Where-Object { $_ })
$list = @($list | ForEach-Object { if ($_ -match '^[6-9]\d{9}$') { "+91$_" } else { $_ } })
if ($list.Count -eq 0) { Write-Host "No numbers given - nothing changed."; return }
foreach ($n in $list) {
  if ($n -notmatch '^\+[1-9]\d{7,14}$') { Write-Host "Not a valid number: $n  (use +91 followed by 10 digits) - nothing changed."; return }
}
$code = Read-Host "Demo Phone access code (6-32 letters or digits)"
if ($code -notmatch '^[A-Za-z0-9]{6,32}$') { Write-Host "Use 6-32 letters or digits - nothing changed."; return }

# Local .env files, written as UTF-8 without BOM
function Set-EnvValues($file, [hashtable]$values) {
  $path = "$PWD\$file"
  $lines = @()
  if (Test-Path $path) { $lines = @(Get-Content $path | Where-Object { $line = $_; -not ($values.Keys | Where-Object { $line -like "$_=*" }) }) }
  foreach ($k in ($values.Keys | Sort-Object)) { $lines += "$k=$($values[$k])" }
  [IO.File]::WriteAllLines($path, [string[]]$lines, (New-Object Text.UTF8Encoding $false))
}
$shared = @{ SMS_DEMO_NUMBERS = ($list -join ","); PUBLIC_SITE_URL = "http://localhost:5173" }
Set-EnvValues "backend\.env" ($shared + @{ DEMO_PHONE_ACCESS_CODE = $code })
Set-EnvValues "worker\.env" $shared
Write-Host "Done: backend\.env and worker\.env updated ($($list.Count) number(s)). Restart the API to use them."
