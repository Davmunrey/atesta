# Dev environment (infra-dev spec). First apply from a laptop with IAM Identity Center
# credentials; afterwards CI plans with the plan role and applies from the protected
# environment. AWS is postponed by the owner (2026-11-13): nothing has been applied yet.

terraform {
  required_version = "= 1.13.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
  # Partial config: pass -backend-config="bucket=<state bucket>" at init.
  backend "s3" {
    key          = "dev/terraform.tfstate"
    region       = "eu-south-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-south-2"
  default_tags {
    tags = { project = "atesta", env = "dev", managed_by = "opentofu" }
  }
}

variable "state_bucket" {
  type = string
}

variable "budget_email" {
  description = "Address for budget alerts. Set in an untracked tfvars file, never in git."
  type        = string
  sensitive   = true
}

module "cognito" {
  source        = "../../modules/cognito"
  name          = "atesta-dev"
  domain_prefix = "atesta-dev"
  callback_urls = ["http://localhost:3000/auth/callback"]
  logout_urls   = ["http://localhost:3000/"]
}

module "github_oidc" {
  source       = "../../modules/github-oidc"
  repository   = "Davmunrey/atesta"
  state_bucket = var.state_bucket
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_app_client_id" {
  value = module.cognito.app_client_id
}

output "cognito_domain" {
  value = module.cognito.domain
}

# Hosted environment, base layer (hosted-environment spec). Nothing is applied until the owner
# decides; a plan shows what an apply would create.
module "kms" {
  source = "../../modules/kms"
  name   = "atesta-dev"
}

module "network" {
  source       = "../../modules/network"
  name         = "atesta-dev"
  logs_key_arn = module.kms.logs_key_arn
}

module "evidence" {
  source      = "../../modules/s3-evidence"
  bucket_name = "atesta-dev-evidence-${data.aws_caller_identity.current.account_id}"
  kms_key_arn = module.kms.evidence_key_arn
}

# The API, worker and migration tasks share this group; the ECS module (next PR) attaches it.
resource "aws_security_group" "app" {
  name        = "atesta-dev-app"
  description = "Application tasks: the only clients of the database"
  vpc_id      = module.network.vpc_id
}

module "database" {
  source                = "../../modules/rds"
  name                  = "atesta-dev"
  vpc_id                = module.network.vpc_id
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = aws_security_group.app.id
  kms_key_arn           = module.kms.database_key_arn
  secrets_key_arn       = module.kms.secrets_key_arn
  logs_key_arn          = module.kms.logs_key_arn
  multi_az              = false
  backup_retention_days = 14
}

module "ecr" {
  source      = "../../modules/ecr"
  name        = "atesta-dev"
  kms_key_arn = module.kms.secrets_key_arn
}

# Services come up once images are pushed (pinned by digest); until then images stays null and
# only the base layer is planned.
variable "images" {
  type    = object({ api = string, worker = string, scan = string })
  default = null
}

variable "app_environment" {
  description = "Plain settings (ATESTA_ENV, Cognito ids, web origin). Never secrets."
  type        = map(string)
  default     = {}
}

resource "aws_secretsmanager_secret" "session_key" {
  name        = "atesta/atesta-dev/api/session-key"
  description = "ATESTA_SESSION_KEY (base64, 32 bytes), set by hand"
  kms_key_id  = module.kms.secrets_key_arn
}

module "ecs" {
  source                = "../../modules/ecs"
  count                 = var.images == null ? 0 : 1
  name                  = "atesta-dev"
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  private_subnet_ids    = module.network.private_subnet_ids
  app_security_group_id = aws_security_group.app.id
  db_security_group_id  = module.database.security_group_id
  logs_key_arn          = module.kms.logs_key_arn
  secrets_key_arn       = module.kms.secrets_key_arn
  evidence_bucket_arn   = module.evidence.bucket_arn
  images                = var.images
  environment           = var.app_environment
  secrets = {
    api = {
      ATESTA_DATABASE_URL = module.database.app_url_secret_arn
      ATESTA_SESSION_KEY  = aws_secretsmanager_secret.session_key.arn
    }
    worker  = { ATESTA_DATABASE_URL = module.database.app_url_secret_arn }
    migrate = { ATESTA_MIGRATION_DATABASE_URL = module.database.migration_url_secret_arn }
  }
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
  source = "../../modules/ses"
  count  = var.mail_domain == null ? 0 : 1
  name   = "atesta-dev-notifications"
  domain = var.mail_domain
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "mail_dns_records" {
  value = try(module.ses_notifications[0].dns_records, [])
}

data "aws_caller_identity" "current" {}
