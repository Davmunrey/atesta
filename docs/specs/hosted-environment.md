# Spec: hosted environment, ready to deploy

- Issue: #202. Builds on `infra-dev.md`, ADR-003, ADR-004, ADR-007 (and amendment 1), ADR-012.
- Status: draft. Nothing is applied: the owner postponed AWS until after the 2026-12-18 go/no-go
  and asked for everything to be ready to deploy in a day (2026-11-23).

## Problem

Pilots and the first customers need Atesta hosted in AWS eu-south-2. Today only the Cognito pool,
GitHub OIDC and budgets exist as code, for dev. Writing, reviewing and validating the rest can
happen now, at no cost. Applying it is the owner's decision.

## Acceptance criteria

- [ ] **Modules in `infra/modules/`.** Each is validated by `tofu validate`, and pytest asserts its
  security settings:
  - **`kms`:** customer-managed keys for the database, the evidence bucket and logs.
  - **`network`:** a VPC across two availability zones. Containers and the database sit in private
    subnets, and nothing in them takes inbound traffic from the internet. Outbound access is
    either through VPC endpoints for AWS services or through a NAT gateway; the choice is
    recorded with its cost.
  - **`rds`:** PostgreSQL 16, encrypted with the database key, not publicly accessible, TLS
    required. Backups are kept 14 days in dev and 35 in prod; prod is Multi-AZ. The database
    roles follow `bootstrap.sql` (`atesta_owner` for migrations, `atesta_app` for runtime).
    A one-off `bootstrap` task (API image, `python -m atesta_api.platform.db_bootstrap`) runs
    `bootstrap.sql` as the RDS master user and gives each role LOGIN with the password in its
    own connection-URL secret. The master password reaches the task only as an ECS secret (the
    `password` key of the RDS-managed secret). The task prints role names only, never a password
    or URL, and running it again changes nothing but the passwords.
  - **`ecs`:**
    - The API and the worker run as Fargate services. One task definition per scan follows
      ADR-004, with a task role scoped to that tenant's prefix.
    - Secrets come from Secrets Manager, never from environment files.
    - Logs go to CloudWatch with a retention period; no secrets or customer content (rule 2).
  - **`web`:**
    - The static export lives in a private S3 bucket behind CloudFront with origin access control.
    - `/api/*` and `/auth/*` go to the API's load balancer.
    - A response headers policy carries the CSP built by `scripts/csp.ts`, HSTS, nosniff,
      `Referrer-Policy: same-origin`, and `no-referrer` on `/invite` and `/training`
      (web-shell spec).
  - **`s3-evidence`:** private and encrypted with its key. Versioning is on and public access is
    blocked. Keys use the `<organization_id>/` prefix that the evidence model already checks.
  - **`ses`:** a sending identity for notification email. Where it sits is decided by ADR-007
    amendment 1.
- [ ] **Environments:** `infra/envs/prod` mirrors `dev` with prod sizes. Each has its own state
  bucket and account.
- [ ] **Deploy workflow:**
  - It is triggered manually.
  - It builds the images and the static export, runs migrations as `atesta_owner`, deploys,
    and runs a smoke check.
  - It uses the OIDC roles only (no long-lived keys) and the existing `test_ci_workflow` hardening
    rules (pinned actions, least permissions).
- [ ] **Runbook `docs/runbooks/deploy.md`:** the owner's one-day path. It lists the account steps
  only the owner can take, the first apply, DNS and certificates, the first deploy, smoke tests
  and rollback.
- [ ] **Cost estimate:** a monthly estimate for dev and prod in the runbook, from the AWS Pricing
  Calculator for eu-south-2, checked against the budget alerts (150, 250 and 400 EUR).

## Verified on 2026-11-23

**Available in eu-south-2.** Source: the AWS public regional services table,
\`https://api.regional-table.region-services.aws.a2z.com/index.json\`, which lists the following
in eu-south-2:
- Amazon ECS, Amazon RDS for PostgreSQL (and Aurora PostgreSQL), KMS, S3 and CloudFront;
- Secrets Manager, CloudWatch and CloudWatch Logs, Elastic Load Balancing, SES and ECR;
- Cognito, WAF, ACM, VPC, NAT Gateway, PrivateLink and AWS Backup.

**AWS Fargate.** The ECS guide's Fargate Regions page lists Europe (Spain) eu-south-2 for Linux and
Windows containers:
\`https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate-Regions.html\`.

**ENS High scope.** Source: \`https://aws.amazon.com/compliance/services-in-scope/ENS-High/\`,
last updated 6 November 2025, read in the services table only.
- **Marked in scope:** Amazon ECS, ECR, RDS, KMS, S3, Secrets Manager, CloudWatch, CloudWatch Logs,
  Elastic Load Balancing, SES, Cognito, WAF, ACM and VPC.
- **CloudFront:** in scope with one exclusion, "content delivery through Amazon CloudFront Embedded
  Point of Presence". Atesta does not use that feature.

## Still open

- **Fargate and ENS High:** Fargate is not named separately in the ENS High table, though ECS is.
  The owner should confirm in the ENS High certificate (AWS Artifact, which needs an account)
  whether ECS on Fargate is covered. If it is not, the containers run on ECS with EC2 capacity
  instead.
- **CloudFront and ADR-007 amendment 1:** CloudFront serves from global edge locations. It carries
  the static web app and proxies API traffic. Whether that counts as processing customer data
  outside the EU needs a decision. A web-only distribution with the API served directly from
  eu-south-2 avoids the question.
- **Cost:** compare NAT Gateway with VPC endpoints for this traffic using the AWS Pricing
  Calculator in eu-south-2, at build time.

## Out of scope

- Creating accounts, buying domains, or applying anything (owner).
- WAF rules and per-token rate limits (later, at the edge).

## Test plan

- `tofu fmt -check` and `tofu validate` for every module and environment in CI.
- pytest over the HCL (as `infra/tests` does today):
  - encryption on;
  - no public database;
  - private subnets for tasks;
  - an S3 public access block;
  - log retention set;
  - secrets only from Secrets Manager;
  - headers policy present on CloudFront.
