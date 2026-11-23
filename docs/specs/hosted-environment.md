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

## To verify before building (candidates, not facts)

Each is checked against official AWS documentation, and the source URL is recorded in the module or
runbook:

- every service used is available in eu-south-2: ECS Fargate, RDS for PostgreSQL 16, Secrets
  Manager, CloudWatch Logs, Application Load Balancer, KMS, S3, and the VPC endpoints needed;
- CloudFront, which is global, and where it processes data with respect to ADR-007 amendment 1;
- which of these services are within AWS's ENS High certification scope (ADR-007);
- the NAT gateway versus VPC endpoints cost for this traffic.

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
