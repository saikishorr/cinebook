# Prints the version of every tool this project needs. Run in a NEW VS Code terminal.
$env:WSL_UTF8 = "1"   # makes wsl print readable text
$tools = @(
  @{ Name = "Python";        Cmd = { python --version } },
  @{ Name = "pip";           Cmd = { python -m pip --version } },
  @{ Name = "Git";           Cmd = { git --version } },
  @{ Name = "AWS CLI";       Cmd = { aws --version } },
  @{ Name = "AWS identity";  Cmd = { aws sts get-caller-identity --query Arn --output text } },
  @{ Name = "PostgreSQL";    Cmd = { psql --version } },
  @{ Name = "Node.js";       Cmd = { node --version } },
  @{ Name = "npm";           Cmd = { npm --version } },
  @{ Name = "WSL";           Cmd = { wsl --version | Select-Object -First 1 } },
  @{ Name = "Docker";        Cmd = { docker --version } },
  @{ Name = "Docker engine"; Cmd = { docker info --format "{{.ServerVersion}}" } },
  @{ Name = "Terraform";     Cmd = { terraform -version | Select-Object -First 1 } }
)
foreach ($t in $tools) {
  try   { $v = (& $t.Cmd 2>&1 | Out-String).Trim(); if ($LASTEXITCODE -ne 0) { throw $v } ; Write-Host ("OK      {0,-14} {1}" -f $t.Name, $v) }
  catch { Write-Host ("MISSING {0,-14} see the section for this tool" -f $t.Name) -ForegroundColor Yellow }
}
