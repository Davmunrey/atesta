"""Operator portal staff rows, from a local checkout (runbook "Staff accounts").

    uv run python -m apps.api.devtools.operator_staff add --email <e> --sub <sub> --role support \
        --by <admin email> --reason "<why, ticket>"
    uv run python -m apps.api.devtools.operator_staff disable --email <e> --by <admin> \
        --reason "..."

Connects with ATESTA_MIGRATION_DATABASE_URL as atesta_owner. The command lives in the API image as
`atesta_api.ops.staff`, which the hosted runbook runs as an ECS task; this is the same command.
"""

from atesta_api.ops.staff import main

if __name__ == "__main__":
    main()
