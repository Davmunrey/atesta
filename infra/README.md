# infra

OpenTofu for AWS eu-south-2 (Spain), ADR-007.

```text
infra/
  modules/        network, ecs, rds, s3-evidence, kms, cognito, ses
  envs/dev/
  envs/prod/
```

Accounts: management, prod, dev (log archive from month 6). Deploys from GitHub Actions via
OIDC, no long-lived keys. Budget alerts at 150, 250 and 400 EUR/month.

## Status (2026-11-13)

`modules/cognito`, `modules/github-oidc` and `envs/dev` follow docs/specs/infra-dev.md. Nothing
is applied: the owner postponed AWS. CI runs `tofu fmt`, `tofu validate` and the HCL checks in
`tests/`. Local sign-in works meanwhile with `apps/api/devtools/fake_cognito.py`.

First apply, once the dev account exists (owner, with IAM Identity Center credentials):

```bash
cd infra/envs/dev
tofu init -backend-config="bucket=<state bucket>"
tofu apply -var state_bucket=<state bucket> -var budget_email=<alerts address>
```
