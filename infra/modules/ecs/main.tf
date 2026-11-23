# Containers (hosted-environment spec, ADR-004): the API and the worker run as Fargate services in
# private subnets (the API's load balancer is in api.tf); migrations run as a one-off task; each scan attempt is one RunTask of the scan
# task definition with the per-org, per-provider role passed by the worker (overrides.taskRoleArn).
# Secrets reach containers only through ECS secrets from Secrets Manager; images are pinned by
# digest. The scan egress allowlist (scanner-connectors spec, Runners) is not built yet: the scan
# security group allows HTTPS out only, and the allowlisting proxy comes with the Fargate runner.

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

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "app_security_group_id" {
  type = string
}

variable "db_security_group_id" {
  type = string
}

variable "logs_key_arn" {
  type = string
}

variable "secrets_key_arn" {
  type = string
}

variable "evidence_bucket_arn" {
  type = string
}

variable "images" {
  description = "Image references for api, worker and scan, pinned by digest."
  type        = object({ api = string, worker = string, scan = string })
  validation {
    condition     = alltrue([for image in values(var.images) : can(regex("@sha256:[0-9a-f]{64}$", image))])
    error_message = "Pin every image by digest (repository@sha256:...)."
  }
}

variable "environment" {
  description = "Plain settings shared by api, worker and migrate. Never secrets."
  type        = map(string)
  validation {
    condition     = alltrue([for k in keys(var.environment) : !can(regex("(DATABASE_URL|_KEY|SECRET|PASSWORD|TOKEN)$", k))])
    error_message = "Secrets go in var.secrets (Secrets Manager), never in plain environment."
  }
}

variable "secrets" {
  description = "Per container: environment variable name to Secrets Manager ARN."
  type        = object({ api = map(string), worker = map(string), migrate = map(string) })
}

variable "migrate_command" {
  type    = list(string)
  default = ["alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"]
}

variable "worker_count" {
  type    = number
  default = 1
}

variable "log_retention_days" {
  type    = number
  default = 365
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account         = data.aws_caller_identity.current.account_id
  region          = data.aws_region.current.region
  scan_family_arn = "arn:aws:ecs:${local.region}:${local.account}:task-definition/${var.name}-scan"
  # Every container: read-only root, non-root user, no privileges, no Linux capabilities.
  locked = {
    readonlyRootFilesystem = true
    user                   = "10001"
    privileged             = false
    linuxParameters        = { initProcessEnabled = true, capabilities = { drop = ["ALL"] } }
  }
  containers = {
    api = merge(local.locked, {
      mountPoints      = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
      image            = var.images.api
      portMappings     = [{ containerPort = 8000, protocol = "tcp" }]
      environment      = [for k, v in var.environment : { name = k, value = v }]
      secrets          = [for k, arn in var.secrets.api : { name = k, valueFrom = arn }]
      logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.this["api"].name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "api" } }
    })
    worker = merge(local.locked, {
      mountPoints      = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
      image            = var.images.worker
      environment      = [for k, v in var.environment : { name = k, value = v }]
      secrets          = [for k, arn in var.secrets.worker : { name = k, valueFrom = arn }]
      logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.this["worker"].name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "worker" } }
    })
    migrate = merge(local.locked, {
      mountPoints      = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
      image            = var.images.api
      command          = var.migrate_command
      environment      = [for k, v in var.environment : { name = k, value = v }]
      secrets          = [for k, arn in var.secrets.migrate : { name = k, valueFrom = arn }]
      logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.this["migrate"].name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "migrate" } }
    })
    scan = merge(local.locked, {
      # Same writable paths as the local runner's tmpfs mounts (scanner-connectors spec).
      mountPoints = [
        { sourceVolume = "tmp", containerPath = "/tmp" },
        { sourceVolume = "work", containerPath = "/work" },
        { sourceVolume = "home", containerPath = "/home/scanner" },
      ]
      image            = var.images.scan
      logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.this["scan"].name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "scan" } }
    })
  }
}

resource "aws_cloudwatch_log_group" "this" {
  for_each          = toset(["api", "worker", "migrate", "scan"])
  name              = "/atesta/${var.name}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_key_arn
}

resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# --- IAM ------------------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_tasks" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

# Pulls images, writes logs and resolves exactly the secrets listed in var.secrets.
data "aws_iam_policy_document" "execution" {
  statement {
    sid       = "ReadListedSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = distinct(concat(values(var.secrets.api), values(var.secrets.worker), values(var.secrets.migrate)))
  }
  statement {
    sid       = "DecryptSecretsAndImages"
    actions   = ["kms:Decrypt"]
    resources = [var.secrets_key_arn]
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution" {
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

# The scan execution role only pulls the scan image and writes scan logs: no secrets.
resource "aws_iam_role" "scan_execution" {
  name               = "${var.name}-scan-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks.json
}

resource "aws_iam_role_policy_attachment" "scan_execution_managed" {
  role       = aws_iam_role.scan_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# The worker starts scans, passes only the scan execution role or a per-org scan role (path
# /atesta-scan/<name>/), and stops or describes them.
data "aws_iam_policy_document" "worker" {
  statement {
    sid       = "RunScans"
    actions   = ["ecs:RunTask"]
    resources = ["${local.scan_family_arn}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }
  statement {
    sid       = "WatchScans"
    actions   = ["ecs:DescribeTasks", "ecs:StopTask"]
    resources = ["arn:aws:ecs:${local.region}:${local.account}:task/${var.name}/*"]
  }
  statement {
    sid     = "PassScanRoles"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.scan_execution.arn,
      "arn:aws:iam::${local.account}:role/atesta-scan/${var.name}/*",
    ]
  }
}

resource "aws_iam_role" "worker" {
  name               = "${var.name}-worker"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks.json
}

resource "aws_iam_role_policy" "worker" {
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

resource "aws_iam_role" "api" {
  name               = "${var.name}-api"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks.json
}

# Permissions boundary for every per-org scan role (scanner-connectors spec, Runners): whatever
# a role's own policy says, it can read only connector secrets of this environment, write scan
# outputs and read job files under an organization prefix, and decrypt with the secrets key.
data "aws_iam_policy_document" "scan_boundary" {
  statement {
    sid       = "ConnectorSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = ["arn:aws:secretsmanager:${local.region}:${local.account}:secret:atesta/${var.name}/*"]
  }
  statement {
    sid       = "ScanOutputs"
    actions   = ["s3:PutObject"]
    resources = ["${var.evidence_bucket_arn}/*/scans/*/attempt-*/out/*"]
  }
  statement {
    sid       = "ScanJobs"
    actions   = ["s3:GetObject"]
    resources = ["${var.evidence_bucket_arn}/*/scans/*/attempt-*/job.json"]
  }
  statement {
    sid       = "Decrypt"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.secrets_key_arn]
  }
}

resource "aws_iam_policy" "scan_boundary" {
  name   = "${var.name}-scan-boundary"
  policy = data.aws_iam_policy_document.scan_boundary.json
}

# --- Network --------------------------------------------------------------------------------

resource "aws_vpc_security_group_egress_rule" "app_https" {
  security_group_id = var.app_security_group_id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "app_db" {
  security_group_id            = var.app_security_group_id
  referenced_security_group_id = var.db_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_security_group" "scan" {
  name        = "${var.name}-scan"
  description = "Scan tasks: no inbound, HTTPS out only"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "scan_https" {
  security_group_id = aws_security_group.scan.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

# --- Tasks and services ---------------------------------------------------------------------

resource "aws_ecs_task_definition" "this" {
  for_each                 = { api = aws_iam_role.api.arn, worker = aws_iam_role.worker.arn, migrate = null }
  family                   = "${var.name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = each.key == "worker" ? "512" : "256"
  memory                   = each.key == "worker" ? "1024" : "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = each.value
  container_definitions    = jsonencode([merge(local.containers[each.key], { name = each.key, essential = true })])
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  volume {
    name = "tmp"
  }
}

resource "aws_ecs_task_definition" "scan" {
  family                   = "${var.name}-scan"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "2048"
  memory                   = "4096"
  execution_role_arn       = aws_iam_role.scan_execution.arn
  container_definitions    = jsonencode([merge(local.containers.scan, { name = "scan", essential = true })])
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  dynamic "volume" {
    for_each = toset(["tmp", "work", "home"])
    content {
      name = volume.value
    }
  }
}

resource "aws_ecs_service" "worker" {
  name            = "${var.name}-worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this["worker"].arn
  desired_count   = var.worker_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.app_security_group_id]
    assign_public_ip = false
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "scan_security_group_id" {
  value = aws_security_group.scan.id
}

output "scan_boundary_arn" {
  value = aws_iam_policy.scan_boundary.arn
}
