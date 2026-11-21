# Security groups: each tier accepts traffic only from the tier in front of it.
# (Descriptions cannot be changed without replacing a group, so they match the originals exactly.)

resource "aws_security_group" "alb" {
  name        = "cinebook-alb-sg"
  description = "Load balancer - HTTP from CloudFront only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "cloudfront"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cinebook-alb-sg" }
}

resource "aws_security_group" "app" {
  name        = "cinebook-app-sg"
  description = "API servers - port 8000 from the load balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "from-alb"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cinebook-app-sg" }
}

resource "aws_security_group" "lambda" {
  name        = "cinebook-lambda-sg"
  description = "Booking worker Lambda - no inbound"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cinebook-lambda-sg" }
}

resource "aws_security_group" "db" {
  name        = "cinebook-db-sg"
  description = "RDS PostgreSQL - 5432 from API servers and Lambda"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "from-app"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  ingress {
    description     = "from-lambda"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cinebook-db-sg" }
}

# Kept for the interface-endpoint option (unused while the NAT instance is used).
resource "aws_security_group" "endpoints" {
  name        = "cinebook-endpoints-sg"
  description = "Interface endpoints - 443 from API servers and Lambda"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "from-app"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  ingress {
    description     = "from-lambda"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cinebook-endpoints-sg" }
}

resource "aws_security_group" "nat" {
  name        = "cinebook-nat-sg"
  description = "NAT instance - all traffic from API servers and Lambda"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "from-app"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.app.id]
  }

  ingress {
    description     = "from-lambda"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cinebook-nat-sg" }
}
