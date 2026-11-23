# Sub-processors (draft for the DPA)

- **Status:** draft, 2026-11-23. Nothing runs in production yet (the owner postponed AWS). Legal
  review and the owner's sign-off are required before this list is published or attached to a DPA
  (ROADMAP, "Only a human can do").
- **Source of truth:** ADR-007 and its amendments 1 (EU residency) and 2 (CloudFront), and the infrastructure in
  `infra/`. Any change to either must update this file in the same pull request.

## Sub-processors that will process customer personal data

| Sub-processor | Service | Region | Customer personal data | Purpose |
| --- | --- | --- | --- | --- |
| Amazon Web Services (entity to confirm) | RDS for PostgreSQL, ECS (Fargate), S3, KMS, Secrets Manager, CloudWatch | eu-south-2 (Spain) | Members' names and email addresses, the organization's records (assessments, evidence statements, reviews, audit events), connection metadata | Hosting, storage, encryption and operation of the service |
| Amazon Web Services (entity to confirm) | Amazon Cognito | eu-south-2 (Spain) | Members' email addresses and sign-in credentials | Sign-in and multi-factor authentication |
| Amazon Web Services (entity to confirm) | Amazon SES, used by Cognito for its emails | eu-west-3 (Paris) | Members' email addresses, verification and reset codes | Account emails; the eu-south-2 user pool cannot use SES in its own region (ADR-007 amendment 1) |
| Amazon Web Services (entity to confirm) | Amazon CloudFront | Global edge locations (Europe and North America), transit only | Requests and responses of signed-in members in transit, including session cookies; nothing cached or stored for the API | Serves the web app and carries its API traffic to eu-south-2 over TLS (ADR-007 amendment 2) |

The contracting AWS entity and its transfer terms must be confirmed against the AWS customer
agreement and the AWS GDPR DPA when the account exists.

## Not sub-processors

- **Customers' own Microsoft 365 and Google Workspace tenants.** Atesta reads them with read-only
  consent granted by the customer. They are sources the customer controls, not services Atesta
  engages.
- **GitHub.** It hosts source code and CI. No customer data is stored there (CLAUDE.md rule 2,
  ADR-015).
- **AI services.** None is in use. The cited AI assistant (ADR-010) is on the roadmap as "Later".
  Before any customer data reaches an AI service, that service must be added here and to ADR-007
  as an EU-only exception.
