"""Override mutation is plugin-owned and always receives an explicit context.

Core has no format-neutral dictionary mutator. A plugin without the optional
``apply_overrides`` hook is refused deterministically; a plugin that supplies
one must also declare every path it can mutate so the transaction layer can
capture exact before-images.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context

import plugins.minimal_plugin as minimal_plugin


def _context():
    return driver_context(
        minimal_plugin.MinimalTestPlugin(), source="test:override-apply",
    )


def test_apply_requires_a_context_rather_than_resolving_one() -> None:
    """The signature is the guard: omitting it must fail loudly, not silently
    fall back to whichever plugin happens to be installed."""
    context = _context()
    with pytest.raises(TypeError, match="driver_context"):
        context.capabilities.override_scopes.apply([], case_root="/tmp")


def test_missing_plugin_mutator_is_refused_without_adapter_delegation() -> None:
    context = _context()
    assert not hasattr(context.plugin, "apply_overrides"), (
        "this test exists to exercise the FALLBACK; the minimal plugin must "
        "not implement the hook"
    )
    with pytest.raises(ValueError, match="apply_overrides"):
        context.capabilities.override_scopes.apply(
            [], case_root="/tmp", driver_context=context,
        )


def test_custom_mutator_must_declare_its_complete_target_set(tmp_path: Path) -> None:
    class CustomMutator(minimal_plugin.MinimalTestPlugin):
        def apply_overrides(self, overrides, *, case_root):
            del overrides, case_root

    context = driver_context(CustomMutator(), source="test:custom-mutator")

    with pytest.raises(ValueError, match="get_override_target_paths"):
        context.capabilities.override_scopes.target_paths(
            [], case_root=tmp_path, driver_context=context,
        )


def test_custom_target_declaration_is_exposed_without_mutating(tmp_path: Path) -> None:
    class DeclaredMutator(minimal_plugin.MinimalTestPlugin):
        def apply_overrides(self, overrides, *, case_root):
            del overrides, case_root

        def get_override_target_paths(self, overrides, *, case_root):
            del overrides
            return (case_root / "system" / "fvSchemes",)

    context = driver_context(DeclaredMutator(), source="test:declared-mutator")

    assert context.capabilities.override_scopes.target_paths(
        [], case_root=tmp_path, driver_context=context,
    ) == (tmp_path / "system" / "fvSchemes",)
