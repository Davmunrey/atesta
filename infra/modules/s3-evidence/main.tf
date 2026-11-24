# Evidence bucket (hosted-environment spec): private, encrypted with its own key, versioned, TLS
# only. Object keys start with the organization id, as the evidence model already checks; the
# per-scan task roles (ADR-004) are scoped to that prefix in the ecs module.
#
# Object Lock (#263, owner 2026-11-23): every object version is retained 365 days in governance
# mode. A lifecycle expiration cannot delete a locked version (AWS, "Managing S3 Lifecycle
# policies with Object Lock"), so noncurrent versions live at least that long. The bucket policy
# denies s3:BypassGovernanceRetention to every principal, the deploy role's s3:* included.
#
# Malware scanning (evidence-malware-scanning spec): GuardDuty Malware Protection for S3 scans
# every new object version and tags it GuardDutyMalwareScanStatus. The whole bucket is protected:
# prefixes are literal and keys start with the organization id (D2). Only the scan role may write
# that tag, so the API's read, bound to it in the ecs module, cannot be unlocked by anyone else.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "name" {
  description = "Environment prefix (atesta-dev, atesta-prod): the scan role's name."
  type        = string
}

variable "bucket_name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

variable "noncurrent_days" {
  description = "Days a replaced object version is kept before it expires; the lock retention wins."
  type        = number
  default     = 90
}

resource "aws_s3_bucket" "this" {
  bucket              = var.bucket_name
  object_lock_enabled = true
}

resource "aws_s3_bucket_object_lock_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 365
    }
  }
  depends_on = [aws_s3_bucket_versioning.this]
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    id     = "expire-noncurrent"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
  # Explicit deny beats every allow. Erasing locked evidence means changing this policy first.
  statement {
    sid       = "DenyGovernanceBypass"
    effect    = "Deny"
    actions   = ["s3:BypassGovernanceRetention"]
    resources = ["${aws_s3_bucket.this.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
  # Scan storage is write-once (scanner-connectors spec, AWS runner; issue 453). The scan roles
  # and the worker must send If-None-Match on every scan write, so no output or job file is ever
  # replaced; multipart parts carry no conditional header, so they are refused too (both writers
  # use one PutObject). AWS, "Enforce conditional writes on Amazon S3 buckets".
  statement {
    sid       = "DenyScanWritesWithoutIfNoneMatch"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this.arn}/*/scans/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Null"
      variable = "s3:if-none-match"
      values   = ["true"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = [local.scan_roles, local.worker_role]
    }
  }
  # A scan role writes only its outputs: never a job file, whatever its own policy says.
  statement {
    sid       = "DenyScanRolesJobWrites"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this.arn}/*/job.json"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = [local.scan_roles]
    }
  }
  statement {
    sid    = "DenyScanRolesDeletesAndMetadata"
    effect = "Deny"
    actions = [
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:PutObjectAcl",
      "s3:PutObjectVersionAcl",
      "s3:PutObjectRetention",
      "s3:PutObjectLegalHold",
      "s3:PutObjectTagging",
      "s3:PutObjectVersionTagging",
    ]
    resources = ["${aws_s3_bucket.this.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"
      values   = [local.scan_roles]
    }
  }
  # The scan tag is the API's read permission: nobody but GuardDuty's role may set it, on an
  # upload (PutObject with tags needs PutObjectTagging too) or afterwards (AWS, "Using tag-based
  # access control (TBAC) with Malware Protection for S3").
  statement {
    sid       = "DenyScanTagWritesButGuardDuty"
    effect    = "Deny"
    actions   = ["s3:PutObject", "s3:PutObjectTagging", "s3:PutObjectVersionTagging"]
    resources = ["${aws_s3_bucket.this.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "s3:RequestObjectTagKeys"
      values   = ["GuardDutyMalwareScanStatus"]
    }
    condition {
      test     = "ArnNotEquals"
      variable = "aws:PrincipalArn"
      values   = [aws_iam_role.malware_scan.arn]
    }
  }
}

# The role GuardDuty assumes to scan and tag, as AWS's template ("Create or update IAM role
# policy"), for this bucket and key only.
data "aws_iam_policy_document" "malware_scan_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["malware-protection-plan.guardduty.amazonaws.com"]
    }
  }
}

locals {
  # Role ARNs as aws:PrincipalArn reports them for an assumed role (the role, not the session).
  scan_roles   = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/atesta-scan/${var.name}/*"
  worker_role  = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.name}-worker"
  managed_rule = "arn:aws:events:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:rule/DO-NOT-DELETE-AmazonGuardDutyMalwareProtectionS3*"
}

data "aws_iam_policy_document" "malware_scan" {
  statement {
    sid       = "AllowManagedRuleToSendS3EventsToGuardDuty"
    actions   = ["events:PutRule", "events:DeleteRule", "events:PutTargets", "events:RemoveTargets"]
    resources = [local.managed_rule]
    condition {
      test     = "StringLike"
      variable = "events:ManagedBy"
      values   = ["malware-protection-plan.guardduty.amazonaws.com"]
    }
  }
  statement {
    sid       = "AllowGuardDutyToMonitorEventBridgeManagedRule"
    actions   = ["events:DescribeRule", "events:ListTargetsByRule"]
    resources = [local.managed_rule]
  }
  statement {
    sid       = "AllowPostScanTag"
    actions   = ["s3:PutObjectTagging", "s3:GetObjectTagging", "s3:PutObjectVersionTagging", "s3:GetObjectVersionTagging"]
    resources = ["${aws_s3_bucket.this.arn}/*"]
  }
  statement {
    sid       = "AllowEnableS3EventBridgeEvents"
    actions   = ["s3:PutBucketNotification", "s3:GetBucketNotification"]
    resources = [aws_s3_bucket.this.arn]
  }
  statement {
    sid       = "AllowPutValidationObject"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.this.arn}/malware-protection-resource-validation-object"]
  }
  statement {
    sid       = "AllowCheckBucketOwnership"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.this.arn]
  }
  statement {
    sid       = "AllowMalwareScan"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.this.arn}/*"]
  }
  statement {
    sid       = "AllowDecryptForMalwareScan"
    actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
    resources = [var.kms_key_arn]
    condition {
      test     = "StringLike"
      variable = "kms:ViaService"
      values   = ["s3.${data.aws_region.current.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "malware_scan" {
  name               = "${var.name}-malware-scan"
  assume_role_policy = data.aws_iam_policy_document.malware_scan_trust.json
}

resource "aws_iam_role_policy" "malware_scan" {
  role   = aws_iam_role.malware_scan.id
  policy = data.aws_iam_policy_document.malware_scan.json
}

resource "aws_guardduty_malware_protection_plan" "evidence" {
  role = aws_iam_role.malware_scan.arn
  protected_resource {
    s3_bucket {
      bucket_name = aws_s3_bucket.this.id
    }
  }
  actions {
    tagging {
      status = "ENABLED"
    }
  }
  depends_on = [aws_iam_role_policy.malware_scan]
}

resource "aws_s3_bucket_policy" "this" {
  bucket     = aws_s3_bucket.this.id
  policy     = data.aws_iam_policy_document.bucket.json
  depends_on = [aws_s3_bucket_public_access_block.this]
}

output "bucket_name" {
  value = aws_s3_bucket.this.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}

output "malware_protection_plan_arn" {
  value = aws_guardduty_malware_protection_plan.evidence.arn
}
