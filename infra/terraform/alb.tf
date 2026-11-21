resource "aws_lb" "api" {
  count              = var.running ? 1 : 0 # a load balancer cannot be stopped, so it is deleted while paused
  name               = "cinebook-alb"
  internal           = false
  load_balancer_type = "application"
  ip_address_type    = "ipv4"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [aws_subnet.this["public-1a"].id, aws_subnet.this["public-1b"].id]
}

resource "aws_lb_target_group" "api" {
  name                 = "cinebook-api-tg"
  port                 = 8000
  protocol             = "HTTP"
  vpc_id               = aws_vpc.main.id
  target_type          = "instance"
  deregistration_delay = 30

  health_check {
    enabled             = true
    path                = "/health"
    protocol            = "HTTP"
    port                = "traffic-port"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  count             = var.running ? 1 : 0
  load_balancer_arn = aws_lb.api[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# The load balancer and listener were adopted before the "running" switch existed.
# These blocks tell Terraform they are now the first (and only) instance of each, so nothing is recreated.
moved {
  from = aws_lb.api
  to   = aws_lb.api[0]
}

moved {
  from = aws_lb_listener.http
  to   = aws_lb_listener.http[0]
}
