"""Agent addressability of regression cases (solver-free): strict resolves by
registered entry name, generic by case-folder path (the case-folder branch).
"""
from __future__ import annotations

from typing import Any

from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.registry import resolve_entry
from regression_equivalence.registry import RegressionCase


def _cardiac_context():
    return load_plugin_context("cardiacfoam")


def resolve_generic(case: RegressionCase) -> dict[str, Any]:
    """A path that is both a registered and a case_folder entry is ambiguous; pin case_folder."""
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
