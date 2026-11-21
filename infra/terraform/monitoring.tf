resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "cinebook"
  dashboard_body = file("${path.module}/../monitoring/dashboard.json")
}

resource "aws_sns_topic" "alerts" {
  name = "cinebook-alerts"
}
# The email subscription is created once with the CLI and confirmed by clicking the
# link AWS sends; Terraform cannot confirm email subscriptions, so it is not managed here.

resource "aws_cloudwatch_metric_alarm" "dead_letters" {
  alarm_name          = "cinebook-dead-letter-messages"
  alarm_description   = "A booking message failed 3 times and moved to the dead-letter queue"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}
