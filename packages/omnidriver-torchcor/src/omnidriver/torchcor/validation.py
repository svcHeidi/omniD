"""A case.json judged against the runner's catalogue before anything runs.

The rules are the catalogue's: kinds, bounds and menus from ``--describe``, and
the ionic model's own options and initial values, which TorchCor itself would
accept misspelt (docs/solver-learning/torchcor.md B4, B6)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.core.tutorial_records import TutorialRecordError

from .catalog import CASE_DOCUMENT, Catalog

_MODEL_FIELDS = {"ionic_options": "string", "ionic_init": "scalar"}


def _problems(name: str, spec: Mapping[str, Any], value: Any, devices: tuple[str, ...]) -> list[str]:
    shape = validate_value_shape(spec["kind"], value)
    if shape:
        return [f"{name} = {value!r} is not a {spec['kind']}: {'; '.join(shape)}"]
    problems = []
    if spec.get("menu") is not None and value not in spec["menu"]:
        host = " (the devices this host can run)" if name == "device" else ""
        problems.append(f"{name} = {value!r} is not one of {spec['menu']}{host}")
    for bound, outside, says in (("minimum", lambda v, b: v < b, "is below its minimum"),
                                 ("exclusive_minimum", lambda v, b: v <= b, "must exceed"),
                                 ("maximum", lambda v, b: v > b, "is above its maximum")):
        if spec.get(bound) is not None and outside(value, spec[bound]):
            problems.append(f"{name} = {value!r} {says} {spec[bound]}")
    return problems


def _model_field(catalog: Catalog, field: str, name: str, value: Any, models: list[str]) -> list[str]:
    """Problems with ``<field>.<name> = value`` for any of ``models``."""
    kind = _MODEL_FIELDS[field]
    if field == "ionic_init":
        if not any(name in catalog.ionic_models[m]["init"] for m in models):
            return [f"{field}.{name}: not an initial value of {' or '.join(models)}; TorchCor would set it and never read it (B6)"]
        return _problems(f"{field}.{name}", {"kind": kind}, value, catalog.devices)
    options = [catalog.ionic_models[m]["options"][name] for m in models if name in catalog.ionic_models[m]["options"]]
    if not options:
        return [f"{field}.{name}: not an option of {' or '.join(models)}"]
    menu = sorted({item for option in options for item in option["menu"] or ()}) or None
    return _problems(f"{field}.{name}", {"kind": kind, "menu": menu}, value, catalog.devices)


def validate_key(catalog: Catalog | None, document: str, key_path: tuple[str, ...], value: Any) -> tuple[str, bool]:
    """``(value_kind, validated)`` for one study key; raises ``TutorialRecordError`` naming a key the runner would refuse."""
    key = ".".join(key_path)
    if document != CASE_DOCUMENT:
        raise TutorialRecordError(f"{document}:{key}: the runner reads only {CASE_DOCUMENT}, never {document}")
    if catalog is None:
        return _kind_of(value), False
    if key in catalog.keys:
        problems = _problems(key, catalog.keys[key], value, catalog.devices)
        kind = catalog.keys[key]["kind"]
    elif len(key_path) == 2 and key_path[0] in _MODEL_FIELDS:
        problems = _model_field(catalog, key_path[0], key_path[1], value, sorted(catalog.ionic_models))
        kind = _MODEL_FIELDS[key_path[0]]
    else:
        problems, kind = [f"{key}: not a key {catalog.runner} takes"], None
    if problems:
        raise TutorialRecordError(f"{document}:{key}: " + "; ".join(problems))
    return kind, True


def _kind_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "scalar"
    return "string" if isinstance(value, str) else "mapping" if isinstance(value, dict) else "scalar_list"


def _flatten(case: Mapping[str, Any], catalog: Catalog) -> dict[str, Any]:
    flat = {}
    for key, value in case.items():
        if isinstance(value, dict) and any(name.startswith(key + ".") for name in catalog.keys):
            flat.update({f"{key}.{field}": item for field, item in value.items()})
        else:
            flat[key] = value
    return flat


def case_diagnostics(case_root: Path, catalog: Catalog) -> tuple[StrictDiagnostic, ...]:
    path = Path(case_root) / CASE_DOCUMENT
    try:
        case = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return (diagnostic("error", "torchcor_case_unreadable", f"{path}: {exc}", source=CASE_DOCUMENT),)
    flat = _flatten(case, catalog)
    found: list[tuple[str, str]] = [(name, f"not a key {catalog.runner} takes") for name in sorted(set(flat) - set(catalog.keys))]
    found += [(name, "required, and missing") for name in sorted(set(catalog.keys) - set(flat)) if catalog.keys[name]["required"]]
    for name in sorted(set(flat) & set(catalog.keys)):
        found += [(name, problem) for problem in _problems(name, catalog.keys[name], flat[name], catalog.devices)]
    model = flat.get("ionic_model")
    if model in catalog.ionic_models:
        for field in _MODEL_FIELDS:
            for name, value in (flat.get(field) or {}).items():
                found += [(f"{field}.{name}", problem) for problem in _model_field(catalog, field, name, value, [model])]
    return tuple(
        diagnostic("error", "torchcor_case_refused", problem, source=CASE_DOCUMENT, field=name) for name, problem in found
    )
