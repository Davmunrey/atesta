# Cognito user pool for Atesta (identity-auth and infra-dev specs). Username settings are
# immutable after creation, so every one of them is fixed here and asserted by
# infra/tests/test_cognito_module.py.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.73.0"
    }
  }
}

locals {
  es = jsondecode(file("${path.module}/../../i18n/cognito.es.json"))
  en = jsondecode(file("${path.module}/../../i18n/cognito.en.json"))
}

resource "aws_cognito_user_pool" "this" {
  name                     = var.name
  user_pool_tier           = "ESSENTIALS"
  deletion_protection      = "ACTIVE"
  mfa_configuration        = "ON"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  software_token_mfa_configuration {
    enabled = true
  }

  username_configuration {
    case_sensitive = false
  }

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  # Required, so every app client can write it at sign-up without a write grant (AWS docs,
  # "Attribute permissions and scopes").
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
    string_attribute_constraints {
      min_length = 3
      max_length = 320
    }
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
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
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "${local.es.verification_subject} / ${local.en.verification_subject}"
    email_message        = "${local.es.verification_message}\n\n${local.en.verification_message}"
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain                = var.domain_prefix
  user_pool_id          = aws_cognito_user_pool.this.id
  managed_login_version = 2
}

resource "aws_cognito_user_pool_client" "web" {
  name                                 = "${var.name}-web"
  user_pool_id                         = aws_cognito_user_pool.this.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls
  read_attributes                      = ["email", "email_verified"]
  # Never empty: an unset WriteAttributes grants write on every attribute. Email stays out.
  write_attributes              = ["name"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  access_token_validity         = 30
  id_token_validity             = 30
  refresh_token_validity        = 12

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "hours"
  }
}

resource "aws_cognito_managed_login_branding" "web" {
  client_id                   = aws_cognito_user_pool_client.web.id
  user_pool_id                = aws_cognito_user_pool.this.id
  use_cognito_provided_values = true
}
