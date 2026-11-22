# Dev environment (infra-dev spec). First apply from a laptop with IAM Identity Center
# credentials; afterwards CI plans with the plan role and applies from the protected
# environment. AWS is postponed by the owner (2026-11-13): nothing has been applied yet.

terraform {
  required_version = "= 1.13.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.73.0"
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
