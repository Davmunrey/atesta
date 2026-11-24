# Network (hosted-environment spec): a VPC across two availability zones. Public subnets hold
# only the load balancer and the NAT gateway; containers and the database live in private
# subnets with no inbound route from the internet. Flow logs go to CloudWatch, encrypted.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "name" {
  type = string
}

variable "cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "nat_per_az" {
  description = "One NAT gateway per zone (prod) or a single shared one (dev, cheaper)."
  type        = bool
  default     = false
}

variable "logs_key_arn" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 365
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  zones = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  availability_zone       = local.zones[count.index]
  cidr_block              = cidrsubnet(var.cidr, 8, count.index)
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.name}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count                   = 2
  vpc_id                  = aws_vpc.this.id
  availability_zone       = local.zones[count.index]
  cidr_block              = cidrsubnet(var.cidr, 8, 10 + count.index)
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.name}-private-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count  = var.nat_per_az ? 2 : 1
  domain = "vpc"
}

resource "aws_nat_gateway" "this" {
  count         = var.nat_per_az ? 2 : 1
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  depends_on    = [aws_internet_gateway.this]
}

resource "aws_route_table" "private" {
  count  = 2
  vpc_id = aws_vpc.this.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[var.nat_per_az ? count.index : 0].id
  }
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# S3 traffic (evidence, images) stays on the AWS network and avoids NAT charges.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id
}

data "aws_region" "current" {}

# Scan egress (scanner-connectors spec, AWS runner; issue 454). A scan task may not reach the
# internet, yet Fargate pulls its image and ships its logs through the task's own network
# interface, without the container's proxy (AWS, "Amazon ECR interface VPC endpoints"; "Fargate
# task networking"). These endpoints carry that traffic and the wrapper's Secrets Manager reads;
# S3 already has its gateway. Private DNS sends every task in the VPC through them. Dev keeps one
# zone (any subnet reaches it), prod one per zone, as the NAT gateways.
locals {
  endpoint_subnets = var.nat_per_az ? aws_subnet.private[*].id : [aws_subnet.private[0].id]
}

resource "aws_security_group" "endpoints" {
  name        = "${var.name}-endpoints"
  description = "Interface endpoints: HTTPS from inside the VPC"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_https" {
  security_group_id = aws_security_group.endpoints.id
  cidr_ipv4         = var.cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = toset(["ecr.api", "ecr.dkr", "logs", "secretsmanager"])
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${data.aws_region.current.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = local.endpoint_subnets
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true
}

resource "aws_cloudwatch_log_group" "flow" {
  name              = "/${var.name}/vpc-flow"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_key_arn
}

data "aws_iam_policy_document" "flow_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "flow" {
  name               = "${var.name}-vpc-flow"
  assume_role_policy = data.aws_iam_policy_document.flow_trust.json
}

data "aws_iam_policy_document" "flow_write" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.flow.arn}:*"]
  }
}

resource "aws_iam_role_policy" "flow" {
  role   = aws_iam_role.flow.id
  policy = data.aws_iam_policy_document.flow_write.json
}

resource "aws_flow_log" "this" {
  vpc_id          = aws_vpc.this.id
  traffic_type    = "ALL"
  log_destination = aws_cloudwatch_log_group.flow.arn
  iam_role_arn    = aws_iam_role.flow.arn
}

output "vpc_id" {
  value = aws_vpc.this.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "s3_prefix_list_id" {
  value = aws_vpc_endpoint.s3.prefix_list_id
}

output "endpoints_security_group_id" {
  value = aws_security_group.endpoints.id
}
