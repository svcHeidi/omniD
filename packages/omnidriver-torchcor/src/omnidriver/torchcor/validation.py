"""A study key judged before staging, and a staged case.json judged by the runner's ``--check``.

The key validator says only whether the runner takes a key and what kind of
value: the rules a whole case must keep (bounds, menus, the model's own
options and initial values, which TorchCor would accept misspelt,
docs/solver-learning/torchcor.md B4, B6) are the runner's, judged on the
staged case."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.core.tutorial_records import TutorialRecordError

from .catalog import CASE_DOCUMENT, Catalog, CatalogError, check

#: Each case.json object whose fields depend on the ionic model, and where ``--describe`` lists them per model.
_MODEL_FIELDS = {"ionic_options": "options", "ionic_init": "init"}


def _kinds(catalog: Catalog, key_path: tuple[str, ...]) -> set[str]:
    key = ".".join(key_path)
    if key in catalog.keys:
        return {catalog.keys[key]["kind"]}
    if len(key_path) == 2 and key_path[0] in _MODEL_FIELDS:
        listed = _MODEL_FIELDS[key_path[0]]
        return {model[listed][key_path[1]]["kind"] for model in catalog.ionic_models.values() if key_path[1] in model[listed]}
    return set()


def validate_key(catalog: Catalog | None, document: str, key_path: tuple[str, ...], value: Any) -> tuple[str, bool]:
    """``(value_kind, validated)`` for one study key; raises ``TutorialRecordError`` naming a key the runner does not take."""
    key = ".".join(key_path)
    if document != CASE_DOCUMENT:
        raise TutorialRecordError(
            f"{document}:{key}: the runner reads only {CASE_DOCUMENT}, never {document}", code="unknown_document",
        )
    if catalog is None:
        return _kind_of(value), False
    kinds = _kinds(catalog, key_path)
    if not kinds:
        raise TutorialRecordError(
            f"{document}:{key}: not a key {catalog.runner} takes, nor a field of any ionic model's", code="unknown_key",
        )
    for kind in sorted(kinds):
        if not validate_value_shape(kind, value):
            return kind, True
    raise TutorialRecordError(
        f"{document}:{key}: {value!r} is not a {' or '.join(sorted(kinds))}", code="catalog_rule",
        rule={"value_kind": sorted(kinds)},
    )


def _kind_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "scalar"
    return "string" if isinstance(value, str) else "mapping" if isinstance(value, dict) else "scalar_list"


def case_diagnostics(case_root: Path, runner: Path, source: Path, env: dict[str, str]) -> tuple[StrictDiagnostic, ...]:
    try:
        refused = check(runner, source, env, Path(case_root) / CASE_DOCUMENT)
    except (CatalogError, OSError, ValueError) as exc:
        return (diagnostic("error", "torchcor_check_failed", str(exc), source=CASE_DOCUMENT),)
    return tuple(
        diagnostic("error", "torchcor_case_refused", item["message"], source=CASE_DOCUMENT, field=item["key"])
        for item in refused
    )
