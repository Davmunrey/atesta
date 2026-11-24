# Containers (hosted-environment spec, ADR-004): the API and the worker run as Fargate services in
# private subnets (the API service and its load balancer are in api.tf); migrations run as a one-off task; each scan attempt is one RunTask of the scan
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

variable "evidence_key_arn" {
  description = "KMS key of the evidence bucket: the API encrypts uploads and decrypts downloads."
  type        = string
}

variable "file_scan_queue_arn" {
  description = "Queue of GuardDuty malware scan results the worker drains (evidence-malware-scanning spec)."
  type        = string
}

variable "m365_secret_arn" {
  description = "The platform's M365 scanner credential, named in M365 job files (issue 453)."
  type        = string
}

variable "alert_topic_arn" {
  description = "Topic the scan failure-rate alarm notifies (issue 453)."
  type        = string
}

variable "queues_key_arn" {
  description = "KMS key of that queue: receiving needs kms:Decrypt (AWS, SQS key management)."
  type        = string
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
  description = "Per container: variable name to Secrets Manager ARN (or ARN:json-key:: for one key)."
  type = object({
    api       = map(string)
    worker    = map(string)
    migrate   = map(string)
    bootstrap = optional(map(string), {})
  })
}

variable "decrypt_key_arns" {
  description = "Other KMS keys the listed secrets use, such as the database key of the RDS master secret."
  type        = list(string)
  default     = []
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
  evidence_bucket = element(split(":", var.evidence_bucket_arn), 5) # arn:aws:s3:::<name>
  # The Fargate runner's settings (issue 453): the worker alone gets them, built from this
  # module's own resources. ATESTA_SCANNER_EXPECTED comes from the worker image.
  scan_runner = {
    ATESTA_SCAN_RUNNER          = "fargate"
    ATESTA_SCAN_BUCKET          = local.evidence_bucket
    ATESTA_SCAN_CLUSTER         = aws_ecs_cluster.this.arn # the RunScans condition compares ARNs
    ATESTA_SCAN_TASK_DEFINITION = "${var.name}-scan"
    ATESTA_SCAN_SUBNETS         = join(",", var.private_subnet_ids)
    ATESTA_SCAN_SECURITY_GROUP  = aws_security_group.scan.id
    ATESTA_SCAN_ROLE_PREFIX     = "arn:aws:iam::${local.account}:role/atesta-scan/${var.name}/"
    ATESTA_M365_CREDENTIAL_REF  = "aws-sm:${var.m365_secret_arn}"
  }
  # The wrapper reads its job and writes its outputs in S3 (issue 444); never an override.
  scan_environment = {
    ATESTA_SCAN_SOURCE = "s3"
    ATESTA_SCAN_BUCKET = local.evidence_bucket
    AWS_DEFAULT_REGION = local.region
  }
  # IAM needs the secret's own ARN, without a ":json-key::" suffix.
  secret_arns = distinct([
    for ref in concat(values(var.secrets.api), values(var.secrets.worker), values(var.secrets.migrate), values(var.secrets.bootstrap)) :
    regex("^arn:aws:secretsmanager:[^:]+:[0-9]+:secret:[^:]+", ref)
  ])
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
      environment      = [for k, v in merge(var.environment, local.scan_runner) : { name = k, value = v }]
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
    # One-off: bootstrap.sql and role passwords as the RDS master (deploy runbook).
    bootstrap = merge(local.locked, {
      mountPoints      = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
      image            = var.images.api
      command          = ["python", "-m", "atesta_api.platform.db_bootstrap"]
      environment      = [for k, v in var.environment : { name = k, value = v }]
      secrets          = [for k, arn in var.secrets.bootstrap : { name = k, valueFrom = arn }]
      logConfiguration = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.this["migrate"].name, "awslogs-region" = local.region, "awslogs-stream-prefix" = "bootstrap" } }
    })
    scan = merge(local.locked, {
      # Same writable paths as the local runner's tmpfs mounts (scanner-connectors spec).
      mountPoints = [
        { sourceVolume = "tmp", containerPath = "/tmp" },
        { sourceVolume = "work", containerPath = "/work" },
        { sourceVolume = "home", containerPath = "/home/scanner" },
      ]
      image            = var.images.scan
      environment      = [for k, v in local.scan_environment : { name = k, value = v }]
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
    resources = local.secret_arns
  }
  statement {
    sid       = "DecryptSecretsAndImages"
    actions   = ["kms:Decrypt"]
    resources = concat([var.secrets_key_arn], var.decrypt_key_arns)
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
    sid       = "DrainFileScans"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility"]
    resources = [var.file_scan_queue_arn]
  }
  statement {
    sid       = "FileScanKey"
    actions   = ["kms:Decrypt"]
    resources = [var.queues_key_arn]
  }
  # Scan storage (issue 453): the worker writes each attempt's job file and reads outputs, and
  # lists only scan prefixes: evidence keys carry document names. Without a bucket-wide list a
  # missing key answers 403, which S3ScanStore settles by listing that key.
  statement {
    sid       = "WriteScanJobs"
    actions   = ["s3:PutObject"]
    resources = ["${var.evidence_bucket_arn}/*/scans/*/attempt-*/job.json"]
  }
  statement {
    sid       = "ReadScanOutputs"
    actions   = ["s3:GetObject"]
    resources = ["${var.evidence_bucket_arn}/*/scans/*"]
  }
  statement {
    sid       = "ListScanOutputs"
    actions   = ["s3:ListBucket"]
    resources = [var.evidence_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["*/scans/*"]
    }
  }
  statement {
    sid       = "ScanStoreKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.evidence_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${local.region}.amazonaws.com"]
    }
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

# Evidence file uploads (evidence-file-uploads spec): the API is the only writer of uploaded
# documents. It may put and get objects under <organization_id>/evidence/ and nothing else in the
# bucket: no delete, no list, no tagging, no scan outputs. It reads a version only once GuardDuty
# tagged it clean (evidence-malware-scanning spec), so a bug in the API's own status check still
# serves nothing unscanned. SSE-KMS needs kms:GenerateDataKey to write and kms:Decrypt to read
# (AWS, "Using server-side encryption with AWS KMS keys").
data "aws_iam_policy_document" "api" {
  statement {
    sid       = "EvidenceUploads"
    actions   = ["s3:PutObject"]
    resources = ["${var.evidence_bucket_arn}/*/evidence/*"]
  }
  statement {
    sid       = "EvidenceReadsWhenClean"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${var.evidence_bucket_arn}/*/evidence/*"]
    condition {
      test     = "StringEquals"
      variable = "s3:ExistingObjectTag/GuardDutyMalwareScanStatus"
      values   = ["NO_THREATS_FOUND"]
    }
  }
  statement {
    sid       = "EvidenceKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.evidence_key_arn]
  }
}

resource "aws_iam_role_policy" "api" {
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# Permissions boundary for every per-org scan role (scanner-connectors spec, Runners): whatever
# a role's own policy says, it can read only connector secrets of this environment, write scan
# outputs and read job files under an organization prefix, decrypt with the secrets key, and use
# the evidence key that encrypts those objects (issue 453).
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
    sid       = "SecretsKey"
    actions   = ["kms:Decrypt"]
    resources = [var.secrets_key_arn]
  }
  statement {
    sid       = "EvidenceKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.evidence_key_arn]
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
  for_each                 = { api = aws_iam_role.api.arn, worker = aws_iam_role.worker.arn, migrate = null, bootstrap = null }
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

# --- Scan failure-rate alert (scanner-connectors spec; issue 453) ------------------------------
# More than 5% of scans failed over 24 h, with at least 20 scans, counted from the worker's
# scan.finished events (ids and codes only), never by a cross-tenant query.

resource "aws_cloudwatch_log_metric_filter" "scans" {
  for_each = {
    ScansFinished = "{ $.event = \"scan.finished\" }"
    ScansFailed   = "{ ($.event = \"scan.finished\") && ($.status = \"failed\") }"
  }
  name           = "${var.name}-${each.key}"
  log_group_name = aws_cloudwatch_log_group.this["worker"].name
  pattern        = each.value
  metric_transformation {
    name      = each.key
    namespace = "Atesta/${var.name}"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "scan_failure_rate" {
  alarm_name          = "${var.name}-scan-failure-rate"
  alarm_description   = "More than 5% of scans failed over 24 h, with at least 20 scans."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 5
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alert_topic_arn]
  metric_query {
    id          = "rate"
    expression  = "IF(FILL(finished, 0) >= 20, 100 * FILL(failed, 0) / FILL(finished, 0), 0)"
    label       = "Failed scans, percent"
    return_data = true
  }
  metric_query {
    id = "finished"
    metric {
      namespace   = "Atesta/${var.name}"
      metric_name = "ScansFinished"
      period      = 86400
      stat        = "Sum"
    }
  }
  metric_query {
    id = "failed"
    metric {
      namespace   = "Atesta/${var.name}"
      metric_name = "ScansFailed"
      period      = 86400
      stat        = "Sum"
    }
  }
  depends_on = [aws_cloudwatch_log_metric_filter.scans]
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
