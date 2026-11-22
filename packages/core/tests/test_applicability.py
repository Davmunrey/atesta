"""Applicability proposals from a pack's selection rules (requirement-register spec)."""

import pytest
from atesta_core.applicability import Proposal, axis_levels, propose

CATEGORY_RULES = [
    {"level": "BÁSICA", "rule": "n.a."},
    {"level": "MEDIA", "rule": "aplica"},
    {"level": "ALTA", "rule": "+ R1"},
]
DIMENSION_RULES = [
    {"level": "BAJO", "rule": "aplica"},
    {"level": "MEDIO", "rule": "+ R1"},
    {"level": "ALTO", "rule": "+ R1+R2"},
]
SCOPE = {"categoría": "MEDIA", "nivel": {"C": "BAJO", "I": "ALTO", "T": "MEDIO", "A": "BAJO"}}


def test_a_category_rule_uses_the_category() -> None:
    assert propose("categoría · Todas", CATEGORY_RULES, SCOPE) == Proposal(
        "applies", "aplica", "MEDIA"
    )
    basic = {"categoría": "BÁSICA"}
    assert propose("categoría · Todas", CATEGORY_RULES, basic) == Proposal(
        "not_applicable", "n.a.", "BÁSICA"
    )


def test_a_dimension_rule_uses_the_highest_listed_dimension() -> None:
    # C is BAJO and T is MEDIO: the highest of the two is MEDIO.
    assert propose("nivel · C T", DIMENSION_RULES, SCOPE) == Proposal("applies", "+ R1", "MEDIO")
    assert propose("nivel · I", DIMENSION_RULES, SCOPE) == Proposal("applies", "+ R1+R2", "ALTO")


def test_an_axis_the_scope_does_not_cover_is_undecided() -> None:
    assert propose("nivel · D", DIMENSION_RULES, SCOPE) == Proposal("undecided", None, None)
    assert propose("categoría · Todas", CATEGORY_RULES, {}) == Proposal("undecided", None, None)


def test_a_level_without_a_rule_is_undecided() -> None:
    rules = [{"level": "MEDIA", "rule": "aplica"}]
    assert propose("categoría · Todas", rules, {"categoría": "ALTA"}).decision == "undecided"


@pytest.mark.parametrize("basis", ["", "categoría", "categoría ·", "· Todas", None])
def test_a_malformed_basis_is_undecided(basis: str | None) -> None:
    assert propose(basis, CATEGORY_RULES, SCOPE).decision == "undecided"


def test_axis_levels_come_from_the_rules_in_order() -> None:
    requirements = [
        {"selection_basis": "categoría · Todas", "selection_rules": CATEGORY_RULES},
        {"selection_basis": "nivel · C I", "selection_rules": DIMENSION_RULES},
        {"selection_basis": "nivel · D", "selection_rules": DIMENSION_RULES},
    ]
    assert axis_levels(requirements) == {
        "categoría": {"keys": [], "levels": ["BÁSICA", "MEDIA", "ALTA"]},
        "nivel": {"keys": ["C", "D", "I"], "levels": ["BAJO", "MEDIO", "ALTO"]},
    }


def test_a_scope_is_valid_only_with_declared_levels() -> None:
    requirements = [
        {"selection_basis": "categoría · Todas", "selection_rules": CATEGORY_RULES},
        {"selection_basis": "nivel · C I", "selection_rules": DIMENSION_RULES},
    ]
    axes = axis_levels(requirements)
    from atesta_core.applicability import valid_scope

    assert valid_scope({"categoría": "MEDIA", "nivel": {"C": "ALTO"}}, axes)
    assert not valid_scope({"categoría": "MEDIUM"}, axes)
    assert not valid_scope({"nivel": {"Z": "ALTO"}}, axes)
    assert not valid_scope({"nivel": {"C": "HIGH"}}, axes)
    assert not valid_scope({"unknown": "x"}, axes)
