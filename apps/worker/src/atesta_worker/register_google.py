"""`atesta-register-google`: record an org's Google service accounts (D8, issue 398).

The owner's runbook runs it after creating the org's scan and verifier service accounts and
storing their keys: locally with `uv run`, in AWS as a one-off task of the worker image. It runs
in the org's context with reason `job`, as atesta_app, and moves a `pending_provisioning` Google
connection to `pending_setup`. A command, not a queued job: a credential reference is not an id,
and queue tables carry ids only (ADR-012 amendment 2). It prints ids only; there is no secret to
print, since it takes references, never keys.

Environment: ATESTA_DATABASE_URL (atesta_app) and ATESTA_DB_SSLMODE.
"""

import argparse
import json
import os
import sys
import uuid
from collections.abc import Sequence

from atesta_api.modules.connections.api import (
    ConnectionStateError,
    GoogleServiceAccounts,
    register_google_client,
)
from atesta_api.platform.db import make_engine
from atesta_api.platform.guard import assert_safe_runtime_role
from sqlalchemy.exc import IntegrityError

from atesta_worker import context


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atesta-register-google", description=__doc__)
    for name in ("organization-id", "connection-id"):
        parser.add_argument(f"--{name}", required=True, type=uuid.UUID)
    for name in (
        "client-id",
        "verifier-client-id",
        "unique-id",
        "verifier-unique-id",
        "credential-ref",
        "verifier-credential-ref",
    ):
        parser.add_argument(f"--{name}", required=True)
    return parser


def register(argv: Sequence[str]) -> dict[str, str]:
    """Parse, record, and return the event to print. Raises SystemExit with a reason."""
    args = _parser().parse_args(argv)
    try:
        accounts = GoogleServiceAccounts(
            client_id=args.client_id,
            verifier_client_id=args.verifier_client_id,
            unique_id=args.unique_id,
            verifier_unique_id=args.verifier_unique_id,
            credential_ref=args.credential_ref,
            verifier_credential_ref=args.verifier_credential_ref,
        )
    except ValueError as error:
        raise SystemExit(f"atesta-register-google: {error}") from None
    try:
        with context.org_session(str(args.organization_id)) as session:
            found = register_google_client(
                session, args.organization_id, args.connection_id, accounts
            )
            if found is None:
                raise SystemExit("atesta-register-google: no such connection in this org")
    except ConnectionStateError:
        raise SystemExit(
            "atesta-register-google: the connection is not a Google one waiting for provisioning"
        ) from None
    except IntegrityError:  # the ref CHECKs: another org's secret, or not a reference at all
        raise SystemExit(
            "atesta-register-google: a credential reference is not this org's Google secret"
        ) from None
    return {
        "event": "connection.provisioned",
        "organization_id": str(args.organization_id),
        "connection_id": str(args.connection_id),
    }


def main(argv: Sequence[str] | None = None) -> None:
    url = os.environ["ATESTA_DATABASE_URL"]
    sslmode = os.environ.get("ATESTA_DB_SSLMODE", "verify-full")
    engine = make_engine(url, sslmode=sslmode, null_pool=True)
    assert_safe_runtime_role(engine, require_tls=sslmode != "disable")
    context.configure(engine)
    print(json.dumps(register(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    main()
