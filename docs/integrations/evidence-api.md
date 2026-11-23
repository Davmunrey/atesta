# Recording evidence from your tools

Spec: [`evidence-ingestion-api`](../specs/evidence-ingestion-api.md).

An admin creates a token in **Integraciones**. The token can only record evidence; it cannot read
anything. Store it as a secret in the tool that uses it, and revoke it when that tool no longer
needs it.

## Request

```
POST /api/v1/ingest/evidence
Authorization: Bearer atesta_…
Content-Type: application/json

{
  "control": "ctl.continuity_restore",
  "title": "Restore test",
  "statement": "Nightly restore of the billing database succeeded in 14 minutes.",
  "source": "github-actions",
  "reference_url": "https://github.com/acme/infra/actions/runs/123",
  "external_id": "restore-123"
}
```

**Fields:**
- `control`: a common control key (see `catalog/controls/`).
- `title`: up to 200 characters.
- `statement`: up to 4000 characters.
- `source`: names the tool, up to 50 characters.
- `reference_url`: optional; HTTPS only.
- `external_id`: optional; makes retries safe.

**Responses:**
- `201` with `{"evidence_id": "…", "duplicate": false}`.
- `200` with `"duplicate": true` when the same token already sent that `external_id`. Nothing new is written.
- `401` `identity.api_token_invalid`: the token is missing, unknown, revoked or expired.
- `422` `evidence.control_not_found`: the control is unknown or retired; other `422`s mean invalid fields.
- `400`: the request had a query string. Tokens never go in URLs.

## GitHub Actions

```yaml
- name: Record the restore test in Atesta
  if: success()
  env:
    ATESTA_URL: ${{ vars.ATESTA_URL }}  # your Atesta address
    ATESTA_TOKEN: ${{ secrets.ATESTA_TOKEN }}
  run: |
    curl --fail-with-body -sS -X POST "${ATESTA_URL}/api/v1/ingest/evidence" \
      -H "Authorization: Bearer ${ATESTA_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"control\": \"ctl.continuity_restore\", \"title\": \"Restore test\",
           \"statement\": \"Restore of ${GITHUB_REPOSITORY} passed.\",
           \"source\": \"github-actions\",
           \"reference_url\": \"${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}\",
           \"external_id\": \"${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}\"}"
```

## What Atesta does with it

- **Where the statement appears:** on the control, with source `api` and the token's name. Its
  author is the admin who created the token.
- **The token's last use** is shown in Integraciones.
- **Audit log:** every write is an `evidence.ingested` event.
- **No decisions:** the statement is evidence for a reviewer. Atesta does not decide pass or fail
  from it (ADR-005).
