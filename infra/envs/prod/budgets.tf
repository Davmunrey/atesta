# Prod budget alerts at 250, 350 and 450 (owner, 2026-11-23, #286): the runbook estimates prod
# at about 228 USD a month, so dev's 150 and 250 would fire every month. Amounts are in the
# account's billing currency; AWS Budgets reports in USD unless the payer bills in another.

resource "aws_budgets_budget" "monthly" {
  name         = "atesta-prod-monthly"
  budget_type  = "COST"
  limit_amount = "450"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = toset(["250", "350", "450"])
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = tonumber(notification.value)
      threshold_type             = "ABSOLUTE_VALUE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.budget_email]
    }
  }
}
