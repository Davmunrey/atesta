# Customer-managed keys (hosted-environment spec): one per data class (database, evidence,
# application secrets, logs, queues), yearly rotation. The logs key lets CloudWatch Logs in this
# region use it, scoped to this account's log groups. The queues key lets EventBridge encrypt the
# messages it puts on this account's queues (evidence-malware-scanning spec): EventBridge cannot
# deliver to an encrypted queue otherwise ("My events are not delivered to the target Amazon SQS
# queue", EventBridge troubleshooting). It also lets CloudWatch alarms publish to the alerts topic
# it encrypts (issue 453), as AWS documents ("Encryption at rest", Amazon SNS key management).

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "name" {
  description = "Prefix for aliases, for example atesta-dev."
  type        = string
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
  region  = data.aws_region.current.region
}

data "aws_iam_policy_document" "base" {
  statement {
    sid       = "AccountAdministers"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${local.account}:root"]
    }
  }
}

data "aws_iam_policy_document" "logs" {
  source_policy_documents = [data.aws_iam_policy_document.base.json]
  statement {
    sid       = "CloudWatchLogsUse"
    actions   = ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${local.region}.amazonaws.com"]
    }
    condition {
      test     = "ArnLike"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:aws:logs:${local.region}:${local.account}:log-group:*"]
    }
  }
}

data "aws_iam_policy_document" "queues" {
  source_policy_documents = [data.aws_iam_policy_document.base.json]
  statement {
    sid       = "CloudWatchAlarmsUse"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey*"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
  }
  statement {
    sid       = "EventBridgeUse"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
  }
}

resource "aws_kms_key" "database" {
  description             = "${var.name} database"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.base.json
}

resource "aws_kms_key" "evidence" {
  description             = "${var.name} evidence bucket"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.base.json
}

resource "aws_kms_key" "secrets" {
  description             = "${var.name} application secrets"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.base.json
}

resource "aws_kms_key" "logs" {
  description             = "${var.name} logs"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.logs.json
}

resource "aws_kms_key" "queues" {
  description             = "${var.name} queues"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.queues.json
}

resource "aws_kms_alias" "database" {
  name          = "alias/${var.name}-database"
  target_key_id = aws_kms_key.database.key_id
}

resource "aws_kms_alias" "evidence" {
  name          = "alias/${var.name}-evidence"
  target_key_id = aws_kms_key.evidence.key_id
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.name}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

resource "aws_kms_alias" "logs" {
  name          = "alias/${var.name}-logs"
  target_key_id = aws_kms_key.logs.key_id
}

resource "aws_kms_alias" "queues" {
  name          = "alias/${var.name}-queues"
  target_key_id = aws_kms_key.queues.key_id
}

output "database_key_arn" {
  value = aws_kms_key.database.arn
}

output "evidence_key_arn" {
  value = aws_kms_key.evidence.arn
}

output "secrets_key_arn" {
  value = aws_kms_key.secrets.arn
}

output "logs_key_arn" {
  value = aws_kms_key.logs.arn
}

output "queues_key_arn" {
  value = aws_kms_key.queues.arn
}
