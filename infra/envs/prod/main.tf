# Prod environment (hosted-environment spec): the same platform module as dev with prod sizes,
# in its own account and state bucket. Cognito sends email through SES in eu-west-3, the one EU
# exception in ADR-007 amendment 1. Nothing is applied until the owner decides.

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
    key          = "prod/terraform.tfstate"
    region       = "eu-south-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-south-2"
  default_tags {
    tags = { project = "atesta", env = "prod", managed_by = "opentofu" }
  }
}

provider "aws" {
  alias  = "paris"
  region = "eu-west-3"
  default_tags {
    tags = { project = "atesta", env = "prod", managed_by = "opentofu" }
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

variable "app_url" {
  description = "Public origin of the app, for example https://app.example.com (owner's domain)."
  type        = string
}

variable "cognito_mail_domain" {
  description = "Domain Cognito sends from, verified in SES eu-west-3."
  type        = string
}

variable "cognito_from" {
  description = "From address for Cognito email, for example Atesta <no-reply@example.com>."
  type        = string
}

module "ses_cognito" {
  source    = "../../modules/ses"
  providers = { aws = aws.paris }
  name      = "atesta-prod-cognito"
  domain    = var.cognito_mail_domain
}

module "cognito" {
  source                = "../../modules/cognito"
  name                  = "atesta-prod"
  domain_prefix         = "atesta-prod"
  callback_urls         = ["${var.app_url}/auth/callback"]
  logout_urls           = ["${var.app_url}/"]
  email_sending_account = "DEVELOPER"
  ses_source_arn        = module.ses_cognito.identity_arn
  from_email_address    = var.cognito_from
}

module "github_oidc" {
  source            = "../../modules/github-oidc"
  repository        = "Davmunrey/atesta"
  state_bucket      = var.state_bucket
  apply_environment = "prod"
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

# Hosted environment (hosted-environment spec): prod sizes. Nothing is applied until the owner
# decides. images, edge and mail_domain stay null until images are pushed and the owner has a
# domain and certificates (docs/runbooks/deploy.md); until then only the base layer is planned.
variable "images" {
  type    = object({ api = string, worker = string, scan = string })
  default = null
}

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

variable "mail_domain" {
  type    = string
  default = null
}

module "platform" {
  source                = "../../modules/platform"
  name                  = "atesta-prod"
  multi_az              = true
  backup_retention_days = 35
  nat_per_az            = true
  api_count             = 2
  worker_count          = 1
  images                = var.images
  edge                  = var.edge
  app_environment       = var.app_environment
  mail_domain           = var.mail_domain
}

output "platform" {
  value = {
    database_endpoint = module.platform.database_endpoint
    ecr_repositories  = module.platform.ecr_repositories
    api_load_balancer = module.platform.api_load_balancer
    web               = module.platform.web
    mail_dns_records  = module.platform.mail_dns_records
    cognito_dns       = module.ses_cognito.dns_records
  }
}
