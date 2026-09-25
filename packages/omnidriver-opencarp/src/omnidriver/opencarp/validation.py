"""Record-key validation against the generated catalog.

Refusals name the key and cite the evidence (docs/solver-learning/opencarp.md).
Bounds are checked only when +Help gives a literal number; expressions such
as ``dt/1000.`` (G1) are left to openCARP itself."""
from __future__ import annotations

import re
from typing import Any

from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.core.tutorial_records import TutorialRecordError

from .catalog import load_catalog, template_name
from .par_format import ParFormatError, parse_par, unquote

_LITERAL_NUMBER = re.compile(r"^-?\d+(\.\d*)?([eE][+-]?\d+)?$")
_TOP_INDEX = re.compile(r"^(?P<array>[A-Za-z_]\w*)\[(?P<index>\d+)\]")


def record_key_validator(document: str, key_path: tuple[str, ...], value: Any) -> tuple[str, bool]:
    key = ".".join(key_path)
    if not document.endswith(".par"):
        raise TutorialRecordError(f"{document}:{key}: openCARP study keys address a .par document")
    catalog = load_catalog()
    spec = catalog.parameters.get(template_name(key))
    if spec is None:
        raise TutorialRecordError(f"{document}:{key} is not an openCARP {catalog.identity['tag']} parameter")
    if spec.value_kind is None:
        raise TutorialRecordError(
            f"{document}:{key} is openCARP's whole-array form ({spec.opencarp_type}); set each element, e.g. {key}[0]"
        )
    problems = validate_value_shape(spec.value_kind, value)
    if problems:
        hint = " (openCARP reads 'no' and 'off' as on: F1)" if spec.value_kind == "boolean" else ""
        raise TutorialRecordError(f"{document}:{key}: {'; '.join(problems)}{hint}")
    if spec.menu:
        spelled = str(int(value)) if isinstance(value, bool) else str(value)
        if spelled not in spec.menu:
            raise TutorialRecordError(f"{document}:{key} = {value!r} is not one of {list(spec.menu)}")
    for bound, label, outside in ((spec.minimum, "minimum", lambda v, b: v < b), (spec.maximum, "maximum", lambda v, b: v > b)):
        if bound is not None and _LITERAL_NUMBER.match(bound) and spec.value_kind in ("integer", "scalar"):
            if outside(float(value), float(bound)):
                raise TutorialRecordError(f"{document}:{key} = {value!r} is beyond its {label} {bound}")
    return spec.value_kind, True


def check_indices(text: str) -> None:
    """Refuse an indexed key at or beyond its count (F2; openCARP exits 5 at startup).

    A count absent from the text takes its catalog default (F7:
    ``num_stim`` defaults to 2). Only top-level arrays are checked;
    nested counts (``phys_region[0].num_IDs``) are left to openCARP."""
    catalog = load_catalog()
    count_key_for = {array: spec.name for spec in catalog.parameters.values() for array in spec.allocates}
    values = {a.key: a.value for a in parse_par(text)}
    for key in values:
        match = _TOP_INDEX.match(key)
        if match is None or match["array"] not in count_key_for:
            continue
        count_key = count_key_for[match["array"]]
        raw = values.get(count_key)
        count_text = unquote(raw) if raw is not None else catalog.parameters[count_key].default
        if count_text is None or not count_text.lstrip("-").isdigit():
            continue
        if int(match["index"]) >= int(count_text):
            source = "" if raw is not None else " (its default; F7)"
            raise ParFormatError(f"{key}: index {match['index']} is outside {count_key} = {count_text}{source} (F2)")
