# Sending identity (hosted-environment spec). The caller picks the region through the provider:
# notification email is sent from eu-south-2; Cognito's own email must use SES in eu-west-3, the
# one exception listed in ADR-007 amendment 1. DNS lives wherever the owner registers the domain,
# so the module outputs the records to publish instead of creating them.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.73.0"
    }
  }
}

variable "domain" {
  description = "Sending domain, for example mail.example.com (decided by the owner)."
  type        = string
}

variable "name" {
  type = string
}

resource "aws_sesv2_configuration_set" "this" {
  configuration_set_name = var.name

  delivery_options {
    tls_policy = "REQUIRE"
  }
  reputation_options {
    reputation_metrics_enabled = true
  }
  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }
}

resource "aws_sesv2_email_identity" "this" {
  email_identity         = var.domain
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name

  dkim_signing_attributes {
    next_signing_key_length = "RSA_2048_BIT"
  }
}

resource "aws_sesv2_email_identity_mail_from_attributes" "this" {
  email_identity         = aws_sesv2_email_identity.this.email_identity
  mail_from_domain       = "bounce.${var.domain}"
  behavior_on_mx_failure = "REJECT_MESSAGE"
}

data "aws_region" "current" {}

output "identity_arn" {
  value = aws_sesv2_email_identity.this.arn
}

output "configuration_set" {
  value = aws_sesv2_configuration_set.this.configuration_set_name
}

# Records the owner publishes: three DKIM CNAMEs, MAIL FROM MX and SPF, and a DMARC policy.
output "dns_records" {
  value = concat(
    [for token in aws_sesv2_email_identity.this.dkim_signing_attributes[0].tokens : {
      type  = "CNAME"
      name  = "${token}._domainkey.${var.domain}"
      value = "${token}.dkim.amazonses.com"
    }],
    [
      {
        type  = "MX"
        name  = "bounce.${var.domain}"
        value = "10 feedback-smtp.${data.aws_region.current.region}.amazonses.com"
      },
      { type = "TXT", name = "bounce.${var.domain}", value = "v=spf1 include:amazonses.com -all" },
      { type = "TXT", name = "_dmarc.${var.domain}", value = "v=DMARC1; p=reject; adkim=s; aspf=s" },
    ],
  )
}
