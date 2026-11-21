# Prints the version of every tool this project needs. Run in a NEW VS Code terminal.
$tools = @(
  @{ Name = "Python";        Cmd = { python --version } },
  @{ Name = "pip";           Cmd = { python -m pip --version } },
  @{ Name = "Git";           Cmd = { git --version } },
  @{ Name = "PostgreSQL";    Cmd = { psql --version } },
  @{ Name = "Node.js";       Cmd = { node --version } },
  @{ Name = "npm";           Cmd = { npm --version } }
)
foreach ($t in $tools) {
  try   { $v = (& $t.Cmd 2>&1 | Out-String).Trim(); if ($LASTEXITCODE -ne 0) { throw $v } ; Write-Host ("OK      {0,-14} {1}" -f $t.Name, $v) }
  catch { Write-Host ("MISSING {0,-14} see the section for this tool" -f $t.Name) -ForegroundColor Yellow }
}
