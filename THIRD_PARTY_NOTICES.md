# Third-party notices

| Component | License | Use |
| --- | --- | --- |
| Prowler (prowler-cloud/prowler) | Apache-2.0 | Scan engine, pinned version in `scanner/Dockerfile`. LICENSE and NOTICE retained in the image. |
| psycopg, psycopg-binary, psycopg-pool | LGPL-3.0-only | Postgres driver, used unmodified as installed libraries (ADR-006 amendment 1). |
| certifi (via httpx) | MPL-2.0 | CA bundle, used unmodified; file-level copyleft only. |
| obra/superpowers skills (3) | MIT | Agent skills vendored in `.claude/skills/`, not shipped in any service (ADR-013). |
| anthropics/skills frontend-design | Apache-2.0 | Agent skill vendored in `.claude/skills/`, LICENSE.txt kept beside it, not shipped (ADR-013). |
| pbakaus/impeccable (text subset) | Apache-2.0 | Agent skill vendored in `.claude/skills/impeccable/`, LICENSE.txt kept beside it, not shipped (ADR-013). |
| GoogleChrome/modern-web-guidance (text subset) | Apache-2.0 | Agent skill vendored in `.claude/skills/modern-web-guidance/`, LICENSE.txt kept beside it, not shipped (ADR-013). |
| vercel-labs/agent-skills react-best-practices (subset) | MIT | Agent skill vendored in `.claude/skills/`, not shipped (ADR-013). |
| Newsreader, IBM Plex Sans, IBM Plex Mono | OFL-1.1 | Unmodified Latin WOFF2 fonts, self-hosted. Fontsource packages pinned to 5.3.0; copyright, licenses and checksums in `apps/web/src/styles/fonts/`. |

Policy: no AGPL or GPL dependencies in network-facing services; unmodified LGPL libraries are
allowed (ADR-006).
