"""Record-key validation against the generated catalog.

Refusals name the key and cite the evidence (docs/solver-learning/opencarp.md).
Bounds are checked only when +Help gives a literal number; expressions such
as ``dt/1000.`` (G1) are left to openCARP itself."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.core.tutorial_records import TutorialRecord, TutorialRecordError

from .catalog import load_catalog, template_name
from .par_format import ParFormatError, parse_par, unquote
from .records import TUTORIAL_RECORDS

_LITERAL_NUMBER = re.compile(r"^-?\d+(\.\d*)?([eE][+-]?\d+)?$")
_TOP_INDEX = re.compile(r"^(?P<array>[A-Za-z_]\w*)\[(?P<index>\d+)\]")


@dataclass(frozen=True)
class CommandLineAssignment:
    """A ``-<key> <value>`` a record step passes after ``+F <document>``."""

    record: str
    step_id: str
    value: str


def _flag_assignments(arguments: tuple[str, ...]) -> list[tuple[str, str]]:
    """The ``-<key> <value>`` pairs in ``arguments`` (every openCARP flag takes
    a value); a nested ``+F <file>`` is skipped as a pair."""
    pairs, i = [], 0
    while i < len(arguments):
        token = arguments[i]
        if token == "+F":
            i += 2
        elif token.startswith("-") and len(token) > 1 and i + 1 < len(arguments):
            pairs.append((token[1:], arguments[i + 1]))
            i += 2
        else:
            i += 1
    return pairs


def read_documents(records: Mapping[str, TutorialRecord]) -> dict[str, dict[str, CommandLineAssignment]]:
    """Every document some record step passes with ``+F``, mapped to the keys
    that step's command line assigns AFTER it.

    Derived from the records' own ``WorkflowStep.command`` (one source of
    truth; review I1). openCARP reads only the ``+F`` documents, and it reads
    its arguments in order with the last assignment winning, silently (F14):
    a ``-<key>`` after ``+F <document>`` overrides that document's value, one
    before it does not. Arguments an axis appends at resolve time
    (``AxisResult.command_arguments``) are not visible here; niedererNVersion's
    one axis (``dx``) appends only to the ``mesh`` step, which reads no
    document."""
    documents: dict[str, dict[str, CommandLineAssignment]] = {}
    for record in records.values():
        for step in record.workflow_steps:
            arguments = tuple(step.command[1:])
            for i, token in enumerate(arguments):
                if token != "+F" or i + 1 >= len(arguments):
                    continue
                owned = documents.setdefault(arguments[i + 1], {})
                for key, value in _flag_assignments(arguments[i + 2:]):
                    owned.setdefault(key, CommandLineAssignment(record.name, step.step_id, value))
    return documents


def make_record_key_validator(
    records: Mapping[str, TutorialRecord],
) -> Callable[[str, tuple[str, ...], Any], tuple[str, bool]]:
    """A key validator for these records: refuses a document no record step
    reads and a key a record's command line owns (I1, F14), then checks the
    key against the generated catalog."""
    documents = read_documents(records)

    def validate(document: str, key_path: tuple[str, ...], value: Any) -> tuple[str, bool]:
        key = ".".join(key_path)
        if document not in documents:
            raise TutorialRecordError(
                f"{document}:{key}: no record step passes {document!r} to openCARP with +F, so "
                f"openCARP would never read it (documents it reads: {sorted(documents)})"
            )
        owner = documents[document].get(key)
        if owner is not None:
            raise TutorialRecordError(
                f"{document}:{key} is set by the record's command line (record {owner.record!r}, "
                f"step {owner.step_id!r}: -{key} {owner.value}); a .par value would be silently "
                "overridden (F14)"
            )
        return _catalog_check(document, key, value)

    return validate


def _catalog_check(document: str, key: str, value: Any) -> tuple[str, bool]:
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


record_key_validator = make_record_key_validator(TUTORIAL_RECORDS)


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
