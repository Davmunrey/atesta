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


ItemText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class GuideReference(Content):
    """Where a guide says it: cited, never copied (requirement-register spec, issue 226)."""

    guide: Text
    edition: Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    section: Text
    page: Annotated[int, Field(ge=1)]


class ExpectedEvidenceItem(Content):
    es: ItemText
    en: ItemText
    ref: GuideReference


class ExpectedEvidence(Content):
    """What an auditor is likely to ask for, in Atesta's own words with the guide reference.
    A candidate until the owner signs it: a signature is the reviewer's name and the date."""

    items: list[ExpectedEvidenceItem] = Field(min_length=1, max_length=8)
    reviewed_by: Text | None
    reviewed_on: date | None = None

    @model_validator(mode="after")
    def signed_in_full(self) -> Self:
        if (self.reviewed_by is None) != (self.reviewed_on is None):
            raise ValueError("a signed checklist names its reviewer and the review date")
        return self


class PageReference(Content):
    """A section and page of the profile's own guide (its first reference)."""

    section: Text
    page: Annotated[int, Field(ge=1)]


class ScopeProfile(Content):
    """A published compliance profile as a scope option (requirement-register spec, issue 227):
    one value per requirement of the pack, a level or `n.a.`. The guide is cited, never copied.
    A candidate until the owner signs it, like expected evidence."""

    key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    title_es: Text
    title_en: Text
    summary_es: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
    ]
    summary_en: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
    ]
    refs: list[GuideReference] = Field(min_length=1, max_length=4)
    levels: dict[str, Text]
    criteria: dict[str, PageReference] = Field(default_factory=dict)
    reviewed_by: Text | None
    reviewed_on: date | None = None

    @model_validator(mode="after")
    def signed_in_full(self) -> Self:
        if self.key == "profile":
            raise ValueError("the profile key 'profile' is reserved")
        if (self.reviewed_by is None) != (self.reviewed_on is None):
            raise ValueError("a signed profile names its reviewer and the review date")
        return self


GuideText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class ScopeGuideStep(Content):
    """One valuation question: an asset type and one dimension key, in Atesta's own words."""

    asset: Literal["information", "service"]
    key: Text
    es: GuideText
    en: GuideText
    ref: GuideReference


class ScopeGuideNote(Content):
    es: GuideText
    en: GuideText
    ref: GuideReference


class ScopeGuide(Content):
    """How to value the system before recording the scope (requirement-register spec, issue 225):
    ordered steps on the pack's dimension axis, and the category each level leads to."""

    axis: Text
    category_axis: Text
    category_by_level: dict[str, Text] = Field(min_length=1)
    steps: list[ScopeGuideStep] = Field(min_length=1, max_length=20)
    notes: list[ScopeGuideNote] = Field(default_factory=list, max_length=10)
    reviewed_by: Text | None
    reviewed_on: date | None = None

    @model_validator(mode="after")
    def signed_in_full(self) -> Self:
        if (self.reviewed_by is None) != (self.reviewed_on is None):
            raise ValueError("a signed guide names its reviewer and the review date")
        return self


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
    expected_evidence: ExpectedEvidence | None = None

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


class ReportingClock(Content):
    """A reporting deadline copied from the official text (recorded-routines spec). It starts when
    the organization became aware of the incident, when it classified the incident as significant
    (`starts: classified`), or when the clock named in `after` was met. A classified clock may
    keep an outer limit in hours from awareness, which lapses when classification is later."""

    key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    title_es: Text
    title_en: Text
    hours: Annotated[int, Field(ge=1, le=8760)] | None = None
    months: Annotated[int, Field(ge=1, le=36)] | None = None
    after: Text | None = None
    starts: Literal["aware", "classified"] = "aware"
    outer_limit_hours: Annotated[int, Field(ge=1, le=8760)] | None = None
    needs: Literal["significant", "personal_data"]
    requirement: Text

    @model_validator(mode="after")
    def one_duration(self) -> Self:
        if (self.hours is None) == (self.months is None):
            raise ValueError("a reporting clock lasts hours or months, not both")
        if self.starts == "classified" and (self.after is not None or self.needs != "significant"):
            raise ValueError("a clock from classification needs significant and no other clock")
        if self.outer_limit_hours is not None and self.starts != "classified":
            raise ValueError("only a clock from classification has an outer limit")
        return self


class CriterionText(Content):
    """An official text shown next to an incident flag, copied from the act (rule 10). For
    criteria that are not measures, so they stay out of the self-assessment register."""

    section: Text
    title_es: Text
    title_en: Text | None = None
    official_text_es: Text
    official_text_en: Text | None = None
    source: Link
    source_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class IncidentCriterion(Content):
    """What explains an incident flag (recorded-routines spec): a requirement of the pack, or an
    official text given inline."""

    needs: Literal["significant", "personal_data"]
    requirement: Text | None = None
    text: CriterionText | None = None

    @model_validator(mode="after")
    def one_source(self) -> Self:
        if (self.requirement is None) == (self.text is None):
            raise ValueError("an incident criterion names a requirement or an official text")
        return self


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
    reporting_clocks: list[ReportingClock] = Field(default_factory=list)
    scope_profiles: list[ScopeProfile] = Field(default_factory=list)
    scope_guide: ScopeGuide | None = None
    incident_criteria: list[IncidentCriterion] = Field(default_factory=list)


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
    """A candidate until the owner signs it in session: the reviewer's name and the date, both or
    neither (control-model-schema spec, #210). The database keeps the name; git keeps the date."""

    requirement_id: Text
    control_id: Text
    rationale: Text
    source: Link
    reviewed_by: Text | None = None
    reviewed_on: date | None = None

    @model_validator(mode="after")
    def signed_in_full(self) -> Self:
        if (self.reviewed_by is None) != (self.reviewed_on is None):
            raise ValueError("a signed mapping names its reviewer and the review date")
        return self


class Requirements(Content):
    requirements: list[RequirementContent]


class Mappings(Content):
    mappings: list[MappingContent]


class Pack(Content):
    metadata: PackMetadata
    requirements: list[RequirementContent]
    mappings: list[MappingContent]
    coverage: Coverage | None = None
