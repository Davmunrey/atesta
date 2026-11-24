"""`atesta-worker`: run the job worker against ATESTA_DATABASE_URL as atesta_app."""

import os

from atesta_api.modules.notifications.api import configure_mail, mail_config_from_env
from atesta_api.platform.db import make_engine
from atesta_api.platform.guard import assert_safe_runtime_role

from atesta_worker import context, file_scans
from atesta_worker.app import build_app
from atesta_worker.logs import configure_logging
from atesta_worker.scans import config_from_env, configure_scans


def main() -> None:
    configure_logging()  # INFO events such as scan.finished reach stdout (issue 452)
    url = os.environ["ATESTA_DATABASE_URL"]
    sslmode = os.environ.get("ATESTA_DB_SSLMODE", "verify-full")
    engine = make_engine(url, sslmode=sslmode)
    assert_safe_runtime_role(engine, require_tls=sslmode != "disable")
    context.configure(engine)
    configure_scans(config_from_env(os.environ))
    configure_mail(mail_config_from_env(os.environ))  # none configured: nothing is sent
    file_scans.configure(file_scans.config_from_env(os.environ))  # none: the poll does nothing
    build_app(url, sslmode).run_worker()


if __name__ == "__main__":
    main()
