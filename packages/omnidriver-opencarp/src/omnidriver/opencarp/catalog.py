"""openCARP's parameter catalog, generated from the binary (catalog_generation.py).

Names are +Help's template form (``stim[Int].pulse.strength``); a whole-array shorthand (type ``{ 3 x Float }``) has no value kind, so the validator asks for its indexed elements instead."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib import resources

VALUE_KIND_BY_TYPE = {
    "Int": "integer", "Short": "integer", "Long": "integer",
    "Float": "scalar", "Double": "scalar",
    "Flag": "boolean",                               # only 0 and false read as off (no and off read as on), so this is always written 1/0
    "String": "string", "RFile": "string", "WFile": "string",
}
_INDEX = re.compile(r"\[\d+\]")
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def number_of(text: str | None) -> float | None:
    """The value of a number spelled as +Help or a .par spells it (``5.``, ``.5``, ``+1``, ``1e-3``), else ``None``."""
    return float(text) if text is not None and _NUMBER.fullmatch(text.strip()) else None


def numeric_limits(spec: "ParameterSpec") -> dict[str, float]:
    """The bounds of ``spec`` that +Help gives as plain numbers, by core's bound name; an expression is not one."""
    limits = {"minimum": number_of(spec.minimum), "maximum": number_of(spec.maximum)}
    return {name: limit for name, limit in limits.items() if limit is not None}


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    opencarp_type: str
    value_kind: str | None
    #: A literal as a .par spells it; ``None`` when +Help's default is a C expression, kept in ``default_expression``.
    default: str | None
    default_expression: str | None
    minimum: str | None
    maximum: str | None
    #: In core's unit spelling where it has one ("us" for +Help's "microseconds"); ``units_as_printed`` is +Help's.
    units: str | None
    units_as_printed: str | None
    menu: tuple[str, ...]
    menu_labels: dict[str, str]
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
            default=entry["default"], default_expression=entry["default_expression"],
            minimum=entry["minimum"], maximum=entry["maximum"],
            units=entry["units"], units_as_printed=entry["units_as_printed"],
            menu=tuple(entry["menu"]), menu_labels=dict(entry["menu_labels"]), allocates=tuple(entry["allocates"]),
            description=entry["description"],
        )
        for entry in payload["parameters"]
    }
    return Catalog(identity=dict(payload["opencarp"]), parameters=parameters)
