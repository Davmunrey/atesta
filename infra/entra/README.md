# Entra app registrations

`scanner-app/<env>.json` is the `requiredResourceAccess` of the "Atesta Scanner" app registration
in that environment (scanner-connectors spec, rule 1). A unit test
(`packages/core/tests/test_readonly.py`) fails if it differs from the expected set of the current
allowlist version in `atesta_core.connectors.readonly`, and the live golden reads the live
registration through Graph and fails likewise.

Until the owner creates the dev registration (owner step for PR 8), `dev.json` is the intended
registration, generated from the allowlist. Once it exists, replace it with the export:

```bash
az ad app show --id <scanner app id> --query "{requiredResourceAccess: requiredResourceAccess}" \
  > infra/entra/scanner-app/dev.json
```

Configure the registration from this file, never from Microsoft's "least privileged" column.
