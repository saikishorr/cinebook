# READ-ONLY: saves the current settings of every CineBook resource into infra\terraform\discovery\
# so the Terraform code can be written to match them exactly. Nothing is changed in AWS.
# Run from the project folder:  .\infra\terraform\discover.ps1
$r   = "ap-south-1"
$out = "infra\terraform\discovery"
New-Item -ItemType Directory -Force -Path $out | Out-Null
function Save($name, [scriptblock]$cmd) {
  Write-Host "  $name"
  & $cmd 2>&1 | Out-File -Encoding utf8 "$out\$name.json"
}
$vpc  = aws ec2 describe-vpcs --region $r --filters "Name=tag:Name,Values=Cinebook-vpc" --query "Vpcs[0].VpcId" --output text
$acct = aws sts get-caller-identity --query Account --output text
Write-Host "VPC $vpc, account $acct"

Save "vpc"               { aws ec2 describe-vpcs --region $r --vpc-ids $vpc }
Save "vpc-dns"           { aws ec2 describe-vpc-attribute --region $r --vpc-id $vpc --attribute enableDnsHostnames }
Save "subnets"           { aws ec2 describe-subnets --region $r --filters "Name=vpc-id,Values=$vpc" }
Save "route-tables"      { aws ec2 describe-route-tables --region $r --filters "Name=vpc-id,Values=$vpc" }
Save "igw"               { aws ec2 describe-internet-gateways --region $r --filters "Name=attachment.vpc-id,Values=$vpc" }
Save "vpc-endpoints"     { aws ec2 describe-vpc-endpoints --region $r --filters "Name=vpc-id,Values=$vpc" }
Save "security-groups"   { aws ec2 describe-security-groups --region $r --filters "Name=vpc-id,Values=$vpc" }
Save "nat-instance"      { aws ec2 describe-instances --region $r --filters "Name=tag:Name,Values=cinebook-nat" "Name=instance-state-name,Values=pending,running,stopping,stopped" }
Save "launch-template"   { aws ec2 describe-launch-template-versions --region $r --launch-template-name cinebook-api --versions '$Latest' }
Save "asg"               { aws autoscaling describe-auto-scaling-groups --region $r --auto-scaling-group-names cinebook-api-asg }
Save "alb"               { aws elbv2 describe-load-balancers --region $r --names cinebook-alb }
$alb = aws elbv2 describe-load-balancers --region $r --names cinebook-alb --query "LoadBalancers[0].LoadBalancerArn" --output text
$tg  = aws elbv2 describe-target-groups --region $r --names cinebook-api-tg --query "TargetGroups[0].TargetGroupArn" --output text
Save "alb-attributes"    { aws elbv2 describe-load-balancer-attributes --region $r --load-balancer-arn $alb }
Save "alb-listeners"     { aws elbv2 describe-listeners --region $r --load-balancer-arn $alb }
Save "target-group"      { aws elbv2 describe-target-groups --region $r --target-group-arns $tg }
Save "tg-attributes"     { aws elbv2 describe-target-group-attributes --region $r --target-group-arn $tg }
Save "rds"               { aws rds describe-db-instances --region $r --db-instance-identifier cinebook-db }
Save "rds-subnet-group"  { aws rds describe-db-subnet-groups --region $r --db-subnet-group-name cinebook-db-subnets }
Save "dynamodb"          { aws dynamodb describe-table --region $r --table-name seat-holds }
Save "dynamodb-ttl"      { aws dynamodb describe-time-to-live --region $r --table-name seat-holds }
Save "dynamodb-pitr"     { aws dynamodb describe-continuous-backups --region $r --table-name seat-holds }
$q  = aws sqs get-queue-url --region $r --queue-name booking-requests.fifo --query QueueUrl --output text
$dq = aws sqs get-queue-url --region $r --queue-name booking-requests-dlq.fifo --query QueueUrl --output text
Save "sqs-main"          { aws sqs get-queue-attributes --region $r --queue-url $q --attribute-names All }
Save "sqs-dlq"           { aws sqs get-queue-attributes --region $r --queue-url $dq --attribute-names All }
Save "ecr"               { aws ecr describe-repositories --region $r --repository-names cinebook-api }
foreach ($b in "cinebook-artifacts-$acct", "cinebook-site-$acct") {
  $s = $b -replace "-$acct", ""
  Save "$s-encryption"   { aws s3api get-bucket-encryption --bucket $b }
  Save "$s-versioning"   { aws s3api get-bucket-versioning --bucket $b }
  Save "$s-pab"          { aws s3api get-public-access-block --bucket $b }
  Save "$s-ownership"    { aws s3api get-bucket-ownership-controls --bucket $b }
  Save "$s-policy"       { aws s3api get-bucket-policy --bucket $b }
}
Save "lambda"            { aws lambda get-function-configuration --region $r --function-name cinebook-confirm-booking }
Save "lambda-esm"        { aws lambda list-event-source-mappings --region $r --function-name cinebook-confirm-booking }
Save "log-groups"        { aws logs describe-log-groups --region $r }
Save "sns-topics"        { aws sns list-topics --region $r }
Save "sns-subscriptions" { aws sns list-subscriptions --region $r }
Save "alarms"            { aws cloudwatch describe-alarms --region $r --alarm-names cinebook-dead-letter-messages }
Save "ses-identities"    { aws sesv2 list-email-identities --region $r }
foreach ($role in "cinebook-ec2-role", "cinebook-nat-role", "cinebook-worker-role") {
  Save "iam-$role"          { aws iam get-role --role-name $role }
  Save "iam-$role-attached" { aws iam list-attached-role-policies --role-name $role }
  Save "iam-$role-inline"   { aws iam list-role-policies --role-name $role }
}
Save "iam-profiles"      { aws iam list-instance-profiles --path-prefix / --query "InstanceProfiles[?starts_with(InstanceProfileName,'cinebook')]" }
Save "cloudfront-oac"    { aws cloudfront list-origin-access-controls }
Save "cloudfront-fn"     { aws cloudfront describe-function --name cinebook-spa-rewrite }
Save "ssm-parameters"    { aws ssm describe-parameters --region $r --parameter-filters "Key=Name,Option=BeginsWith,Values=/cinebook/" }
Save "ssm-values"        { aws ssm get-parameters-by-path --region $r --path /cinebook/prod --recursive --query "Parameters[?Type=='String'].[Name,Value]" }
Write-Host ""
Write-Host "Done. Files saved in $out (no passwords are included)."
