"""Public framework register: catalog guidance and recorded observations stay distinct."""

from typing import Literal

from pydantic import BaseModel

from atesta_api.modules.compliance.overview import SnapshotSummary

type RecordedStatus = Literal["pass", "fail", "manual", "not_applicable"]
type Observation = Literal["pass", "fail", "manual", "not_evaluated"]


class CheckDetail(BaseModel):
    engine: str
    check_id: str
    observed_status: Observation | None


class ControlDetail(BaseModel):
    key: str
    title_es: str
    title_en: str
    description_es: str
    description_en: str
    manual: bool
    remediation_refs: list[str]
    mapping_reviewed: bool
    mapping_source: str
    observed_status: Observation | None
    checks: list[CheckDetail]


class RequirementDetail(BaseModel):
    code: str
    title_es: str | None
    title_en: str | None
    source: str | None
    applies_to: list[str]
    in_current_catalog: bool
    status: RecordedStatus | Literal["not_evaluated"]
    controls: list[ControlDetail]


class FrameworkDetail(BaseModel):
    key: str
    name: str
    version: str
    status: str
    source: str
    catalog_version: str | None
    catalog_matches_snapshot: bool
    snapshot: SnapshotSummary | None
    requirements: list[RequirementDetail]
    development: bool
