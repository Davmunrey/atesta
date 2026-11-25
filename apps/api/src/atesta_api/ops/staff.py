"""Staff of the operator portal (operator-portal spec, build step 7; runbook "Staff accounts").

    python -m atesta_api.ops.staff add --email <e> --sub <staff pool sub> --role <role> \\
        --by <admin email> --reason "<why, ticket>"
    python -m atesta_api.ops.staff add --email <e> --sub <sub> --role admin --first --reason "..."
    python -m atesta_api.ops.staff disable|enable --email <e> --by <admin email> --reason "..."

The account lives in the staff Cognito pool, created by an owner step; this sets its row in
`operator_staff`. Every change is written to the operator trail with the enabled admin named by
`--by`. `--first` is the bootstrap: only while no admin is enabled, an admin adds themselves and
the trail names them. The portal's own rules hold: nobody changes their own row, and the last
enabled admin is never disabled. A refusal exits 2 and changes nothing.
"""

import argparse
import json
import sys
import uuid

from sqlalchemy.orm import Session

from atesta_api.modules.identity.api import (
    STAFF_ROLES,
    OperatorError,
    StaffMember,
    add_staff,
    change_staff,
    enabled_admins,
    staff_by_email,
)
from atesta_api.ops import owner_engine
from atesta_api.platform.audit import record_operator


class RefusedError(Exception):
    pass


def _admin(session: Session, email: str) -> StaffMember:
    admin = staff_by_email(session, email)
    if admin is None or admin.role != "admin" or admin.disabled_at is not None:
        raise RefusedError("--by must name an enabled admin")
    return admin


def _apply(session: Session, args: argparse.Namespace) -> tuple[str, StaffMember]:
    if args.command == "add":
        if args.first:
            if args.role != "admin" or enabled_admins(session):
                raise RefusedError("--first adds an admin, and only while no admin is enabled")
        elif args.by is None:
            raise RefusedError("--by is required (or --first for the first admin)")
        actor = None if args.first else _admin(session, args.by)
        added = add_staff(session, cognito_sub=args.sub, email=args.email, role=args.role)
        return "staff.added", actor or added
    actor = _admin(session, args.by)
    target = staff_by_email(session, args.email)
    if target is None:
        raise RefusedError("no staff member with that email")
    try:
        change_staff(session, target.id, actor_id=actor.id, disabled=args.command == "disable")
    except OperatorError as error:
        raise RefusedError(error.code) from None
    return f"staff.{args.command}d", actor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["add", "disable", "enable"])
    parser.add_argument("--email", required=True)
    parser.add_argument("--sub", help="the account's sub in the staff pool (add)")
    parser.add_argument("--role", choices=STAFF_ROLES, help="admin, billing or support (add)")
    parser.add_argument("--by", help="email of the enabled admin making the change")
    parser.add_argument("--first", action="store_true", help="the first admin adds themselves")
    parser.add_argument("--reason", required=True, help="why, and the ticket (1-500 characters)")
    args = parser.parse_args()
    if args.command == "add" and not (args.sub and args.role):
        parser.error("add needs --sub and --role")
    engine = owner_engine()
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("SET LOCAL ROLE atesta_owner")
            session = Session(bind=conn)
            action, actor = _apply(session, args)
            target = staff_by_email(session, args.email)
            if target is None:  # just added or changed in this transaction
                raise RuntimeError("staff row not found")
            record_operator(
                session,
                staff_id=actor.id,
                staff_role=actor.role,
                action=action,
                request_id=f"ops-{uuid.uuid4()}",
                target_id=str(target.id),
                reason=args.reason,
                metadata={"role": target.role},
            )
            session.flush()
    except RefusedError as refused:
        print(f"refused: {refused}", file=sys.stderr)
        sys.exit(2)
    finally:
        engine.dispose()
    print(json.dumps({"event": action, "staff": str(target.id), "role": target.role}))
    sys.exit(0)


if __name__ == "__main__":
    main()
