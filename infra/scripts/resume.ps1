# CineBook - resume after pause.ps1.
# Run from the project folder:  .\infra\scripts\resume.ps1
# 1) AWS CLI: database started first (the API's health check needs it).
# 2) Terraform (running = true): NAT started, load balancer created, API server launched, worker trigger on.
# 3) Waits until the load balancer reports the new API server healthy.
$r = "ap-south-1"

# Find Terraform even in a terminal that was opened before it was added to PATH.
if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
  $tfExe = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter terraform.exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($tfExe) { $env:Path += ";" + $tfExe.DirectoryName }
}
if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
  Write-Host "Terraform was not found. Install it (winget install Hashicorp.Terraform) or reopen VS Code, then run this script again."
  return
}

Write-Host "1/2  Database -> starting"
$db = aws rds describe-db-instances --region $r --db-instance-identifier cinebook-db --query "DBInstances[0].DBInstanceStatus" --output text
if ($db -eq "stopped") { aws rds start-db-instance --region $r --db-instance-identifier cinebook-db --query DBInstance.DBInstanceStatus --output text }
Write-Host "     waiting until the database is available (usually 3-8 minutes)..."
aws rds wait db-instance-available --region $r --db-instance-identifier cinebook-db

Write-Host "2/2  Terraform: running = true  (review the plan, then type yes)"
Set-Content -Encoding ascii infra\terraform\running.auto.tfvars "running = true"
Push-Location infra\terraform
terraform apply
$result = $LASTEXITCODE
$alb = terraform output -raw alb_dns_name 2>$null
Pop-Location
if ($result -ne 0) { Write-Host "Terraform did not complete - read the message above, fix it, then run this script again."; return }

Write-Host ""
Write-Host "Resumed. Load balancer: http://$alb"
Write-Host "A fresh API server is starting. Waiting until the load balancer reports it healthy (usually 6-9 minutes)..."
$tg = aws elbv2 describe-target-groups --region $r --names cinebook-api-tg --query "TargetGroups[0].TargetGroupArn" --output text
$state = ""
foreach ($i in 1..40) {
  Start-Sleep -Seconds 20
  $state = aws elbv2 describe-target-health --region $r --target-group-arn $tg --query "TargetHealthDescriptions[0].TargetHealth.State" --output text
  Write-Host ("     {0,3}s  {1}" -f ($i * 20), $state)
  if ($state -eq "healthy") { break }
}
if ($state -eq "healthy") {
  Write-Host "The API server is healthy. The system is ready."
} else {
  Write-Host "The API server is not healthy yet. See why with:"
  Write-Host "  python infra\scripts\server-log.py"
}
