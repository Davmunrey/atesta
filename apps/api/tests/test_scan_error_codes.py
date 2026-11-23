"""Every code a scan stores in error_code is known, listed and translated (#270).

GET /scans returns error_code, so the web needs ES and EN text for each one. The model refuses
any other code, so every write path the database tests exercise is checked too.
"""

import pytest
from atesta_api.contract import error_codes
from atesta_api.modules.scanning.api import SCAN_ERROR_CODES
from atesta_api.modules.scanning.attempts import BLOCKED_CODES, ENGINE_FAILED, TRANSIENT_ERRORS
from atesta_api.modules.scanning.models import Scan


def test_the_scan_failure_codes_are_in_the_contract_list() -> None:
    assert set(error_codes()) >= SCAN_ERROR_CODES


def test_every_exit_code_and_verdict_maps_to_a_known_code() -> None:
    mapped = {TRANSIENT_ERRORS.get(code, ENGINE_FAILED) for code in range(256)}
    assert mapped | set(BLOCKED_CODES.values()) <= SCAN_ERROR_CODES


@pytest.mark.parametrize("code", sorted(SCAN_ERROR_CODES))
def test_a_known_code_can_be_stored(code: str) -> None:
    assert Scan(error_code=code).error_code == code


def test_an_unknown_code_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown scan error code"):
        Scan(error_code="scanning.something_new")
    scan = Scan()
    scan.error_code = None
    assert scan.error_code is None
