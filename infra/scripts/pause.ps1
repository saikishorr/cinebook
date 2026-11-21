# CineBook - pause everything that is charged by the hour.
# Run from the project folder:  .\infra\scripts\pause.ps1
# 1) Terraform (running = false): worker trigger off, API servers -> 0, load balancer deleted, NAT stopped.
# 2) AWS CLI: database stopped (Terraform cannot stop or start RDS).
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

Write-Host "1/2  Terraform: running = false  (review the plan, then type yes)"
Set-Content -Encoding ascii infra\terraform\running.auto.tfvars "running = false"
Push-Location infra\terraform
terraform apply
$result = $LASTEXITCODE
Pop-Location
if ($result -ne 0) {
  Set-Content -Encoding ascii infra\terraform\running.auto.tfvars "running = true"
  Write-Host "Terraform did not complete (or you answered no). Nothing else was changed; the database is still running."
  return
}

Write-Host "2/2  Database -> stopped"
$db = aws rds describe-db-instances --region $r --db-instance-identifier cinebook-db --query "DBInstances[0].DBInstanceStatus" --output text
if ($db -eq "available") { aws rds stop-db-instance --region $r --db-instance-identifier cinebook-db --query DBInstance.DBInstanceStatus --output text }
else { Write-Host "     database is '$db' - left as it is" }

Write-Host ""
Write-Host "Paused. To continue later run:  .\infra\scripts\resume.ps1"
Write-Host "Reminder: AWS starts a stopped database again after 7 days - run pause.ps1 again if your break is longer."
