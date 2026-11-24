# One Atesta environment (hosted-environment spec): everything below Cognito and the GitHub roles.
# envs/dev and envs/prod differ only in the sizes passed here, so prod cannot drift from what dev
# exercises. Nothing is applied until the owner decides; a plan shows what an apply would create.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "name" {
  description = "Environment prefix: atesta-dev or atesta-prod."
  type        = string
}

variable "multi_az" {
  type = bool
}

variable "backup_retention_days" {
  type = number
}

variable "nat_per_az" {
  type = bool
}

variable "api_count" {
  type = number
}

variable "worker_count" {
  type = number
}

module "kms" {
  source = "../kms"
  name   = var.name
}

module "network" {
  source       = "../network"
  name         = var.name
  logs_key_arn = module.kms.logs_key_arn
  nat_per_az   = var.nat_per_az
}

module "evidence" {
  source      = "../s3-evidence"
  name        = var.name
  bucket_name = "${var.name}-evidence-${data.aws_caller_identity.current.account_id}"
  kms_key_arn = module.kms.evidence_key_arn
}

# Malware scan results (evidence-malware-scanning spec): GuardDuty publishes each result of the
# evidence bucket's plan to the default event bus; this rule puts them on an encrypted queue the
# worker drains every minute. A message the worker cannot place (its upload has not committed)
# comes back after the visibility timeout and, after 10 receives, waits 14 days in the
# dead-letter queue.
resource "aws_sqs_queue" "file_scans_dead" {
  name                      = "${var.name}-file-scans-dead"
  kms_master_key_id         = module.kms.queues_key_arn
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "file_scans" {
  name                       = "${var.name}-file-scans"
  kms_master_key_id          = module.kms.queues_key_arn
  visibility_timeout_seconds = 300
  message_retention_seconds  = 345600
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.file_scans_dead.arn, maxReceiveCount = 10 })
}

resource "aws_cloudwatch_event_rule" "file_scans" {
  name        = "${var.name}-file-scans"
  description = "GuardDuty malware scan results of the evidence bucket, to the worker's queue"
  event_pattern = jsonencode({
    source        = ["aws.guardduty"]
    "detail-type" = ["GuardDuty Malware Protection Object Scan Result"]
    resources     = [module.evidence.malware_protection_plan_arn]
  })
}

resource "aws_cloudwatch_event_target" "file_scans" {
  rule = aws_cloudwatch_event_rule.file_scans.name
  arn  = aws_sqs_queue.file_scans.arn
}

# Only this rule may send (AWS, "Using resource-based policies for Amazon EventBridge", SQS).
data "aws_iam_policy_document" "file_scans_queue" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.file_scans.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_cloudwatch_event_rule.file_scans.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "file_scans" {
  queue_url = aws_sqs_queue.file_scans.id
  policy    = data.aws_iam_policy_document.file_scans_queue.json
}

# The API, worker and migration tasks share this group: the only clients of the database.
resource "aws_security_group" "app" {
  name        = "${var.name}-app"
  description = "Application tasks: the only clients of the database"
  vpc_id      = module.network.vpc_id
}

module "database" {
  source                = "../rds"
  name                  = var.name
  vpc_id                = module.network.vpc_id
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = aws_security_group.app.id
  kms_key_arn           = module.kms.database_key_arn
  secrets_key_arn       = module.kms.secrets_key_arn
  logs_key_arn          = module.kms.logs_key_arn
  multi_az              = var.multi_az
  backup_retention_days = var.backup_retention_days
}

module "ecr" {
  source      = "../ecr"
  name        = var.name
  kms_key_arn = module.kms.secrets_key_arn
}

# Services come up once images are pushed (pinned by digest) and the edge certificates exist;
# until then images and edge stay null and only the base layer is planned.
variable "images" {
  type    = object({ api = string, worker = string, scan = string })
  default = null
}

# Public edge: hostnames and certificates the owner creates (docs/runbooks/deploy.md). The API
# certificate is in eu-south-2 for the load balancer; the web one is in us-east-1 for CloudFront.
variable "edge" {
  type = object({
    aliases                 = list(string)
    web_certificate_arn     = string
    api_origin_domain       = string
    api_certificate_arn     = string
    content_security_policy = string
  })
  default = null
}

variable "app_environment" {
  description = "Plain settings (ATESTA_ENV, Cognito ids, web origin). Never secrets."
  type        = map(string)
  default     = {}
}

resource "aws_secretsmanager_secret" "session_key" {
  name        = "atesta/${var.name}/api/session-key"
  description = "ATESTA_SESSION_KEY (base64, 32 bytes), set by hand"
  kms_key_id  = module.kms.secrets_key_arn
}

# Evidence file uploads (#222): the services find the evidence bucket through these settings.
# Later arguments win in merge(), so a hand-set value cannot point the API at another bucket.
locals {
  app_environment = merge(var.app_environment, {
    ATESTA_EVIDENCE_STORE      = "s3"
    ATESTA_EVIDENCE_BUCKET     = module.evidence.bucket_name
    ATESTA_FILE_SCAN_QUEUE_URL = aws_sqs_queue.file_scans.url
    AWS_DEFAULT_REGION         = data.aws_region.current.region
  })
}

module "ecs" {
  source                = "../ecs"
  count                 = var.images == null || var.edge == null ? 0 : 1
  name                  = var.name
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = aws_security_group.app.id
  db_security_group_id  = module.database.security_group_id
  logs_key_arn          = module.kms.logs_key_arn
  secrets_key_arn       = module.kms.secrets_key_arn
  evidence_bucket_arn   = module.evidence.bucket_arn
  evidence_key_arn      = module.kms.evidence_key_arn
  file_scan_queue_arn   = aws_sqs_queue.file_scans.arn
  queues_key_arn        = module.kms.queues_key_arn
  certificate_arn       = var.edge.api_certificate_arn
  images                = var.images
  environment           = local.app_environment
  api_count             = var.api_count
  worker_count          = var.worker_count
  secrets = {
    api = {
      ATESTA_DATABASE_URL = module.database.app_url_secret_arn
      ATESTA_SESSION_KEY  = aws_secretsmanager_secret.session_key.arn
    }
    worker  = { ATESTA_DATABASE_URL = module.database.app_url_secret_arn }
    migrate = { ATESTA_MIGRATION_DATABASE_URL = module.database.migration_url_secret_arn }
    bootstrap = {
      ATESTA_MASTER_PASSWORD        = "${module.database.master_secret_arn}:password::"
      ATESTA_DATABASE_URL           = module.database.app_url_secret_arn
      ATESTA_MIGRATION_DATABASE_URL = module.database.migration_url_secret_arn
    }
  }
  decrypt_key_arns = [module.kms.database_key_arn]
}

module "web" {
  source                  = "../web"
  count                   = var.edge == null ? 0 : 1
  name                    = var.name
  aliases                 = var.edge.aliases
  certificate_arn         = var.edge.web_certificate_arn
  api_origin_domain       = var.edge.api_origin_domain
  content_security_policy = var.edge.content_security_policy
}

output "api_load_balancer" {
  value = try(module.ecs[0].alb_dns_name, null)
}

output "web" {
  value = try({ bucket = module.web[0].bucket_name, distribution = module.web[0].distribution_id, domain = module.web[0].domain_name }, null)
}

output "ecr_repositories" {
  value = module.ecr.repository_urls
}

variable "mail_domain" {
  description = "Sending domain for notification email; leave unset until the owner picks one."
  type        = string
  default     = null
}

module "ses_notifications" {
  source = "../ses"
  count  = var.mail_domain == null ? 0 : 1
  name   = "${var.name}-notifications"
  domain = var.mail_domain
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "mail_dns_records" {
  value = try(module.ses_notifications[0].dns_records, [])
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Everything the deploy workflow (.github/workflows/deploy.yml) reads, in one output.
output "deploy" {
  value = {
    cluster            = try(module.ecs[0].cluster_arn, null)
    private_subnets    = module.network.private_subnet_ids
    app_security_group = aws_security_group.app.id
    migrate_family     = "${var.name}-migrate"
    bootstrap_family   = "${var.name}-bootstrap"
    repositories       = module.ecr.repository_urls
    web_bucket         = try(module.web[0].bucket_name, null)
    distribution       = try(module.web[0].distribution_id, null)
    hostname           = try(var.edge.aliases[0], null)
  }
}
