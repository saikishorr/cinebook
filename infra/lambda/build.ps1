# Build the booking worker Lambda package -> worker\lambda.zip
# Run from the project folder:  .\infra\lambda\build.ps1
$build = "worker\build"
if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Path $build | Out-Null

# Linux ARM (Graviton) wheels for Python 3.13, the Lambda runtime we use.
# boto3 is not included: the Lambda Python runtime already provides it.
python -m pip install --quiet "psycopg[binary]" tzdata `
  --platform manylinux2014_aarch64 --only-binary=:all: --python-version 3.13 --implementation cp `
  --target $build
if ($LASTEXITCODE -ne 0) { Write-Host "pip failed - see the error above"; return }

Copy-Item worker\confirm_booking.py, worker\demo_sms.py, worker\lambda_entry.py $build

# Zip with Python: Windows PowerShell 5.1's Compress-Archive can write backslashes
# into zip paths, which Lambda (Linux) cannot import.
if (Test-Path worker\lambda.zip) { Remove-Item worker\lambda.zip }
python -c "import shutil; shutil.make_archive('worker/lambda', 'zip', 'worker/build')"
Get-Item worker\lambda.zip | Select-Object Name, @{n='SizeMB';e={[math]::Round($_.Length/1MB,1)}}
