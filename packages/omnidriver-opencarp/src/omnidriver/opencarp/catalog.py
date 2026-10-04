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


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    opencarp_type: str
    value_kind: str | None
    default: str | None
    minimum: str | None
    maximum: str | None
    #: As +Help prints it ("ms", "microseconds"); none for a parameter with no units.
    units: str | None
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
            default=entry["default"], minimum=entry["minimum"], maximum=entry["maximum"], units=entry["units"],
            menu=tuple(entry["menu"]), allocates=tuple(entry["allocates"]),
            description=entry["description"],
        )
        for entry in payload["parameters"]
    }
    return Catalog(identity=dict(payload["opencarp"]), parameters=parameters)
