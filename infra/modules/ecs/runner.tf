# The erasure runner (operator-portal spec, "Erasure" and "Design notes"; ADR-017, "Erase"): a
# one-off task of the erasure task definition (main.tf), started every 6 hours by EventBridge
# Scheduler, which runs in eu-south-2 (AWS General Reference, "Amazon EventBridge Scheduler
# endpoints and quotas", read 2026-11-25). Apart from deploys, it is the only holder of the
# migration credential. It erases only approved requests whose closure date has passed.
#
# Alarms (operator-portal spec, build step 6) go to the alerts topic: a failed run, or no
# finished run in a day; and operator 5xx, or no healthy operator task.

locals {
  erasure_family_arn = "arn:aws:ecs:${local.region}:${local.account}:task-definition/${var.name}-erasure"
}

# Scheduler's execution role: start that task definition on this cluster and pass the shared
# execution role, nothing else. Confused-deputy conditions as AWS recommends for Scheduler
# ("Cross-service confused deputy prevention", read 2026-11-25).
data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = ["arn:aws:scheduler:${local.region}:${local.account}:schedule-group/default"]
    }
  }
}

data "aws_iam_policy_document" "erasure_scheduler" {
  statement {
    sid       = "RunErasure"
    actions   = ["ecs:RunTask"]
    resources = ["${local.erasure_family_arn}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }
  statement {
    sid       = "PassExecutionRole"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "erasure_scheduler" {
  name               = "${var.name}-erasure-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
}

resource "aws_iam_role_policy" "erasure_scheduler" {
  role   = aws_iam_role.erasure_scheduler.id
  policy = data.aws_iam_policy_document.erasure_scheduler.json
}

resource "aws_scheduler_schedule" "erasure" {
  name                = "${var.name}-erasure"
  description         = "Erasure runner: approved erasure requests whose closure date has passed"
  schedule_expression = "rate(6 hours)"
  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn      = aws_ecs_cluster.this.arn
    role_arn = aws_iam_role.erasure_scheduler.arn
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.this["erasure"].arn
      launch_type         = "FARGATE"
      network_configuration {
        subnets          = var.private_subnet_ids
        security_groups  = [var.app_security_group_id]
        assign_public_ip = false
      }
    }
    retry_policy {
      maximum_retry_attempts = 0 # the next run comes in 6 hours; a missed one alarms
    }
  }
}

# Each run ends with {"event": "erasure.run", "status": "finished" | "failed"} (atesta_api.ops.erase).
resource "aws_cloudwatch_log_metric_filter" "erasure" {
  for_each = {
    ErasureRunsFinished = "{ ($.event = \"erasure.run\") && ($.status = \"finished\") }"
    ErasureRunsFailed   = "{ ($.event = \"erasure.run\") && ($.status = \"failed\") }"
  }
  name           = "${var.name}-${each.key}"
  log_group_name = aws_cloudwatch_log_group.this["erasure"].name
  pattern        = each.value
  metric_transformation {
    name      = each.key
    namespace = "Atesta/${var.name}"
    value     = "1"
    unit      = "Count"
  }
}

# Alarms on a failed run, and on a day without a finished one: a task that never started or died
# before its last line logs nothing, so missing data is breaching.
resource "aws_cloudwatch_metric_alarm" "erasure_runner" {
  alarm_name          = "${var.name}-erasure-runner"
  alarm_description   = "The erasure runner failed, or finished no run in 24 h."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  treat_missing_data  = "breaching"
  alarm_actions       = [var.alert_topic_arn]
  metric_query {
    id          = "problem"
    expression  = "IF(FILL(failed, 0) > 0 OR FILL(finished, 0) < 1, 1, 0)"
    label       = "Erasure runner failed or silent"
    return_data = true
  }
  metric_query {
    id = "finished"
    metric {
      namespace   = "Atesta/${var.name}"
      metric_name = "ErasureRunsFinished"
      period      = 86400
      stat        = "Sum"
    }
  }
  metric_query {
    id = "failed"
    metric {
      namespace   = "Atesta/${var.name}"
      metric_name = "ErasureRunsFailed"
      period      = 86400
      stat        = "Sum"
    }
  }
  depends_on = [aws_cloudwatch_log_metric_filter.erasure]
}

# The operator service answered a 5xx, or has no healthy task, in 5 minutes.
resource "aws_cloudwatch_metric_alarm" "operator" {
  alarm_name          = "${var.name}-operator"
  alarm_description   = "The operator service answered 5xx, or no operator task is healthy."
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  treat_missing_data  = "breaching"
  alarm_actions       = [var.alert_topic_arn]
  metric_query {
    id          = "problem"
    expression  = "IF(FILL(errors, 0) > 0 OR FILL(healthy, 0) < 1, 1, 0)"
    label       = "Operator 5xx or no healthy task"
    return_data = true
  }
  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      period      = 300
      stat        = "Sum"
      dimensions  = { TargetGroup = aws_lb_target_group.operator.arn_suffix, LoadBalancer = aws_lb.api.arn_suffix }
    }
  }
  metric_query {
    id = "healthy"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HealthyHostCount"
      period      = 300
      stat        = "Minimum"
      dimensions  = { TargetGroup = aws_lb_target_group.operator.arn_suffix, LoadBalancer = aws_lb.api.arn_suffix }
    }
  }
}
