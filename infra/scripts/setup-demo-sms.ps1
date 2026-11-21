# Phase 2, Step 2.1 - one-time setup of the demo SMS settings.
# Run from the project folder:  .\infra\scripts\setup-demo-sms.ps1
# Asks for the demo phone numbers and the Demo Phone access code, then writes:
#   1) infra\terraform\demo.auto.tfvars          (git-ignored; numbers for Terraform)
#   2) backend\.env and worker\.env               (local settings for testing on this computer)
#   3) Parameter Store /cinebook/prod/app/DEMO_PHONE_ACCESS_CODE (SecureString; for the cloud API)
# Nothing you type is printed back. Run it again at any time to change the values.
$r = "ap-south-1"
if (-not (Test-Path infra\terraform)) { Write-Host "Run this from the project folder."; return }

$raw = Read-Host "Demo phone numbers, comma-separated (e.g. +919812345678, 9876543210)"
$list = @($raw.Split(",") | ForEach-Object { $_.Trim() -replace "[\s-]", "" } | Where-Object { $_ })
$list = @($list | ForEach-Object { if ($_ -match '^[6-9]\d{9}$') { "+91$_" } else { $_ } })
if ($list.Count -eq 0) { Write-Host "No numbers given - nothing changed."; return }
foreach ($n in $list) {
  if ($n -notmatch '^\+[1-9]\d{7,14}$') { Write-Host "Not a valid number: $n  (use +91 followed by 10 digits) - nothing changed."; return }
}
$code = Read-Host "Demo Phone access code (6-32 letters or digits)"
if ($code -notmatch '^[A-Za-z0-9]{6,32}$') { Write-Host "Use 6-32 letters or digits - nothing changed."; return }

# 1) Terraform values (git-ignored file)
$quoted = ($list | ForEach-Object { '"' + $_ + '"' }) -join ", "
[IO.File]::WriteAllLines("$PWD\infra\terraform\demo.auto.tfvars", @("sms_demo_numbers = [$quoted]"))
Write-Host "1/3  infra\terraform\demo.auto.tfvars written ($($list.Count) number(s))"

# 2) Local .env files - existing lines are kept, these keys are replaced (UTF-8 without BOM)
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
Write-Host "2/3  backend\.env and worker\.env updated"

# 3) Access code for the cloud API (encrypted)
aws ssm put-parameter --region $r --name /cinebook/prod/app/DEMO_PHONE_ACCESS_CODE --type SecureString --value $code --overwrite --query Version --output text | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "3/3  Parameter Store update FAILED - check the message above."; return }
Write-Host "3/3  Parameter Store: /cinebook/prod/app/DEMO_PHONE_ACCESS_CODE saved (SecureString)"
Write-Host ""
Write-Host "Done. Next: review the Terraform plan (see the Step 2.1 instructions)."
