# PostgreSQL 16 (hosted-environment spec): encrypted with the database key, private subnets only,
# TLS required, master password managed by RDS in Secrets Manager. The application roles
# (atesta_owner for migrations, atesta_app at runtime) come from apps/api/migrations/bootstrap.sql,
# run once by the deploy runbook as the master user; their connection URLs live in two secrets
# whose values are set out of band, never in code or state.

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

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "app_security_group_id" {
  description = "Security group of the API, worker and migration tasks: the only clients."
  type        = string
}

variable "kms_key_arn" {
  description = "Database key: storage, snapshots and the master user secret."
  type        = string
}

variable "secrets_key_arn" {
  type = string
}

variable "logs_key_arn" {
  type = string
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "allocated_storage_gb" {
  type    = number
  default = 20
}

variable "max_allocated_storage_gb" {
  type    = number
  default = 100
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "backup_retention_days" {
  description = "14 in dev, 35 in prod (the RDS maximum)."
  type        = number
  default     = 14
  validation {
    condition     = var.backup_retention_days >= 14 && var.backup_retention_days <= 35
    error_message = "Keep backups between 14 and 35 days."
  }
}

variable "log_retention_days" {
  type    = number
  default = 365
}

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "db" {
  name        = "${var.name}-db"
  description = "PostgreSQL, reachable only from the application tasks"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "from_app" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = var.app_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_parameter_group" "this" {
  name   = "${var.name}-pg16"
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  # Statement text and bind values may carry customer data (rule 2): log errors and
  # connections, never statements.
  parameter {
    name  = "log_statement"
    value = "none"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "-1"
  }
  parameter {
    name  = "log_connections"
    value = "1"
  }
}

resource "aws_cloudwatch_log_group" "postgres" {
  name              = "/aws/rds/instance/${var.name}/postgresql"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.logs_key_arn
}

resource "aws_db_instance" "this" {
  identifier            = var.name
  engine                = "postgres"
  engine_version        = "16"
  instance_class        = var.instance_class
  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = var.max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  db_name                             = "atesta"
  username                            = "atesta_master"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = var.kms_key_arn
  iam_database_authentication_enabled = false

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  parameter_group_name   = aws_db_parameter_group.this.name
  multi_az               = var.multi_az

  backup_retention_period    = var.backup_retention_days
  backup_window              = "02:00-03:00"
  maintenance_window         = "sun:03:30-sun:04:30"
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  deletion_protection        = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = "${var.name}-final"

  enabled_cloudwatch_logs_exports = ["postgresql"]
  depends_on                      = [aws_cloudwatch_log_group.postgres]
}

# Connection URLs for the two application roles. Values are written once by the runbook after
# bootstrap.sql sets each role's password; tasks read them through ECS secrets.
resource "aws_secretsmanager_secret" "app_url" {
  name        = "atesta/${var.name}/db/app-url"
  description = "ATESTA_DATABASE_URL for atesta_app"
  kms_key_id  = var.secrets_key_arn
}

resource "aws_secretsmanager_secret" "migration_url" {
  name        = "atesta/${var.name}/db/migration-url"
  description = "ATESTA_MIGRATION_DATABASE_URL for atesta_owner (migration task only)"
  kms_key_id  = var.secrets_key_arn
}

output "endpoint" {
  value = aws_db_instance.this.address
}

output "master_secret_arn" {
  value = aws_db_instance.this.master_user_secret[0].secret_arn
}

output "app_url_secret_arn" {
  value = aws_secretsmanager_secret.app_url.arn
}

output "migration_url_secret_arn" {
  value = aws_secretsmanager_secret.migration_url.arn
}

output "security_group_id" {
  value = aws_security_group.db.id
}
