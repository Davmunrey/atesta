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

# Hosted environment (hosted-environment spec): dev sizes. Nothing is applied until the owner
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

variable "scan_organizations" {
  description = "Customers whose scan roles to create: organization id => connectors. Set in the untracked tfvars."
  type        = map(set(string))
  default     = {}
}

module "platform" {
  source                = "../../modules/platform"
  name                  = "atesta-dev"
  multi_az              = false
  backup_retention_days = 14
  nat_per_az            = false
  api_count             = 1
  worker_count          = 1
  images                = var.images
  edge                  = var.edge
  app_environment       = var.app_environment
  mail_domain           = var.mail_domain
  alert_email           = var.budget_email
  scan_organizations    = var.scan_organizations
}

output "platform" {
  value = {
    database_endpoint = module.platform.database_endpoint
    ecr_repositories  = module.platform.ecr_repositories
    api_load_balancer = module.platform.api_load_balancer
    web               = module.platform.web
    mail_dns_records  = module.platform.mail_dns_records
  }
}

output "deploy" {
  value = module.platform.deploy
}
