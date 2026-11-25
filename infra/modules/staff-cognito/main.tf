# Staff user pool for the operator portal (ADR-017, "Staff identity"; operator-portal spec, build
# step 6). Separate from the customer pool (modules/cognito): only an owner step creates accounts,
# MFA is required and never by SMS, and the only app client is the portal's. Username settings are
# immutable after creation, so each one is fixed here and asserted by infra/tests.
#
# Passkeys (AWS Cognito developer guide, "Authentication flows" and "Adding MFA to a user pool",
# read 2026-11-25): with MFA required, choice-based sign-in offers WEB_AUTHN only when the pool's
# WebAuthnConfiguration has FactorConfiguration MULTI_FACTOR_WITH_USER_VERIFICATION. The pinned
# provider (hashicorp/aws 6.73.0) cannot set that field: web_authn_configuration has only
# relying_party_id and user_verification, and SetUserPoolMfaConfig is sent without it whenever an
# MFA argument changes. So the first apply offers password plus TOTP; the owner sets the factor
# configuration once (deploy runbook) and then turns on var.passkeys. If the field is ever reset,
# Cognito stops offering passkeys and password plus TOTP still applies: it fails closed.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "name" {
  description = "User pool name, e.g. atesta-dev-staff."
  type        = string
}

variable "domain_prefix" {
  description = "Cognito prefix domain for managed login."
  type        = string
}

variable "callback_urls" {
  description = "OAuth callback URLs: /auth/callback on the admin host."
  type        = list(string)
}

variable "logout_urls" {
  description = "Sign-out return URLs on the admin host."
  type        = list(string)
}

variable "passkeys" {
  description = "Offer passkeys as the first factor. Only after the owner set FactorConfiguration (deploy runbook)."
  type        = bool
  default     = false
}

variable "email_sending_account" {
  description = "COGNITO_DEFAULT in dev only; DEVELOPER (SES in eu-west-3) in prod (ADR-007 amendment 1)."
  type        = string
  default     = "COGNITO_DEFAULT"
}

variable "ses_source_arn" {
  type    = string
  default = null
}

variable "from_email_address" {
  type    = string
  default = null
}

locals {
  es = jsondecode(file("${path.module}/../../i18n/cognito.es.json"))
  en = jsondecode(file("${path.module}/../../i18n/cognito.en.json"))
}

resource "aws_cognito_user_pool" "this" {
  name                     = var.name
  user_pool_tier           = "ESSENTIALS" # passkeys and passkey MFA need Essentials or higher
  deletion_protection      = "ACTIVE"
  mfa_configuration        = "ON"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  software_token_mfa_configuration {
    enabled = true
  }

  web_authn_configuration {
    user_verification = "required"
  }

  sign_in_policy {
    allowed_first_auth_factors = var.passkeys ? ["PASSWORD", "WEB_AUTHN"] : ["PASSWORD"]
  }

  username_configuration {
    case_sensitive = false
  }

  # No self-service recovery: a lost password or device goes to an admin (staff runbook).
  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
    invite_message_template {
      email_subject = "${local.es.staff_invite_subject} / ${local.en.staff_invite_subject}"
      email_message = "${local.es.staff_invite_message}\n\n${local.en.staff_invite_message}"
    }
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = false
    require_uppercase                = false
    require_numbers                  = false
    require_symbols                  = false
    temporary_password_validity_days = 3
  }

  email_configuration {
    email_sending_account = var.email_sending_account
    source_arn            = var.ses_source_arn
    from_email_address    = var.from_email_address
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain                = var.domain_prefix
  user_pool_id          = aws_cognito_user_pool.this.id
  managed_login_version = 2
}

# The portal's BFF (apps/operator, session.py): code flow with PKCE, no secret. Tokens are short;
# the session's own limits (30 minutes idle, 8 hours in total) end it sooner.
resource "aws_cognito_user_pool_client" "operator" {
  name                                 = "${var.name}-operator"
  user_pool_id                         = aws_cognito_user_pool.this.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  # Passkeys exist only in the choice-based flow, which the client must allow (AWS, as above).
  explicit_auth_flows           = var.passkeys ? ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_AUTH"] : ["ALLOW_REFRESH_TOKEN_AUTH"]
  callback_urls                 = var.callback_urls
  logout_urls                   = var.logout_urls
  read_attributes               = ["email", "email_verified"]
  write_attributes              = ["name"] # never empty: unset grants write on every attribute
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  access_token_validity         = 15
  id_token_validity             = 15
  refresh_token_validity        = 8

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }
}

resource "aws_cognito_managed_login_branding" "operator" {
  client_id                   = aws_cognito_user_pool_client.operator.id
  user_pool_id                = aws_cognito_user_pool.this.id
  use_cognito_provided_values = true
}

data "aws_region" "current" {}

output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  value = aws_cognito_user_pool.this.arn
}

output "app_client_id" {
  value = aws_cognito_user_pool_client.operator.id
}

output "domain" {
  description = "Managed login domain host, for ATESTA_STAFF_COGNITO_DOMAIN."
  value       = "${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
}
