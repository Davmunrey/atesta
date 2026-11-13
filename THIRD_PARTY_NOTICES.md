# Third-party notices

| Component | License | Use |
| --- | --- | --- |
| Prowler (prowler-cloud/prowler) | Apache-2.0 | Scan engine, pinned version in `scanner/Dockerfile`. LICENSE and NOTICE retained in the image. |
| psycopg, psycopg-binary, psycopg-pool | LGPL-3.0-only | Postgres driver, used unmodified as installed libraries (ADR-006 amendment 1). |
| certifi (via httpx) | MPL-2.0 | CA bundle, used unmodified; file-level copyleft only. |
| obra/superpowers skills (3) | MIT | Agent skills vendored in `.claude/skills/`, not shipped in any service (ADR-013). |

Policy: no AGPL or GPL dependencies in network-facing services; unmodified LGPL libraries are
allowed (ADR-006).
