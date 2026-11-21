# Application settings read by the API servers at start-up (Parameter Store).
# Secrets (the database password, the Demo Phone access code) are deliberately not managed here.
locals {
  app_settings = {
    API_PREFIX        = "/api"
    APP_TIMEZONE      = "Asia/Kolkata"
    AWS_REGION        = var.region
    BOOKING_QUEUE_URL = aws_sqs_queue.bookings.url
    CORS_ORIGINS      = "*"
    DYNAMODB_TABLE    = aws_dynamodb_table.holds.name
    HOLD_SECONDS      = "300"
    # Phase 2: demo SMS with a chat link (shared with the booking worker below)
    PUBLIC_SITE_URL  = local.sms_settings.PUBLIC_SITE_URL
    SMS_DEMO_NUMBERS = local.sms_settings.SMS_DEMO_NUMBERS
    # Phase 3: chat assistant (the secret GEMINI_API_KEY is stored separately, see below)
    CHAT_PROVIDER = var.chat_provider
    CHAT_MODEL_ID = var.chat_model_id
  }
  sms_settings = {
    PUBLIC_SITE_URL  = var.public_site_url
    SMS_DEMO_NUMBERS = join(",", var.sms_demo_numbers)
  }
  # DEMO_PHONE_ACCESS_CODE (SecureString, same folder) is created by infra\scripts\setup-demo-sms.ps1, not here.
  # GEMINI_API_KEY (SecureString, same folder) is created by infra\scripts\push-chat-key.py, not here.
}

resource "aws_ssm_parameter" "app" {
  for_each = local.app_settings
  name     = "/cinebook/prod/app/${each.key}"
  type     = "String"
  value    = each.value
}

resource "aws_ssm_parameter" "db_host" {
  name        = "/cinebook/prod/db/host"
  description = "CineBook RDS endpoint"
  type        = "String"
  value       = aws_db_instance.main.address
}

resource "aws_ssm_parameter" "db_username" {
  name        = "/cinebook/prod/db/master-username"
  description = "CineBook RDS master user name"
  type        = "String"
  value       = aws_db_instance.main.username
}

resource "aws_ssm_parameter" "image_tag" {
  name  = "/cinebook/prod/deploy/image-tag"
  type  = "String"
  value = var.image_tag
}
