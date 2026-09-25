"""openCARP's parameter catalog, generated from the binary (catalog_generation.py).

Names are +Help's template form (``stim[Int].pulse.strength``). A whole-array
shorthand (type ``{ 3 x Float }``) has no value kind; the validator asks for
its indexed elements instead."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources

VALUE_KIND_BY_TYPE = {
    "Int": "integer", "Short": "integer", "Long": "integer",
    "Float": "scalar", "Double": "scalar",
    "Flag": "boolean",                               # written 1/0 only (F1)
    "String": "string", "RFile": "string", "WFile": "string",
}
_INDEX = re.compile(r"\[\d+\]")


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    opencarp_type: str
    value_kind: str | None
    default: str | None
    minimum: str | None
    maximum: str | None
    menu: tuple[str, ...]
    allocates: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class Catalog:
    identity: dict[str, str]
    parameters: dict[str, ParameterSpec]


def template_name(key: str) -> str:
    return _INDEX.sub("[Int]", key)


@cache
def load_catalog() -> Catalog:
    payload = json.loads(resources.files(__package__).joinpath("opencarp_parameters.json").read_text())
    parameters = {
        entry["name"]: ParameterSpec(
            name=entry["name"], opencarp_type=entry["type"],
            value_kind=VALUE_KIND_BY_TYPE.get(entry["type"]),
            default=entry["default"], minimum=entry["minimum"], maximum=entry["maximum"],
            menu=tuple(entry["menu"]), allocates=tuple(entry["allocates"]),
            description=entry["description"],
        )
        for entry in payload["parameters"]
    }
    return Catalog(identity=dict(payload["opencarp"]), parameters=parameters)
