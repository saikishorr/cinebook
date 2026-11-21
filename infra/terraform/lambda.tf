# ---------------------------------------------------------------- Log groups (7-day retention)
resource "aws_cloudwatch_log_group" "api" {
  name              = "/cinebook/api"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/cinebook-confirm-booking"
  retention_in_days = 7
}

# ---------------------------------------------------------------- Booking confirmation worker
# Build the package first with .\infra\lambda\build.ps1 (creates worker\lambda.zip).
resource "aws_lambda_function" "worker" {
  function_name    = "cinebook-confirm-booking"
  role             = aws_iam_role.worker.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "lambda_entry.lambda_handler"
  filename         = local.worker_zip
  source_code_hash = filebase64sha256(local.worker_zip)
  timeout          = 30
  memory_size      = 256

  environment {
    variables = merge({
      DYNAMODB_TABLE   = aws_dynamodb_table.holds.name
      SES_SENDER_EMAIL = var.ses_sender_email
      APP_TIMEZONE     = "Asia/Kolkata"
      DB_PARAM_PREFIX  = "/cinebook/prod/db"
    }, local.sms_settings)
  }

  vpc_config {
    subnet_ids         = local.app_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  depends_on = [aws_cloudwatch_log_group.worker, aws_iam_role_policy_attachment.worker_vpc]
}

resource "aws_lambda_event_source_mapping" "bookings" {
  event_source_arn        = aws_sqs_queue.bookings.arn
  function_name           = aws_lambda_function.worker.arn
  batch_size              = 5
  function_response_types = ["ReportBatchItemFailures"]
  enabled                 = var.running # no queue polling while paused
}
