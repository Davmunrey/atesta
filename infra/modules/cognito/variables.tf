variable "name" {
  description = "User pool name, e.g. atesta-dev."
  type        = string
}

variable "domain_prefix" {
  description = "Cognito prefix domain for managed login (no certificate needed)."
  type        = string
}

variable "callback_urls" {
  description = "OAuth callback URLs: the BFF route /auth/callback on each web origin."
  type        = list(string)
}

variable "logout_urls" {
  description = "Sign-out return URLs."
  type        = list(string)
}

variable "email_sending_account" {
  description = "COGNITO_DEFAULT in dev only; DEVELOPER (SES in eu-west-3) in prod (ADR-007 amendment 1)."
  type        = string
  default     = "COGNITO_DEFAULT"
  validation {
    condition     = contains(["COGNITO_DEFAULT", "DEVELOPER"], var.email_sending_account)
    error_message = "email_sending_account must be COGNITO_DEFAULT or DEVELOPER."
  }
}

variable "ses_source_arn" {
  description = "Verified SES identity ARN, required with DEVELOPER."
  type        = string
  default     = null
}

variable "from_email_address" {
  description = "From address with DEVELOPER email, inside the verified SES domain."
  type        = string
  default     = null
}
