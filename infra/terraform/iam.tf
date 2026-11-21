# ---------------------------------------------------------------- Trust policies
locals {
  ec2_trust = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  lambda_trust = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  arn_prefix = "${var.region}:${local.account_id}"
}

# ---------------------------------------------------------------- API servers
resource "aws_iam_role" "ec2" {
  name               = "cinebook-ec2-role"
  description        = "CineBook EC2 servers"
  assume_role_policy = local.ec2_trust
}

resource "aws_iam_instance_profile" "ec2" {
  name = "cinebook-ec2-role"
  role = aws_iam_role.ec2.name
}

resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ec2_ecr" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy" "ec2_read_config" {
  name = "cinebook-read-config"
  role = aws_iam_role.ec2.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadDeployFiles"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.artifacts.arn}/db/*"
      },
      {
        Sid      = "ReadAppConfig"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = "arn:aws:ssm:${local.arn_prefix}:parameter/cinebook/prod/*"
      },
    ]
  })
}

resource "aws_iam_role_policy" "ec2_api_access" {
  name = "cinebook-api-access"
  role = aws_iam_role.ec2.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SeatHolds"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:ConditionCheckItem"]
        Resource = [aws_dynamodb_table.holds.arn, "${aws_dynamodb_table.holds.arn}/index/*"]
      },
      {
        Sid      = "BookingQueue"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.bookings.arn
      },
      {
        Sid      = "ContainerLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = "${aws_cloudwatch_log_group.api.arn}:*"
      },
    ]
  })
}

# ---------------------------------------------------------------- NAT instance
resource "aws_iam_role" "nat" {
  name               = "cinebook-nat-role"
  description        = "CineBook NAT instance"
  assume_role_policy = local.ec2_trust
}

resource "aws_iam_instance_profile" "nat" {
  name = "cinebook-nat-role"
  role = aws_iam_role.nat.name
}

resource "aws_iam_role_policy_attachment" "nat_ssm" {
  role       = aws_iam_role.nat.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# ---------------------------------------------------------------- Booking worker Lambda
resource "aws_iam_role" "worker" {
  name               = "cinebook-worker-role"
  description        = "CineBook booking confirmation Lambda"
  assume_role_policy = local.lambda_trust
}

resource "aws_iam_role_policy_attachment" "worker_vpc" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "worker_access" {
  name = "cinebook-worker-access"
  role = aws_iam_role.worker.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadBookingQueue"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
        Resource = aws_sqs_queue.bookings.arn
      },
      {
        Sid      = "ReleaseSeatHolds"
        Effect   = "Allow"
        Action   = ["dynamodb:DeleteItem"]
        Resource = aws_dynamodb_table.holds.arn
      },
      {
        Sid      = "SendConfirmationEmail"
        Effect   = "Allow"
        Action   = ["ses:SendEmail"]
        Resource = "arn:aws:ses:${local.arn_prefix}:identity/*"
      },
      {
        Sid      = "ReadDatabaseSettings"
        Effect   = "Allow"
        Action   = ["ssm:GetParameters", "ssm:GetParameter"]
        Resource = "arn:aws:ssm:${local.arn_prefix}:parameter/cinebook/prod/db/*"
      },
    ]
  })
}
