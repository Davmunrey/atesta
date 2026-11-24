"""Frozen operator grants, version 1 (ADR-012 amendment 8, operator-portal spec).

Never edit after merge. The successor of rls_v1.grant() for the second runtime role: grants to
atesta_operator only, from SELECT, INSERT and UPDATE (never DELETE, TRUNCATE, REFERENCES or
TRIGGER), column-level whenever columns are named. It also holds the two grants rls_v1 cannot
express: EXECUTE on the setting functions, which the standard tenant policy calls for every role,
and atesta_app's UPDATE on organizations narrowed to the columns customers change (#445).
"""

import re

_IDENT = re.compile(r"[a-z_][a-z0-9_]*")
_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE"})


def _ident(name: str) -> str:
    if not _IDENT.fullmatch(name):
        raise ValueError(f"bad identifier: {name!r}")
    return name


def grant(table: str, privilege: str, columns: str = "") -> str:
    """One privilege to atesta_operator; on the named columns only, when `columns` is given."""
    if privilege not in _PRIVILEGES:
        raise ValueError(f"privilege must come from {sorted(_PRIVILEGES)}")
    names = [_ident(c) for c in columns.split()]
    on = f" ({', '.join(names)})" if names else ""
    return f"GRANT {privilege}{on} ON {_ident(table)} TO atesta_operator"


SETTING_FUNCTIONS = (
    "GRANT EXECUTE ON FUNCTION app_setting_uuid(text), app_setting_text(text) TO atesta_operator"
)
APP_ORGANIZATIONS_UPDATE = (
    "REVOKE UPDATE ON organizations FROM atesta_app",
    "GRANT UPDATE (name, locale, updated_at, closure_requested_at, closure_requested_by)"
    " ON organizations TO atesta_app",
)
