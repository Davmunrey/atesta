# The operator service (ADR-017, "Deployment"; operator-portal spec, build step 6): its own
# image, task and execution roles, security group, log group and target group. It shares the
# cluster and the load balancer with the API, but a request reaches it only through the admin
# distribution, which adds a header whose value is a hand-set secret; the API's distribution never
# sends it (AWS CloudFront developer guide, "Restrict access to Application Load Balancers", read
# 2026-11-25). The customer API, worker and migrations hold none of its credentials.

variable "operator" {
  description = "Staff pool ARN and the operator's plain settings (never secrets)."
  type = object({
    staff_pool_arn = string
    environment    = map(string)
  })
  validation {
    condition     = alltrue([for k in keys(var.operator.environment) : !can(regex("(DATABASE_URL|_KEY|SECRET|PASSWORD|TOKEN)$", k))])
    error_message = "Secrets go in var.secrets.operator (Secrets Manager), never in plain environment."
  }
}

variable "operator_origin_header" {
  description = "Value of the header only the admin distribution sends (secret atesta/<env>/operator/origin-header)."
  type        = string
  sensitive   = true
}

locals {
  operator_header = "X-Atesta-Operator-Origin"
  # Only the operator's execution role resolves these.
  operator_secret_arns = distinct([
    for ref in values(var.secrets.operator) :
    regex("^arn:aws:secretsmanager:[^:]+:[0-9]+:secret:[^:]+", ref)
  ])
}

# --- IAM: its own execution role (its secrets only) and task role (the MFA check only) -------

data "aws_iam_policy_document" "operator_execution" {
  statement {
    sid       = "ReadOperatorSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.operator_secret_arns
  }
  statement {
    sid       = "DecryptSecretsAndImages"
    actions   = ["kms:Decrypt"]
    resources = [var.secrets_key_arn]
  }
}

resource "aws_iam_role" "operator_execution" {
  name               = "${var.name}-operator-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks.json
}

resource "aws_iam_role_policy_attachment" "operator_execution_managed" {
  role       = aws_iam_role.operator_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "operator_execution" {
  role   = aws_iam_role.operator_execution.id
  policy = data.aws_iam_policy_document.operator_execution.json
}

# Startup reads the staff pool's MFA settings and refuses an unsafe pool (apps/operator, mfa.py).
# GetUserPoolMfaConfig is a Read action on the userpool resource type (Service Authorization
# Reference, Amazon Cognito User Pools, read 2026-11-25).
data "aws_iam_policy_document" "operator" {
  statement {
    sid       = "StaffPoolMfaCheck"
    actions   = ["cognito-idp:GetUserPoolMfaConfig"]
    resources = [var.operator.staff_pool_arn]
  }
}

resource "aws_iam_role" "operator" {
  name               = "${var.name}-operator"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks.json
}

resource "aws_iam_role_policy" "operator" {
  role   = aws_iam_role.operator.id
  policy = data.aws_iam_policy_document.operator.json
}

# --- Network: in from the load balancer, out to Postgres and HTTPS (Cognito, AWS APIs) -------

resource "aws_security_group" "operator" {
  name        = "${var.name}-operator"
  description = "Operator service: from the load balancer only"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "operator_from_alb" {
  security_group_id            = aws_security_group.operator.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8001
  to_port                      = 8001
}

resource "aws_vpc_security_group_egress_rule" "alb_to_operator" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.operator.id
  ip_protocol                  = "tcp"
  from_port                    = 8001
  to_port                      = 8001
}

resource "aws_vpc_security_group_egress_rule" "operator_https" {
  security_group_id = aws_security_group.operator.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "operator_db" {
  security_group_id            = aws_security_group.operator.id
  referenced_security_group_id = var.db_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "db_from_operator" {
  security_group_id            = var.db_security_group_id
  referenced_security_group_id = aws_security_group.operator.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

# --- Routing: only requests carrying the admin distribution's header --------------------------

resource "aws_lb_target_group" "operator" {
  name        = "${var.name}-operator"
  port        = 8001
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path    = "/health"
    matcher = "200"
  }
}

resource "aws_lb_listener_rule" "operator" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  condition {
    http_header {
      http_header_name = local.operator_header
      values           = [var.operator_origin_header]
    }
  }
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.operator.arn
  }
}

# --- Task and service -------------------------------------------------------------------------

resource "aws_ecs_task_definition" "operator" {
  family                   = "${var.name}-operator"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.operator_execution.arn
  task_role_arn            = aws_iam_role.operator.arn
  container_definitions    = jsonencode([merge(local.containers.operator, { name = "operator", essential = true })])
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  volume {
    name = "tmp"
  }
}

resource "aws_ecs_service" "operator" {
  name            = "${var.name}-operator"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.operator.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.operator.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.operator.arn
    container_name   = "operator"
    container_port   = 8001
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  depends_on = [aws_lb_listener_rule.operator]
}

output "operator_origin_header_name" {
  value = local.operator_header
}
