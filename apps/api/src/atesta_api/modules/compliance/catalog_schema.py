"""Typed preview content; publishing a reviewed pack needs a separate release workflow."""

from datetime import date
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

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
    """Official text of one requirement (content model v2). Selection tables by category or
    dimension are optional; an act also published in English carries its official English text."""

    official_text_es: Text
    official_text_en: Text | None = None
    applicability_es: Text | None = None
    selection_basis: Text | None = None
    selection_rules: list[SelectionRule] = Field(default_factory=list)
    section: Text
    source_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

    @model_validator(mode="after")
    def rules_need_a_basis(self) -> Self:
        if bool(self.selection_basis) != bool(self.selection_rules):
            raise ValueError("selection rules and their basis come together")
        return self


class GroupHeading(Content):
    prefix: Text
    title: Text
    title_en: Text | None = None  # the official English heading, when the act has one


class CoverageEntry(Content):
    """Units of the official source (articles, provisions, annexes) and what the pack does with
    them: covered by named requirements, or excluded with a reason in ES and EN."""

    units: list[Text] = Field(min_length=1)
    status: Literal["covered", "excluded"]
    requirements: list[Text] = Field(default_factory=list)
    reason_es: Text | None = None
    reason_en: Text | None = None

    @model_validator(mode="after")
    def covered_or_explained(self) -> Self:
        if self.status == "covered" and (not self.requirements or self.reason_es or self.reason_en):
            raise ValueError("a covered unit names its requirements and needs no reason")
        if self.status == "excluded" and (
            self.requirements or not (self.reason_es and self.reason_en)
        ):
            raise ValueError("an excluded unit gives its reason in ES and EN")
        return self


class Coverage(Content):
    source: Text
    entries: list[CoverageEntry] = Field(min_length=1)


class TermLabel(Content):
    """A readable label for an official scope term (axis, dimension key or level). Authored text,
    not official: the stored scope keeps the official term."""

    term: Text
    es: Text
    en: Text


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
    # Official group headings in the source's order, by requirement-code prefix (rule 10). A list,
    # because JSONB does not keep object key order.
    groups_es: list[GroupHeading] = Field(default_factory=list)
    term_labels: list[TermLabel] = Field(default_factory=list)


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
    coverage: Coverage | None = None
