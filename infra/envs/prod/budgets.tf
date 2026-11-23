# Budget alerts at 150, 250 and 400 (Infrastructure tab). Amounts are in the account's billing
# currency; AWS Budgets reports in USD unless the payer account bills in another currency.

resource "aws_budgets_budget" "monthly" {
  name         = "atesta-prod-monthly"
  budget_type  = "COST"
  limit_amount = "400"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = toset(["150", "250", "400"])
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = tonumber(notification.value)
      threshold_type             = "ABSOLUTE_VALUE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.budget_email]
    }
  }
}
