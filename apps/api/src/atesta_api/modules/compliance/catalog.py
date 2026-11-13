"""Read and validate repository content without framework-specific branches or network I/O."""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from atesta_api.modules.compliance.catalog_schema import (
    ControlContent,
    Mappings,
    Pack,
    PackMetadata,
    Requirements,
)


class _UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.Node, deep: bool = False) -> dict[Any, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise ValueError("expected a YAML mapping")
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate YAML key")
        return super().construct_mapping(node, deep=deep)


def _yaml(path: Path) -> Any:
    return yaml.load(path.read_text(), Loader=_UniqueLoader)  # noqa: S506 safe loader subclass


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


@dataclass(frozen=True)
class Catalog:
    packs: list[Pack]
    controls: dict[str, ControlContent]
    engine_version: str

    def used_controls(self, pack: Pack) -> list[ControlContent]:
        keys = set(pack.metadata.attributes.preparation_controls)
        keys.update(m.control_id for m in pack.mappings)
        return [self.controls[key] for key in sorted(keys)]

    def fingerprint(self, pack: Pack) -> str:
        payload = {
            "pack": pack.model_dump(mode="json"),
            "controls": [c.model_dump(mode="json") for c in self.used_controls(pack)],
            "engine_version": self.engine_version,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


def read_catalog(root: Path, *, expected_checks: set[str], engine_version: str) -> Catalog:
    controls = [
        ControlContent.model_validate(_yaml(path))
        for path in sorted((root / "controls").glob("*.yaml"))
        if not path.name.startswith("_")
    ]
    _unique([c.id for c in controls], "control")
    for control in controls:
        _unique(control.prowler_checks, "control check")
        if control.atesta_checks:
            raise ValueError("custom checks need a versioned validation inventory")
        if control.manual and control.prowler_checks:
            raise ValueError("manual controls cannot contain automated checks")
        if not control.manual and not control.prowler_checks:
            raise ValueError("automated controls must contain checks")
        if set(control.prowler_checks) - expected_checks:
            raise ValueError(f"unknown pinned scanner check in {control.id}")
    catalog = Catalog([], {c.id: c for c in controls}, engine_version)
    for directory in sorted((root / "frameworks").iterdir()):
        if not directory.is_dir() or directory.name.startswith("_"):
            continue
        metadata = PackMetadata.model_validate(_yaml(directory / "pack.yaml"))
        requirements = Requirements.model_validate(_yaml(directory / "requirements.yaml"))
        mappings = Mappings.model_validate(_yaml(directory / "mappings.yaml"))
        pack = Pack(metadata=metadata, **requirements.model_dump(), **mappings.model_dump())
        if metadata.id != directory.name:
            raise ValueError("pack id must match its directory")
        _unique([r.id for r in pack.requirements], "requirement")
        _unique([f"{m.requirement_id}:{m.control_id}" for m in pack.mappings], "mapping")
        _unique(metadata.attributes.preparation_controls, "preparation control")
        if (metadata.attributes.content_state == "template") != (not pack.requirements):
            raise ValueError("only empty packs are templates")
        codes = {r.id for r in pack.requirements}
        mapped: dict[str, list[ControlContent]] = defaultdict(list)
        for mapping in pack.mappings:
            if mapping.requirement_id not in codes or mapping.control_id not in catalog.controls:
                raise ValueError("dangling requirement/control mapping")
            mapped[mapping.requirement_id].append(catalog.controls[mapping.control_id])
        if set(metadata.attributes.preparation_controls) - catalog.controls.keys():
            raise ValueError("unknown preparation control")
        if any(not any(c.manual for c in group) for group in mapped.values()):
            raise ValueError("candidate mappings must retain documentary review")
        catalog.packs.append(pack)
    _unique([p.metadata.id for p in catalog.packs], "framework")
    return catalog
