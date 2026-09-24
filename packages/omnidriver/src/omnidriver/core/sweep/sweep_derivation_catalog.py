from __future__ import annotations

import re
from typing import Any, Callable

from omnidriver.core.sweep.sweep_expansion import SweepValidationError


_CASE_ID_RE = re.compile(r"^[A-Za-z0-9_.=-]+$")


def _path_safe_case_id(value: str) -> str:
    if (
        not value
        or value in {".", ".."}
        or value.strip() != value
        or "/" in value
        or "\x00" in value
        or not _CASE_ID_RE.fullmatch(value)
    ):
        raise SweepValidationError(
            f"caseId {value!r} is not path-safe; use only letters, digits, '_', '-', '.', '='"
        )
    return value


def _label_for(value: Any) -> str:
    """Render one axis value as a label fragment.

    List/tuple values (e.g. niederer_2012.py's dx_values=[0.5]) are flattened
    element-wise rather than stringified as a Python literal (str([0.5]) ==
    "[0.5]", which is not path-safe).
    """
    if isinstance(value, (list, tuple)):
        return "-".join(str(v) for v in value)
    return str(value)


def _join_values_path_safe(values: dict[str, Any]) -> str:
    return _path_safe_case_id("_".join(_label_for(v) for v in values.values()))


def _case_id_template(values: dict[str, Any]) -> dict[str, Any]:
    """Join every named value into a single filesystem-safe label, in order."""
    return {"caseId": _join_values_path_safe(values)}


def _output_dir_name_template(values: dict[str, Any]) -> dict[str, Any]:
    """Join every named value into a single filesystem-safe output_dir_name.

    For entry-based sweeps (an existing registered tutorial's own make_spec),
    this plays the same role case_id_template plays for generic case_folder
    sweeps: naming this case's on-disk output directory.
    """
    return {"output_dir_name": _join_values_path_safe(values)}


SWEEP_DERIVATION_CATALOG: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "case_id_template": _case_id_template,
    "output_dir_name_template": _output_dir_name_template,
}

#: The output keys the two naming derivations above produce -- explicit and
#: hand-listed, not "every dependent output" (item 3, docs/superpowers/specs/
#: 2026-09-24-tutorials-are-pointers-design.md §4's worked example): a
#: sweep's ``dependent`` block derives names such as ``caseId`` purely for
#: the sweep machinery's own case/output-directory naming, never for case
#: content and never an axis. A tutorial-record study resolves its bare
#: names against a record's declared axes (``tutorial_records
#: .sort_study_name``); handing it one of these two keys unfiltered is
#: refused as an unrecognized axis, which is exactly the bug this constant
#: fixes -- the record pipeline strips these keys before classifying study
#: names, rather than growing a fallback that accepts any unrecognized bare
#: name. Kept in sync with ``_case_id_template``/``_output_dir_name_template``
#: by test_sweep_derivation_naming_output_keys_matches_the_catalog below.
NAMING_OUTPUT_KEYS: frozenset[str] = frozenset({"caseId", "output_dir_name"})


def get_derivation(name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Fixed-registry lookup. No getattr/eval/dynamic import off agent input."""
    if not isinstance(name, str):
        raise SweepValidationError(
            f"'derive' must be a string naming a registered derivation, got {name!r}"
        )
    try:
        return SWEEP_DERIVATION_CATALOG[name]
    except KeyError:
        known = ", ".join(sorted(SWEEP_DERIVATION_CATALOG)) or "(none registered)"
        raise SweepValidationError(
            f"Unknown derivation '{name}'. Known derivations: {known}"
        ) from None
