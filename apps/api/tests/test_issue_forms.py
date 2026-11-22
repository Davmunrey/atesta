"""Issue forms and labels stay consistent (issue #104): every label a form applies exists in
.github/labels.json, the labels dependabot.yml relies on exist, and every form has the fields
GitHub requires for an issue form."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

GITHUB = Path(__file__).resolve().parents[3] / ".github"
TYPES = {"bug", "feature", "catalog", "security-hardening", "chore"}


def _labels() -> list[dict[str, str]]:
    labels: list[dict[str, str]] = json.loads((GITHUB / "labels.json").read_text())
    return labels


def _forms() -> dict[str, dict[str, Any]]:
    forms = sorted((GITHUB / "ISSUE_TEMPLATE").glob("*.yml"))
    return {p.name: yaml.safe_load(p.read_text()) for p in forms if p.name != "config.yml"}


def test_labels_are_unique_and_well_formed() -> None:
    labels = _labels()
    names = [label["name"] for label in labels]
    assert len(names) == len(set(names))
    for label in labels:
        assert set(label) == {"name", "color", "description"}, label
        assert re.fullmatch(r"[0-9a-f]{6}", label["color"]), label
        assert 0 < len(label["description"]) <= 100, label


def test_every_form_label_exists() -> None:
    names = {label["name"] for label in _labels()}
    for name, form in _forms().items():
        assert set(form.get("labels", [])) <= names, name


def test_each_type_label_has_exactly_one_form() -> None:
    applied = [label for form in _forms().values() for label in form["labels"]]
    assert sorted(applied) == sorted(TYPES)


def test_forms_have_the_fields_github_requires() -> None:
    for name, form in _forms().items():
        assert form["name"] and form["description"], name
        ids = [item["id"] for item in form["body"] if item["type"] != "markdown"]
        assert ids and len(ids) == len(set(ids)), name
        for item in form["body"]:
            assert item["type"] in {"markdown", "textarea", "input", "dropdown", "checkboxes"}


def test_dependabot_labels_exist() -> None:
    names = {label["name"] for label in _labels()}
    config = yaml.safe_load((GITHUB / "dependabot.yml").read_text())
    defaults = {"uv": "python:uv", "npm": "javascript", "github-actions": "github_actions"}
    for update in config["updates"]:
        ecosystem = update["package-ecosystem"]
        for label in update.get("labels", [defaults.get(ecosystem, "dependencies")]):
            assert label in names, (ecosystem, label)
    assert "dependencies" in names


def test_blank_issues_are_disabled() -> None:
    config = yaml.safe_load((GITHUB / "ISSUE_TEMPLATE" / "config.yml").read_text())
    assert config["blank_issues_enabled"] is False
