# GitHub Actions OIDC roles (infra-dev spec): plan on pull requests, apply only from a protected
# environment on main. No long-lived keys.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "name" {
  description = "Environment prefix (atesta-dev, atesta-prod): role names and the IAM the apply role may manage."
  type        = string
  default     = "atesta-dev"
}

variable "repository" {
  description = "owner/name of the GitHub repository."
  type        = string
}

variable "apply_environment" {
  description = "Protected GitHub environment allowed to apply (deploys from main only)."
  type        = string
  default     = "dev"
}

variable "state_bucket" {
  description = "S3 bucket holding the OpenTofu state."
  type        = string
}

data "aws_caller_identity" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "trust" {
  for_each = {
    plan  = "repo:${var.repository}:pull_request"
    apply = "repo:${var.repository}:environment:${var.apply_environment}"
  }
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value]
    }
  }
}

resource "aws_iam_role" "github" {
  for_each             = data.aws_iam_policy_document.trust
  name                 = "${var.name}-${each.key}"
  assume_role_policy   = each.value.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read_only" {
  role       = aws_iam_role.github["plan"].name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "state" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.state_bucket}"]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.state_bucket}/*"]
  }
}

resource "aws_iam_role_policy" "state" {
  for_each = aws_iam_role.github
  name     = "opentofu-state"
  role     = each.value.name
  policy   = data.aws_iam_policy_document.state.json
}

# Apply and deploy (hosted-environment spec): the services modules/platform uses, plus IAM only
# for this environment's own roles and policies, per-org scan roles and service-linked roles.
data "aws_iam_policy_document" "apply" {
  statement {
    sid = "PlatformServices"
    actions = [
      "cognito-idp:*", "budgets:*", "ec2:*", "ecs:*", "ecr:*", "elasticloadbalancing:*", "rds:*",
      "kms:*", "logs:*", "cloudfront:*", "ses:*", "acm:DescribeCertificate", "acm:ListCertificates",
      "application-autoscaling:*", "cloudwatch:*",
    ]
    resources = ["*"]
  }
  statement {
    sid       = "OwnBuckets"
    actions   = ["s3:*"]
    resources = ["arn:aws:s3:::${var.name}-*", "arn:aws:s3:::${var.name}-*/*"]
  }
  statement {
    sid       = "OwnSecrets"
    actions   = ["secretsmanager:*"]
    resources = ["arn:aws:secretsmanager:*:${local.account}:secret:atesta/${var.name}/*"]
  }
  statement {
    sid     = "OwnIam"
    actions = ["iam:*"]
    resources = [
      "arn:aws:iam::${local.account}:role/${var.name}-*",
      "arn:aws:iam::${local.account}:role/atesta-scan/${var.name}/*",
      "arn:aws:iam::${local.account}:policy/${var.name}-*",
      "arn:aws:iam::${local.account}:oidc-provider/token.actions.githubusercontent.com",
    ]
  }
  statement {
    sid       = "ServiceLinkedRoles"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values = [
        "ecs.amazonaws.com", "elasticloadbalancing.amazonaws.com", "rds.amazonaws.com",
        "ecs.application-autoscaling.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role_policy" "apply" {
  name   = "${var.name}-apply"
  role   = aws_iam_role.github["apply"].name
  policy = data.aws_iam_policy_document.apply.json
}

output "plan_role_arn" {
  value = aws_iam_role.github["plan"].arn
}

output "apply_role_arn" {
  value = aws_iam_role.github["apply"].arn
}
