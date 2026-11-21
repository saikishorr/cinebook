#!/bin/bash
# Runs one or more SQL files against the RDS database.
# It runs ON an API server (Session Manager), because only servers inside the VPC can reach RDS.
# The SQL files are read from the artifacts bucket: s3://cinebook-artifacts-<account>/db/migrations/
# Usage:  bash /tmp/apply.sh 002_sms_chat_links.sql 003_chat_messages.sql add_upcoming_shows.sql
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: apply-on-rds.sh <sql file name> [more files...]"; exit 1; }
R=ap-south-1
ACCT=$(aws sts get-caller-identity --query Account --output text)

command -v psql >/dev/null || sudo dnf install -y -q postgresql16

p() { aws ssm get-parameter --region "$R" --name "$1" --with-decryption --query Parameter.Value --output text; }
export PGPASSWORD="$(p /cinebook/prod/db/master-password)"     # never printed
CONN="host=$(p /cinebook/prod/db/host) user=$(p /cinebook/prod/db/master-username) dbname=moviebooking sslmode=require"

for FILE in "$@"; do
  aws s3 cp --region "$R" --quiet "s3://cinebook-artifacts-$ACCT/db/migrations/$FILE" "/tmp/$FILE"
  echo "--- applying $FILE ---"
  psql "$CONN" -v ON_ERROR_STOP=1 -f "/tmp/$FILE"
  rm -f "/tmp/$FILE"
done

echo "--- check: tables ---"
psql "$CONN" -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY 1;"
echo "--- check: upcoming shows ---"
psql "$CONN" -c "SELECT count(*) AS upcoming_shows FROM shows WHERE start_time > now() AND status = 'SCHEDULED';"
unset PGPASSWORD
echo "--- done ---"
