"""Typed preview content; publishing a reviewed pack needs a separate release workflow."""

from datetime import date
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def safe_link(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("catalog references must be HTTPS URLs without credentials")
    return value


Link = Annotated[Text, AfterValidator(safe_link)]


class Content(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectionRule(Content):
    level: Text
    rule: Text


class RequirementContext(Content):
    official_text_es: Text
    applicability_es: Text
    selection_basis: Text
    selection_rules: list[SelectionRule] = Field(min_length=1)
    section: Text
    source_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class PackContext(Content):
    content_state: Literal["template", "partial", "complete"]
    assessment_enabled: Literal[False]
    summary_es: Text
    summary_en: Text
    scope_es: Text
    scope_en: Text
    applicability_es: Text
    applicability_en: Text
    limitations_es: Text
    limitations_en: Text
    preparation_controls: list[Text]
    source_refs: list[Link] = Field(min_length=1)
    verified_on: date


class PackMetadata(Content):
    id: Text
    name: Text
    version: Text
    jurisdiction: Text
    source: Link
    license_notes: Text
    status: Literal["draft"]
    attributes: PackContext


class RequirementContent(Content):
    id: Text
    title_es: Text
    title_en: Text | None = None
    applies_to: list[Text] = Field(default_factory=list)
    source: Link
    attributes: RequirementContext


class ControlContent(Content):
    id: Text
    title_es: Text
    title_en: Text
    description_es: Text
    description_en: Text
    manual: bool
    prowler_checks: list[Text]
    atesta_checks: list[Text]
    remediation_refs: list[Link] = Field(min_length=1)


class MappingContent(Content):
    requirement_id: Text
    control_id: Text
    rationale: Text
    source: Link
    reviewed_by: None


class Requirements(Content):
    requirements: list[RequirementContent]


class Mappings(Content):
    mappings: list[MappingContent]


class Pack(Content):
    metadata: PackMetadata
    requirements: list[RequirementContent]
    mappings: list[MappingContent]
