# Spec: Dev infrastructure for sign-in with MFA

- Requirement ids: FR-01, NFR-03, NFR-04
- Status: draft
- ADRs: ADR-007 (amendment 1), ADR-012, ADR-013
- Build order: after identity-auth; unblocks the week-1 gate "login with MFA works in dev"

## Problem

The API verifies Cognito tokens and the web spec signs users in through Cognito managed login,
but no user pool exists. The week-1 gate needs a dev pool that enforces the identity spec's
settings, created from code so prod later gets the same settings by construction.

## Acceptance criteria

- [ ] OpenTofu in `infra/`, version pinned in `infra/.opentofu-version`, AWS provider pinned in
      `.terraform.lock.hcl`. State in an S3 bucket of the dev account (versioning, SSE-KMS,
      public access blocked) with `use_lockfile = true` (no DynamoDB table).
- [ ] Module `infra/modules/cognito`, used by `infra/envs/dev`, creates in eu-south-2:
  - user pool: `user_pool_tier = "ESSENTIALS"`, `deletion_protection = "ACTIVE"`,
    `mfa_configuration = "ON"`, software token MFA enabled, no SMS configuration,
    `username_attributes = ["email"]`, `username_configuration { case_sensitive = false }`,
    `auto_verified_attributes = ["email"]`, `attributes_require_verification_before_update =
    ["email"]`, account recovery by verified email only, password minimum 12, self sign-up on;
  - prefix domain with `managed_login_version = 2` (no certificate needed for a prefix domain);
  - public app client: no secret, `allowed_oauth_flows = ["code"]`, scopes `openid email`,
    `explicit_auth_flows = ["ALLOW_REFRESH_TOKEN_AUTH"]`, `write_attributes` a non-empty
    list without `email` (an unset list grants write on every attribute; `email` is a required
    schema attribute, which every client may write at sign-up, AWS docs "Attribute permissions
    and scopes", checked 2026-11-13),
    access and ID tokens 30 min, refresh 12 h, callback `http://localhost:8000/auth/callback`
    (the BFF runs in the API, web spec), sign-out `http://localhost:3000/`;
  - `aws_cognito_managed_login_branding` for the client with `use_cognito_provided_values =
    true` until the brand is chosen;
  - email: `COGNITO_DEFAULT` in dev only (builder's own addresses; prod uses SES DEVELOPER in
    eu-west-3, ADR-007 amendment 1).
- [ ] Verification email template text lives in `infra/i18n/cognito.{es,en}.json`, Spanish
      first, English below, read by OpenTofu (rule 11: no Spanish inside `.tf`).
- [ ] GitHub Actions OIDC: provider plus two roles in the dev account. `atesta-dev-plan`
      (read-only, any pull request of this repository) and `atesta-dev-apply` (only the `main`
      branch, behind a protected GitHub environment). No long-lived keys.
- [ ] CI on `infra/**` changes: `tofu fmt -check`, `tofu validate`, and `tofu plan` with the
      plan role. Apply is manual on `main`.
- [ ] A pytest suite parses the module HCL (`python-hcl2`) and asserts every Cognito setting in
      the list above, so a drift in code fails without AWS credentials.
- [ ] AWS Budgets alert at 150, 250 and 400 EUR/month on the dev account (Infrastructure tab).
- [ ] `apps/api/.env.example` lists the four `ATESTA_COGNITO_*` variables with the dev outputs'
      names (no values committed).

## Out of scope

- Prod account and its pool (copy of the module with prod callbacks, SES DEVELOPER, CloudTrail
  trail to S3 with log file validation: prod infra spec, before the first external user).
- RDS, ECS, ALB, S3 + CloudFront for the web (deploy spec). Dev uses local Postgres
  (`compose.yaml`) and runs API and web locally against the dev pool.
- Custom domain and certificates.

## Design notes

### Owner steps (cannot be automated from here)

| Step | Who | Why |
|---|---|---|
| Create the AWS Organization and the dev account; IAM Identity Center with MFA | Owner | Root and billing actions |
| Create the state bucket once (CLI snippet in `infra/README.md`) | Owner | Chicken-and-egg with the backend |
| First `tofu apply` from a laptop with Identity Center credentials | Owner | Creates the OIDC roles CI then uses |
| Sign up in the dev pool, enroll TOTP, sign in through the web | Owner | Week-1 gate, manual by nature |

### Layout

```text
infra/
  .opentofu-version
  modules/cognito/       main.tf, variables.tf, outputs.tf
  modules/github-oidc/
  envs/dev/              backend.tf, main.tf (eu-south-2), budgets.tf
  i18n/cognito.es.json, cognito.en.json
  tests/test_cognito_module.py
```

### Facts checked (2026-11-13)

| Fact | Source |
|---|---|
| `user_pool_tier` takes `LITE`, `ESSENTIALS`, `PLUS`; `deletion_protection` `ACTIVE`/`INACTIVE`; `case_sensitive`; `attributes_require_verification_before_update` must also be in `auto_verified_attributes` | AWS provider docs, `cognito_user_pool` |
| `managed_login_version`: `1` classic hosted UI, `2` managed login; certificate only for custom domains | AWS provider docs, `cognito_user_pool_domain` |
| `aws_cognito_managed_login_branding` with `client_id`, `user_pool_id`, `use_cognito_provided_values` | AWS provider docs |
| S3 backend locking with `use_lockfile = true`, DynamoDB optional | OpenTofu docs, S3 backend |
| A pool in eu-south-2 sends email through SES in eu-west-3 or eu-north-1 | AWS Cognito email Region table (2026-11-13 review) |

## Test plan

| Test | Proves |
|---|---|
| pytest over the HCL: every Cognito setting above, including the absence of SMS config and of the admin scope | Identity spec settings fixed in code |
| `tofu fmt -check`, `tofu validate` in CI | Syntax and provider schema |
| `tofu plan` in CI with the plan role | Changes reviewed before apply |
| Manual: sign-up, TOTP enrollment at the second sign-in, sign-in with TOTP, Spanish pages with `lang=es` | Week-1 gate |
