# Synthetic OCSF fixtures

Hand-built Prowler 5.49.0 `json-ocsf` output for tests (scanner-connectors spec, golden tests).
No tenant data: tenant ids, domains, resource names and messages are fictitious.

- Check ids, service names, severities and resource types are copied from the check metadata in
  the Prowler 5.49.0 wheel (sha256 `e5ed983e…705`, as in the spec).
- Findings are built with `py_ocsf_models` 0.10.0 `DetectionFinding`, field by field as Prowler's
  `lib/outputs/ocsf/ocsf.py` does; `packages/core/tests/test_ocsf.py` validates every finding
  against that model.

| File | Covers |
|---|---|
| `*/scan.ocsf.json` | PASS, FAIL, MANUAL and a muted FAIL (`status: Suppressed`); services with no findings (every other service) |
| `*/wrong-tenant.ocsf.json` | The scan plus one finding from another tenant (M365 `cloud.org.uid`, Google `cloud.account.uid`) |
| `*/unexpected-check.ocsf.json` | The scan plus one finding whose check id Prowler 5.49.0 does not have |

Tenants: M365 `11111111-1111-4111-8111-111111111111` (`fixture.onmicrosoft.com`), other tenant
`22222222-2222-4222-8222-222222222222`; Google customer `C0fixture1`, other customer `C0fixture2`.
Recorded, anonymized fixtures from the live golden test are added beside these later.
