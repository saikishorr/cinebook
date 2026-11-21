#!/bin/bash
# CineBook API server start-up script (runs once, on first boot, as root)
set -euo pipefail          # stop on any error; no "set -x", so secrets never appear in logs

# Copy everything this script prints to the server's console log, so a failed start can be read
# from your computer:  python infra\scripts\server-log.py
exec > >(tee -a /var/log/cinebook-start.log | logger -t cinebook-start -s 2>/dev/console) 2>&1
trap 'echo "CINEBOOK START FAILED at line $LINENO"' ERR
echo "CINEBOOK START begin"

REGION=ap-south-1
export AWS_RETRY_MODE=standard AWS_MAX_ATTEMPTS=8      # AWS CLI: retry while the network settles

# retry <attempts> <seconds between attempts> <command...>
retry() {
  local attempts=$1 wait=$2 i
  shift 2
  for i in $(seq 1 "$attempts"); do
    "$@" && return 0
    echo "attempt $i of $attempts failed: $1 ...; waiting ${wait}s"
    sleep "$wait"
  done
  return 1
}

# 1. Docker. After a resume the NAT instance may still be starting, so the internet
#    can be unreachable for a minute or two: keep trying for up to 5 minutes.
echo "step 1: install Docker"
retry 30 10 dnf install -y -q docker
systemctl enable --now docker

# 2. Who am I?
echo "step 2: identify this server"
TOKEN=$(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
IID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
ACCT=$(aws sts get-caller-identity --query Account --output text)

# 3. Settings file from Parameter Store (root-only). --with-decryption also reads the encrypted settings.
echo "step 3: read settings"
p() { aws ssm get-parameter --region "$REGION" --name "$1" --with-decryption --query Parameter.Value --output text; }
install -d -m 700 /etc/cinebook
ENV=/etc/cinebook/api.env
aws ssm get-parameters-by-path --region "$REGION" --path /cinebook/prod/app --with-decryption \
  --query "Parameters[].[Name,Value]" --output text \
  | awk -F'\t' '{ n = $1; sub(".*/", "", n); print n "=" $2 }' > "$ENV"
echo "DATABASE_URL=postgresql://$(p /cinebook/prod/db/master-username):$(p /cinebook/prod/db/master-password)@$(p /cinebook/prod/db/host):5432/moviebooking?sslmode=require" >> "$ENV"
chmod 600 "$ENV"
echo "settings read: $(wc -l < "$ENV") lines"

# 4. Pull and run the image
TAG=$(p /cinebook/prod/deploy/image-tag)
REG="$ACCT.dkr.ecr.$REGION.amazonaws.com"
echo "step 4: pull and run cinebook-api:$TAG"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REG"
retry 5 10 docker pull -q "$REG/cinebook-api:$TAG"
docker run -d --name cinebook-api --restart always -p 8000:8000 --env-file "$ENV" \
  --log-driver awslogs --log-opt awslogs-region="$REGION" \
  --log-opt awslogs-group=/cinebook/api --log-opt awslogs-stream="$IID" \
  "$REG/cinebook-api:$TAG" \
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips '*'
# ^ 1 worker: a t3.micro has 1 GB of memory, and two workers ran it out of memory

# 5. Confirm the API answers before declaring success.
echo "step 5: wait for the API"
if retry 24 5 curl -fsS -o /dev/null http://localhost:8000/health; then
  echo "CINEBOOK START OK"
else
  echo "API did not become healthy; container status and last log lines:"
  docker ps -a --filter name=cinebook-api --format '{{.Status}}'
  docker logs --tail 40 cinebook-api 2>&1 | sed 's/postgresql:\/\/[^@]*@/postgresql:\/\/***@/g'
  echo "CINEBOOK START FAILED (API not healthy)"
  exit 1
fi
