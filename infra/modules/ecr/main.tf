# Image registries (hosted-environment spec): created before the services, because images are
# pushed first and the ECS module takes them pinned by digest. Tags are immutable and every push
# is scanned.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

resource "aws_ecr_repository" "this" {
  for_each             = toset(["api", "worker", "scan", "egress", "operator"])
  name                 = "${var.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }
}

# Keep the last 30 images per repository so rollbacks stay possible and storage stays bounded.
resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 30 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 30 }
      action       = { type = "expire" }
    }]
  })
}

output "repository_urls" {
  value = { for k, repo in aws_ecr_repository.this : k => repo.repository_url }
}
