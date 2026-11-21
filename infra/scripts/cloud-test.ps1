# CineBook - test the cloud system from your own computer.
# Run from the project folder:
#   .\infra\scripts\cloud-test.ps1          open the load balancer to YOUR internet address only, check the
#                                           cloud API, then run the website on this computer against it
#   .\infra\scripts\cloud-test.ps1 -Close   remove that temporary access again
#
# Why it is needed: the load balancer accepts visitors from CloudFront only. Until CloudFront is
# available, this script adds one temporary firewall rule for your own address so you can test.
param([switch]$Close)
$r = "ap-south-1"
$label = "temporary-test"

$sg = aws ec2 describe-security-groups --region $r --filters "Name=group-name,Values=cinebook-alb-sg" --query "SecurityGroups[0].GroupId" --output text
if (-not $sg -or $sg -eq "None") { Write-Host "The load balancer's security group (cinebook-alb-sg) was not found."; return }

function Remove-TemporaryRules {
  $ids = aws ec2 describe-security-group-rules --region $r --filters "Name=group-id,Values=$sg" --query "SecurityGroupRules[?Description=='$label'].SecurityGroupRuleId" --output text
  if ($ids -and $ids -ne "None") {
    aws ec2 revoke-security-group-ingress --region $r --group-id $sg --security-group-rule-ids ($ids -split "\s+") --query Return --output text | Out-Null
    return $true
  }
  return $false
}

if ($Close) {
  if (Remove-TemporaryRules) { Write-Host "Temporary access removed. The load balancer accepts CloudFront only again." }
  else { Write-Host "No temporary access rule was found - nothing to remove." }
  return
}

Write-Host "1/3  Opening the load balancer to your internet address only"
$alb = aws elbv2 describe-load-balancers --region $r --names cinebook-alb --query "LoadBalancers[0].DNSName" --output text 2>$null
if (-not $alb -or $alb -eq "None") { Write-Host "     No load balancer found - the system is paused. Run .\infra\scripts\resume.ps1 first."; return }
try { $ip = ([string](Invoke-RestMethod -Uri "https://checkip.amazonaws.com" -TimeoutSec 15)).Trim() } catch { $ip = "" }
if ($ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { Write-Host "     Could not find your internet address. Check your connection and run the script again."; return }
Remove-TemporaryRules | Out-Null          # your address changes from time to time: remove an older rule first
aws ec2 authorize-security-group-ingress --region $r --group-id $sg --ip-permissions "IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges=[{CidrIp=$ip/32,Description=$label}]" --query Return --output text | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "     The firewall rule could not be added - read the message above."; return }
Write-Host "     rule added for $ip (HTTP, port 80)"

Write-Host "2/3  Checking the cloud API"
$api = "http://$alb/api"
$healthy = $false
foreach ($i in 1..8) {
  try { $h = Invoke-RestMethod -Uri "$api/health" -TimeoutSec 10; $healthy = $true; break } catch { Start-Sleep -Seconds 5 }
}
if (-not $healthy) {
  Write-Host "     The API did not answer at $api/health"
  Write-Host "     Check the server with:  python infra\scripts\server-log.py"
  return
}
Write-Host "     health:  status $($h.status), database $($h.database)"
try {
  $movies = Invoke-RestMethod -Uri "$api/movies" -TimeoutSec 15
  Write-Host "     movies:  $(@($movies).Count) found"
  Invoke-RestMethod -Uri "$api/help" -TimeoutSec 15 | Out-Null
  Write-Host "     help:    OK"
} catch {
  Write-Host "     A check failed: $($_.Exception.Message)"
  return
}

Write-Host "3/3  Starting the website on this computer, connected to the CLOUD API"
if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) {
  Write-Host "     Port 5173 is already in use (a website from an earlier session is still running)."
  Write-Host "     Stop it with the next line, then run this script again:"
  Write-Host "       Get-NetTCPConnection -LocalPort 5173 -State Listen | ForEach-Object { Stop-Process -Id `$_.OwningProcess -Force }"
  return
}
Write-Host "     Open http://localhost:5173 in your browser. Press Ctrl+C here to stop the website."
Write-Host ""
$env:VITE_API_URL = $api              # for this run only; frontend\.env is not changed
Push-Location frontend
try { npm run dev -- --strictPort }
finally {
  Pop-Location
  Remove-Item Env:VITE_API_URL -ErrorAction SilentlyContinue
  Write-Host ""
  Write-Host "Website stopped. When you have finished testing, remove the temporary access:"
  Write-Host "  .\infra\scripts\cloud-test.ps1 -Close"
}
