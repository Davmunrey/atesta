"""Format checks for billing details (operator-portal spec, "Billing details form"). Format only:
no external lookup, and no check digit, whose algorithm these sources do not state.

Spanish tax IDs (`country` ES), from the official texts:
- **Legal persons and entities** (Orden EHA/451/2008, arts. 2 to 5,
  https://www.boe.es/buscar/act.php?id=BOE-A-2008-3580): nine characters, a letter for the legal
  form (A to H, J, P, Q, R, S, U, V; N for foreign entities, W for permanent establishments), a
  random number of seven digits, and a control character.
- **K, L and M numbers** (Real Decreto 1065/2007, arts. 19.2 and 20.2,
  https://www.boe.es/buscar/act.php?id=BOE-A-2007-15984): nine characters, the letter, seven
  alphanumeric characters and an alphabetic check character.
- **Spanish nationals** (art. 19.1): the DNI number followed by a capital letter. That the
  number has eight digits is not in the decree; a candidate, as for the NIE.
- **Foreign nationals** (art. 20.1): the NIE (X, Y or Z, seven digits, a letter). The NIE's
  composition is set outside the decree; it is a candidate here, to confirm against the
  Interior ministry's rules.

Other countries: 2 to 20 letters or digits once spaces, dots and hyphens are removed.
"""

import re

_SEPARATORS = re.compile(r"[\s.\-]")
_ES_TAX_ID = re.compile(
    r"[ABCDEFGHJNPQRSUVW][0-9]{7}[A-Z0-9]"  # Orden EHA/451/2008
    r"|[KLM][A-Z0-9]{7}[A-Z]"  # RD 1065/2007, arts. 19.2 and 20.2
    r"|[0-9]{8}[A-Z]"  # RD 1065/2007, art. 19.1 (DNI number and letter; eight: candidate)
    r"|[XYZ][0-9]{7}[A-Z]"  # NIE (candidate)
)
_OTHER_TAX_ID = re.compile(r"[A-Z0-9]{2,20}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_POSTAL = re.compile(r"[A-Z0-9][A-Z0-9 \-]{0,18}[A-Z0-9]")
_COUNTRY = re.compile(r"[A-Z]{2}")
LENGTHS = {  # the table's own limits (billing.models.BILLING_FIELDS)
    "legal_name": 200,
    "tax_id": 50,
    "address_line1": 200,
    "address_line2": 200,
    "postal_code": 20,
    "city": 100,
    "region": 100,
    "contact_email": 254,
    "country": 2,
}
OPTIONAL = frozenset({"address_line2"})


def tax_id_ok(value: str, country: str) -> bool:
    plain = _SEPARATORS.sub("", value).upper()
    pattern = _ES_TAX_ID if country == "ES" else _OTHER_TAX_ID
    return pattern.fullmatch(plain) is not None


def invalid_field(values: dict[str, str | None]) -> str | None:
    """The first field (in form order) that fails its format, or None when all pass."""
    for name, limit in LENGTHS.items():
        value = values.get(name)
        if value is None:
            if name in OPTIONAL:
                continue
            return name
        if (
            not value.strip()
            or value != value.strip()
            or len(value) > limit
            or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)
        ):
            return name
    country = values["country"] or ""
    checks = {
        "country": _COUNTRY.fullmatch(country) is not None,
        "tax_id": tax_id_ok(values["tax_id"] or "", country),
        "postal_code": _POSTAL.fullmatch((values["postal_code"] or "").upper()) is not None,
        "contact_email": _EMAIL.fullmatch(values["contact_email"] or "") is not None,
    }
    return next((name for name, ok in checks.items() if not ok), None)
