# Scan roles of one customer organization (scanner-connectors spec, AWS runner; issue 453).
#
# Owner decision, 2026-11-24 ("A y A"): the owner applies this module per customer, by listing
# the organization in the platform's scan_organizations; no Atesta process holds IAM write
# rights. Each role is the task role of one container run (the FargateRunner passes it as
# overrides.taskRoleArn), bounded by the environment's scan boundary, and reaches only this
# organization's scan prefix and its own credentials:
# - scan-m365-<org> reads the platform's M365 scanner credential (one app for every customer);
# - verify-gws-<org> reads the customer's scan key and verifier key (D7);
# - scan-gws-<org> reads the scan key only.
# Secrets Manager appends six characters to a secret's name, matched by "??????" exactly.

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

variable "organization_id" {
  description = "The customer organization's id, as stored in Atesta."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.organization_id))
    error_message = "Use the organization id as a lowercase UUID."
  }
}

variable "connectors" {
  description = "Providers this organization scans: m365, google_workspace or both."
  type        = set(string)
  validation {
    condition     = length(var.connectors) > 0 && alltrue([for c in var.connectors : contains(["m365", "google_workspace"], c)])
    error_message = "List m365, google_workspace or both."
  }
}

variable "boundary_arn" {
  description = "The environment's scan permissions boundary (ecs module)."
  type        = string
}

variable "evidence_bucket_arn" {
  type = string
}

variable "evidence_key_arn" {
  type = string
}

variable "secrets_key_arn" {
  type = string
}

variable "m365_secret_arn" {
  description = "The platform's M365 scanner credential (platform module)."
  type        = string
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account         = data.aws_caller_identity.current.account_id
  region          = data.aws_region.current.region
  prefix          = "${var.evidence_bucket_arn}/${var.organization_id}/scans/*/attempt-*"
  google          = "arn:aws:secretsmanager:${local.region}:${local.account}:secret:atesta/${var.name}/google/${var.organization_id}-??????"
  google_verifier = "arn:aws:secretsmanager:${local.region}:${local.account}:secret:atesta/${var.name}/google-verifier/${var.organization_id}-??????"
  kinds = {
    "scan-m365"  = { connector = "m365", secrets = [var.m365_secret_arn] }
    "verify-gws" = { connector = "google_workspace", secrets = [local.google, local.google_verifier] }
    "scan-gws"   = { connector = "google_workspace", secrets = [local.google] }
  }
  roles = { for kind, role in local.kinds : kind => role.secrets if contains(var.connectors, role.connector) }
}

# ECS documents both keys against the confused deputy; a cluster cannot be named in SourceArn
# (AWS, "Amazon ECS task IAM role"). Only the worker may pass these roles (ecs module).
data "aws_iam_policy_document" "trust" {
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
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:ecs:${local.region}:${local.account}:*"]
    }
  }
}

data "aws_iam_policy_document" "this" {
  for_each = local.roles
  statement {
    sid       = "Credential"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = each.value
  }
  statement {
    sid       = "Outputs"
    actions   = ["s3:PutObject"]
    resources = ["${local.prefix}/out/*"]
  }
  statement {
    sid       = "Job"
    actions   = ["s3:GetObject"]
    resources = ["${local.prefix}/job.json"]
  }
  statement {
    sid       = "SecretsKey"
    actions   = ["kms:Decrypt"]
    resources = [var.secrets_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${local.region}.amazonaws.com"]
    }
  }
  statement {
    sid       = "EvidenceKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.evidence_key_arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${local.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  for_each             = local.roles
  name                 = "${each.key}-${var.organization_id}"
  path                 = "/atesta-scan/${var.name}/"
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  permissions_boundary = var.boundary_arn
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "this" {
  for_each = local.roles
  name     = "scan"
  role     = aws_iam_role.this[each.key].id
  policy   = data.aws_iam_policy_document.this[each.key].json
}

output "role_arns" {
  value = { for kind, role in aws_iam_role.this : kind => role.arn }
}
