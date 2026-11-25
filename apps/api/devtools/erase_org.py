"""Erase an organization through its approved erasure request (operator-portal spec, "Erasure").

    uv run python -m apps.api.devtools.erase_org --request <id>            # dry run
    uv run python -m apps.api.devtools.erase_org --request <id> --execute
    uv run python -m apps.api.devtools.erase_org --pending --execute

Connects with ATESTA_MIGRATION_DATABASE_URL and acts as atesta_owner, the only role that may
delete append-only rows (ADR-012). The command lives in the API image as `atesta_api.ops.erase`,
which the scheduled erasure runner and the hosted runbook call; this is the same command for a
local checkout. Follow docs/runbooks/offboarding.md.
"""

from atesta_api.ops.erase import main

if __name__ == "__main__":
    main()
