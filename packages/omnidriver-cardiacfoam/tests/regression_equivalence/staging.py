"""Agent addressability of regression cases (solver-free).

Two driving paths:

- strict: resolve by the registered entry name (only for mapped cases).
- generic: resolve by the case-folder path, which is not a SPEC_FACTORIES key,
  so ``resolve_entry`` falls through to the generic case-folder branch. This is
  how the agent reasons about cases that have no bespoke spec.
"""
from __future__ import annotations

from typing import Any

from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.registry import resolve_entry
from regression_equivalence.registry import RegressionCase


def _cardiac_context():
    """The plugin whose cases these are.

    ``resolve_entry`` takes a required ``driver_context``; it has since core
    stopped resolving one implicitly. These helpers were not updated, so
    `python -m regression_equivalence` raised TypeError before reaching any
    case -- the CLI documented as the way to validate against a real
    cardiacFoam checkout could not start. Found 2026-09-04 while writing that
    instruction down.
    """
    return load_plugin_context("cardiacfoam")


def resolve_generic(case: RegressionCase) -> dict[str, Any]:
    """Resolve a case by its folder path (the generic, non-registered branch).

    Resolving by path skips the registered-name lookup and lands in the
    case-folder branch. Some mapped cases exist under the same path as both a
    registered entry and a case_folder entry, which is ambiguous; there we pin
    the case_folder kind. Cases with a single entry at their path resolve
    without a kind filter.

    **Corrected 2026-09-26 (5.4b-N):** this used to name ``niederer`` as the
    example of such an ambiguous case. Niederer migrated onto a tutorial
    record (``niederer2011`` now resolves as ``"tutorial_record"``, not
    ``"registered_tutorial"``/``"case_folder"``), so it is no longer this
    kind of ambiguity -- see ``test_staging.py``'s own
    ``test_mapped_entry_resolves_registered`` for the current per-case
    resolution kinds.
    """
    try:
        return resolve_entry(case.case_dir, driver_context=_cardiac_context())
    except KeyError as exc:
        if "ambiguous" not in str(exc):
            raise
        return resolve_entry(
            case.case_dir, entry_kind="case_folder",
            driver_context=_cardiac_context(),
        )


def resolve_strict(case: RegressionCase) -> dict[str, Any]:
    if not case.mapped:
        raise ValueError(f"{case.case_dir} has no registered entry")
    return resolve_entry(case.entry_name, driver_context=_cardiac_context())
