# ---------------------------------------------------------------- NAT instance
resource "aws_instance" "nat" {
  ami                         = data.aws_ssm_parameter.al2023_arm64.insecure_value
  instance_type               = "t4g.micro"
  subnet_id                   = aws_subnet.this["public-1b"].id
  vpc_security_group_ids      = [aws_security_group.nat.id]
  iam_instance_profile        = aws_iam_instance_profile.nat.name
  associate_public_ip_address = true
  source_dest_check           = false # a NAT forwards traffic that is not addressed to itself
  user_data                   = file("${path.module}/../nat/user-data.sh")

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = { Name = "cinebook-nat", Project = "cinebook" }

  lifecycle {
    # Keep the running server when a newer Amazon Linux image is published.
    # associate_public_ip_address reads as false while the NAT is stopped (a stopped
    # instance has no public IP); without ignoring it, every plan made while paused
    # would wrongly replace the NAT.
    ignore_changes = [ami, user_data, associate_public_ip_address]
  }
}

# Keeps the NAT running or stopped according to the "running" switch.
resource "aws_ec2_instance_state" "nat" {
  instance_id = aws_instance.nat.id
  state       = var.running ? "running" : "stopped"
}

# ---------------------------------------------------------------- API servers
resource "aws_launch_template" "api" {
  name                   = "cinebook-api"
  image_id               = data.aws_ssm_parameter.al2023_x86_64.insecure_value
  instance_type          = "t3.micro"
  vpc_security_group_ids = [aws_security_group.app.id]
  user_data              = base64encode(file("${path.module}/../ec2/api-user-data.sh"))
  update_default_version = true

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2.name
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2 # lets code inside Docker reach the role's credentials
  }

  credit_specification {
    cpu_credits = "standard" # never billed extra for CPU
  }

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "cinebook-api", Project = "cinebook" }
  }

  lifecycle {
    ignore_changes = [image_id] # new images are adopted deliberately, not on every plan
  }
}

resource "aws_autoscaling_group" "api" {
  name                      = "cinebook-api-asg"
  min_size                  = var.running ? 1 : 0
  max_size                  = 2
  desired_capacity          = var.running ? 1 : 0
  vpc_zone_identifier       = local.app_subnet_ids
  health_check_type         = "ELB"
  # Time a new server gets to install Docker, pull the image and start before the load balancer's
  # verdict counts. Too short and a slow-starting server is replaced before it finishes, forever.
  health_check_grace_period = 900

  launch_template {
    id      = aws_launch_template.api.id
    version = "$Latest"
  }

  traffic_source {
    identifier = aws_lb_target_group.api.arn
    type       = "elbv2"
  }

  tag {
    key                 = "Project"
    value               = "cinebook"
    propagate_at_launch = true
  }

  # New servers need the NAT (running, with its route) to install Docker and pull the image.
  depends_on = [aws_route.app_nat, aws_ec2_instance_state.nat]
}
