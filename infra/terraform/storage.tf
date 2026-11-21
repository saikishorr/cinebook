# ---------------------------------------------------------------- PostgreSQL (RDS)
resource "aws_db_subnet_group" "main" {
  name        = "cinebook-db-subnets"
  description = "CineBook private database subnets (2 AZs)"
  subnet_ids  = [aws_subnet.this["db-1a"].id, aws_subnet.this["db-1b"].id]
}

resource "aws_db_instance" "main" {
  identifier        = "cinebook-db"
  engine            = "postgres"
  engine_version    = "18.6"
  instance_class    = "db.t4g.micro"
  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true
  db_name           = "moviebooking"
  username          = "cinebook_admin"
  # The master password lives only in Parameter Store (/cinebook/prod/db/master-password).
  # It is set when the database is first created and is not managed here.

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period    = 1
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  deletion_protection        = true # switch off deliberately before a final destroy
  skip_final_snapshot        = true

  tags = { Name = "cinebook-db", Project = "cinebook" }

  lifecycle {
    # AWS applies minor upgrades itself (18.6 -> 18.7); do not try to undo them.
    ignore_changes = [password, engine_version]
  }
}

# ---------------------------------------------------------------- Seat holds (DynamoDB)
resource "aws_dynamodb_table" "holds" {
  name         = "seat-holds"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# ---------------------------------------------------------------- Booking queues (SQS FIFO)
resource "aws_sqs_queue" "dlq" {
  name                        = "booking-requests-dlq.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 30
  message_retention_seconds   = 345600 # 4 days
  max_message_size            = 1048576
}

resource "aws_sqs_queue" "bookings" {
  name                        = "booking-requests.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  visibility_timeout_seconds  = 60    # longer than the worker's 30-second timeout
  message_retention_seconds   = 86400 # 1 day
  max_message_size            = 1048576
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

# ---------------------------------------------------------------- Container images (ECR)
resource "aws_ecr_repository" "api" {
  name                 = "cinebook-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true # lets "terraform destroy" remove the repository with its images

  image_scanning_configuration {
    scan_on_push = true
  }
}

# ---------------------------------------------------------------- S3 buckets
resource "aws_s3_bucket" "artifacts" {
  bucket        = "cinebook-artifacts-${local.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "site" {
  bucket        = "cinebook-site-${local.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------- Email sender (SES)
resource "aws_sesv2_email_identity" "sender" {
  email_identity = var.ses_sender_email
}
