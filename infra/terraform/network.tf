# ---------------------------------------------------------------- VPC and subnets
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "Cinebook-vpc" }
}

locals {
  subnets = {
    "public-1a" = { cidr = "10.0.0.0/20", az = "${var.region}a" }
    "public-1b" = { cidr = "10.0.16.0/20", az = "${var.region}b" }
    "app-1a"    = { cidr = "10.0.128.0/20", az = "${var.region}a" }
    "app-1b"    = { cidr = "10.0.144.0/20", az = "${var.region}b" }
    "db-1a"     = { cidr = "10.0.160.0/20", az = "${var.region}a" }
    "db-1b"     = { cidr = "10.0.176.0/20", az = "${var.region}b" }
  }
  private_tables = ["app-1a", "app-1b", "db-1a", "db-1b"]
  app_subnet_ids = [aws_subnet.this["app-1a"].id, aws_subnet.this["app-1b"].id]
}

resource "aws_subnet" "this" {
  for_each          = local.subnets
  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az
  tags              = { Name = "Cinebook-${each.key}" }
}

# ---------------------------------------------------------------- Internet gateway and routing
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "Cinebook-igw" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "Cinebook-rtb-public" }
}

resource "aws_route_table" "private" {
  for_each = toset(local.private_tables)
  vpc_id   = aws_vpc.main.id
  tags     = { Name = "Cinebook-rtb-${each.key}" }
}

# Public subnets: internet through the internet gateway.
resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

# App subnets: outbound internet through the NAT instance. The db subnets get no internet route.
resource "aws_route" "app_nat" {
  for_each               = toset(["app-1a", "app-1b"])
  route_table_id         = aws_route_table.private[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_instance.nat.primary_network_interface_id
}

resource "aws_route_table_association" "public" {
  for_each       = toset(["public-1a", "public-1b"])
  subnet_id      = aws_subnet.this[each.key].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  for_each       = aws_route_table.private
  subnet_id      = aws_subnet.this[each.key].id
  route_table_id = each.value.id
}

# ---------------------------------------------------------------- Free gateway endpoints
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for k in local.private_tables : aws_route_table.private[k].id]
  tags              = { Name = "Cinebook-vpce-s3" }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private["app-1a"].id, aws_route_table.private["app-1b"].id]
  tags              = { Name = "Cinebook-vpce-dynamodb" }
}
