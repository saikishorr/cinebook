# Values looked up from AWS and shared by the other files.
data "aws_caller_identity" "current" {}

# AWS-maintained list of CloudFront's addresses (used by the load balancer's security group).
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# Latest Amazon Linux 2023 images (used only when a server is created from scratch).
data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

data "aws_ssm_parameter" "al2023_x86_64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  worker_zip = "${path.module}/../../worker/lambda.zip"
}
