"""Owner sign-offs of mappings (control-model-schema spec, #210): exactly the approved ones carry
the reviewer and date; every other mapping stays a candidate. A signing PR edits SIGNED."""

from datetime import date
from pathlib import Path

import pytest
import yaml
from atesta_api.modules.compliance.catalog_schema import MappingContent, Mappings
from pydantic import ValidationError

CATALOG = Path(__file__).resolve().parents[3] / "catalog" / "frameworks"
REVIEWER, ON = "David Muñoz", date(2026, 11, 23)

# Approved in session on 2026-11-23 after every CCN-STIC citation was checked in the PDFs.
SIGNED = {
    "ens_rd311_2022": {
        ("mp.s.1", "ctl.m365_mail_threat_policies"),
        ("op.exp.6", "ctl.m365_mail_threat_policies"),
        ("op.exp.8", "ctl.m365_audit_logging"),
        ("op.acc.6", "ctl.exchange_access_hardening"),
        ("op.acc.1", "ctl.exchange_access_hardening"),
        ("op.exp.2", "ctl.exchange_access_hardening"),
        ("op.acc.4", "ctl.teams_external_access"),
        ("op.exp.2", "ctl.teams_external_access"),
        ("op.acc.6", "ctl.app_governance"),
    },
    "nis2": {
        ("art21.2i", "ctl.app_governance"),
        ("art21.2i", "ctl.teams_external_access"),
        ("art21.2j", "ctl.exchange_access_hardening"),
    },
    "gdpr_art32": {
        ("art32.1b", "ctl.app_governance"),
        ("art32.1b", "ctl.m365_mail_threat_policies"),
        ("art32.1b", "ctl.teams_external_access"),
    },
    "dora": {
        ("c2.art9", "ctl.app_governance"),
        ("c2.art9", "ctl.m365_mail_threat_policies"),
        ("c2.art9", "ctl.exchange_access_hardening"),
        ("c2.art10", "ctl.m365_audit_logging"),
    },
}


def _mappings(pack: str) -> list[MappingContent]:
    raw = yaml.safe_load((CATALOG / pack / "mappings.yaml").read_text())
    return Mappings.model_validate(raw).mappings


@pytest.mark.parametrize(
    "pack", sorted(p.name for p in CATALOG.iterdir() if p.is_dir() and not p.name.startswith("_"))
)
def test_only_the_approved_mappings_are_signed(pack: str) -> None:
    if not (CATALOG / pack / "mappings.yaml").exists():
        return
    signed = {
        (m.requirement_id, m.control_id): (m.reviewed_by, m.reviewed_on)
        for m in _mappings(pack)
        if m.reviewed_by is not None
    }
    assert set(signed) == SIGNED.get(pack, set())
    assert set(signed.values()) <= {(REVIEWER, ON)}


BASE = {
    "requirement_id": "x.1",
    "control_id": "ctl.x",
    "rationale": "r",
    "source": "https://www.boe.es/x",
}


@pytest.mark.parametrize(
    "fields",
    [
        {"reviewed_by": "David Muñoz"},
        {"reviewed_by": None, "reviewed_on": "2026-11-23"},
        {"reviewed_by": " ", "reviewed_on": "2026-11-23"},
    ],
)
def test_a_signature_names_its_reviewer_and_date(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MappingContent.model_validate({**BASE, **fields})


def test_a_full_signature_is_accepted() -> None:
    signed = MappingContent.model_validate(
        {**BASE, "reviewed_by": REVIEWER, "reviewed_on": "2026-11-23"}
    )
    assert (signed.reviewed_by, signed.reviewed_on) == (REVIEWER, ON)
