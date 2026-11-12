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
