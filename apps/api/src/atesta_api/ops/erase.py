"""Erase organizations whose erasure was requested and approved (operator-portal spec, "Erasure").

    python -m atesta_api.ops.erase --request <id>           # dry run: what would be deleted
    python -m atesta_api.ops.erase --request <id> --execute
    python -m atesta_api.ops.erase --pending --execute      # the scheduled runner (#502)

There is one erasure implementation, `identity.api.run_erasure_request`. It refuses a request that
is unknown, not approved, cancelled, already executed, or whose closure date has not passed, so
nothing is erased without a second admin's approval (or a sole admin's after 72 hours) and the
30-day closure. Each request runs in its own transaction. The last line is the run's outcome,
`{"event": "erasure.run", "status": "finished" | "failed"}`, which the alarm counts (infra,
modules/ecs/runner.tf); a refusal or an error exits non-zero.
"""

import argparse
import json
import sys
import uuid

from atesta_api.modules.identity.api import (
    ErasureRefusedError,
    due_erasure_requests,
    run_erasure_request,
)
from atesta_api.ops import owner_engine


def _emit(**event: object) -> None:
    print(json.dumps(event), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--request", type=uuid.UUID, help="one erasure request id")
    which.add_argument("--pending", action="store_true", help="every approved, due request")
    parser.add_argument("--execute", action="store_true", help="delete; without it, a dry run")
    args = parser.parse_args()
    engine = owner_engine()
    code = 0
    try:
        if args.pending:
            with engine.begin() as conn:
                conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
                requests = due_erasure_requests(conn)
        else:
            requests = [args.request]
        for request in requests:
            with engine.begin() as conn:
                conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
                run = run_erasure_request(conn, request, execute=args.execute)
            _emit(
                event="erasure.executed" if args.execute else "erasure.dry_run",
                request=str(run.request_id),
                organization=str(run.organization_id),
                receipt=None if run.receipt_id is None else str(run.receipt_id),
                rows=run.rows,
            )
    except ErasureRefusedError as refused:
        print(f"refused: {refused}", file=sys.stderr)
        code = 2
    except Exception as error:  # the run's outcome is still logged, without the message
        print(f"error: {type(error).__name__}", file=sys.stderr)
        code = 1
    finally:
        engine.dispose()
    _emit(event="erasure.run", status="finished" if code == 0 else "failed")
    sys.exit(code)


if __name__ == "__main__":
    main()
