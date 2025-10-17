from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


LABEL_STORE_FILENAME = "label_templates.json"


def _sorted_unique(values: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


@dataclass
class AttributeOption:
    value: str
    parent_constraints: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "value": self.value,
            "parent_constraints": {k: list(v) for k, v in self.parent_constraints.items()},
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "AttributeOption":
        constraints_raw = payload.get("parent_constraints") or {}
        constraints: Dict[str, List[str]] = {}
        if isinstance(constraints_raw, dict):
            for key, value in constraints_raw.items():
                if isinstance(value, list):
                    constraints[str(key)] = [str(item) for item in value]
        return cls(
            value=str(payload.get("value", "")).strip(),
            parent_constraints=constraints,
        )


@dataclass
class AttributeDefinition:
    name: str
    role: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    options: List[AttributeOption] = field(default_factory=list)
    input_type: str = "list"  # "list" or "number"

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "role": self.role,
            "dependencies": list(self.dependencies),
            "options": [option.to_dict() for option in self.options],
            "input_type": self.input_type,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "AttributeDefinition":
        options_payload = payload.get("options") or []
        options: List[AttributeOption] = []
        if isinstance(options_payload, list):
            for option in options_payload:
                if isinstance(option, dict):
                    options.append(AttributeOption.from_dict(option))
        dependencies_raw = payload.get("dependencies") or []
        dependencies = [str(entry) for entry in dependencies_raw] if isinstance(dependencies_raw, list) else []
        role_raw = payload.get("role")
        role = str(role_raw) if role_raw is not None else None
        input_type = str(payload.get("input_type", "list")) or "list"
        return cls(
            name=str(payload.get("name", "")),
            role=role,
            dependencies=_sorted_unique(dependencies),
            options=options,
            input_type=input_type if input_type in {"list", "number"} else "list",
        )

    def copy(self) -> "AttributeDefinition":
        return AttributeDefinition.from_dict(self.to_dict())


@dataclass
class ClassTemplate:
    name: str
    attributes: List[AttributeDefinition] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "attributes": [attribute.to_dict() for attribute in self.attributes],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "ClassTemplate":
        attrs_payload = payload.get("attributes") or []
        attributes: List[AttributeDefinition] = []
        if isinstance(attrs_payload, list):
            for attribute in attrs_payload:
                if isinstance(attribute, dict):
                    attributes.append(AttributeDefinition.from_dict(attribute))
        name = str(payload.get("name", ""))
        return cls(name=name, attributes=attributes)

    def copy(self) -> "ClassTemplate":
        return ClassTemplate.from_dict(self.to_dict())


class LabelStore:
    def __init__(self, templates: Optional[Dict[str, ClassTemplate]] = None) -> None:
        self.templates: Dict[str, ClassTemplate] = templates or {}

    @property
    def path(self) -> Path:
        return Path(__file__).resolve().parent / LABEL_STORE_FILENAME

    def to_dict(self) -> Dict[str, object]:
        return {
            "templates": [template.to_dict() for template in self.templates.values()],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "LabelStore":
        templates_payload = payload.get("templates") or []
        templates: Dict[str, ClassTemplate] = {}
        if isinstance(templates_payload, list):
            for item in templates_payload:
                if not isinstance(item, dict):
                    continue
                template = ClassTemplate.from_dict(item)
                if template.name:
                    templates[template.name] = template
        return cls(templates=templates)

    def save(self, path: Optional[Path] = None) -> None:
        destination = path if path else self.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "LabelStore":
        instance = cls()
        destination = path if path else instance.path
        if not destination.exists():
            store = cls._with_default_templates()
            store.save(destination)
            return store
        try:
            payload = json.loads(destination.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        return cls.from_dict(payload)

    @classmethod
    def _with_default_templates(cls) -> "LabelStore":
        default_template = ClassTemplate(
            name="Sample Category",
            attributes=[
                AttributeDefinition(
                    name="Protein",
                    role="label",
                    dependencies=[],
                    options=[
                        AttributeOption("Beef"),
                        AttributeOption("Pork"),
                        AttributeOption("Chicken"),
                    ],
                ),
                AttributeDefinition(
                    name="Cut",
                    role=None,
                    dependencies=["Protein"],
                    options=[
                        AttributeOption("Ribeye", parent_constraints={"Protein": ["Beef"]}),
                        AttributeOption("Tenderloin", parent_constraints={"Protein": ["Beef", "Pork"]}),
                        AttributeOption("Ham", parent_constraints={"Protein": ["Pork"]}),
                        AttributeOption("Breast", parent_constraints={"Protein": ["Chicken"]}),
                    ],
                ),
                AttributeDefinition(
                    name="Feed",
                    role=None,
                    dependencies=["Protein"],
                    options=[
                        AttributeOption("Grass Fed", parent_constraints={"Protein": ["Beef"]}),
                        AttributeOption("Grain Finished", parent_constraints={"Protein": ["Beef", "Pork"]}),
                        AttributeOption("Pasture Raised", parent_constraints={"Protein": ["Chicken"]}),
                    ],
                ),
                AttributeDefinition(
                    name="Age (days)",
                    role=None,
                    dependencies=[],
                    options=[],
                    input_type="number",
                ),
            ],
        )
        return cls(templates={default_template.name: default_template})

    def list_templates(self) -> List[ClassTemplate]:
        return [self.templates[name] for name in sorted(self.templates.keys())]

    def get_template(self, name: str) -> Optional[ClassTemplate]:
        return self.templates.get(name)

    def upsert_template(self, template: ClassTemplate) -> None:
        if not template.name:
            raise ValueError("Template name is required")
        self.templates[template.name] = template

    def delete_template(self, name: str) -> None:
        if name in self.templates:
            del self.templates[name]

    def copy(self) -> "LabelStore":
        return LabelStore.from_dict(self.to_dict())
