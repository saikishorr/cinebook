output "alb_dns_name" {
  description = "Load balancer address (reachable from CloudFront only; empty while paused)"
  value       = one(aws_lb.api[*].dns_name)
}

output "database_endpoint" {
  value = aws_db_instance.main.address
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "booking_queue_url" {
  value = aws_sqs_queue.bookings.url
}

output "nat_public_ip" {
  description = "Changes each time the NAT instance is started"
  value       = aws_instance.nat.public_ip
}
