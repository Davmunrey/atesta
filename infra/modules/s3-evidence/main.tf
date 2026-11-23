# Evidence bucket (hosted-environment spec): private, encrypted with its own key, versioned, TLS
# only. Object keys start with the organization id, as the evidence model already checks; the
# per-scan task roles (ADR-004) are scoped to that prefix in the ecs module.
#
# Object Lock (#263, owner 2026-11-23): every object version is retained 365 days in governance
# mode. A lifecycle expiration cannot delete a locked version (AWS, "Managing S3 Lifecycle
# policies with Object Lock"), so noncurrent versions live at least that long. The bucket policy
# denies s3:BypassGovernanceRetention to every principal, the deploy role's s3:* included.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "bucket_name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

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
