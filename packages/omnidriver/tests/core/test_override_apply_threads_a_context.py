"""``override_scopes.apply()`` must reach the OpenFOAM mutators with a context.

Phase 2 Task 6 made ``omnidriver.openfoam``'s ``validate_overrides`` and
``apply_overrides`` require an explicit ``DriverContext``, so that package stops
silently resolving the cardiac default. That broke the fallback underneath them:
``compatibility.legacy_apply_overrides`` called both with no context and had
none to give, because ``_OverrideScopeAdapter`` holds only ``self.plugin``.

The result was a ``TypeError`` on the agent-facing ``step --strict --apply``
path, for **every** shipped plugin -- no plugin implements the optional
``apply_overrides`` hook, so all of them take the fallback.

Nothing caught it. Every test covering that path
(``test_cli_step.py``, ``test_cli_run_document.py``,
``test_trust_boundary_end_to_end.py``) is ``skip_without_monorepo``, and this
standalone clone has no ``tutorials/`` tree, so all three skip. A break can hide
behind a skip exactly as well as behind a green assertion.

This test needs no monorepo, no OpenFOAM install and no case on disk: it only
has to prove the context reaches the boundary. ``validate_overrides`` rejects
the malformed override before touching a filesystem, which is enough -- if the
context were still missing we would get ``TypeError`` instead.
"""
from __future__ import annotations

import sys
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


def test_the_fallback_reaches_openfoam_with_the_context_it_was_given() -> None:
    """A plugin with no apply_overrides hook takes legacy_apply_overrides.

    Skipped without omnidriver-openfoam, which owns the mutators the fallback
    delegates to -- the point is the handoff, not the mutation.
    """
    pytest.importorskip(
        "omnidriver.openfoam.apply_overrides",
        reason="omnidriver-openfoam is not installed",
    )
    context = _context()
    # `.plugin` was the retired single-plugin field (Task 7); `_context()`
    # builds a one-provider stack, so the sole provider is `.providers[-1]`.
    assert not hasattr(context.providers[-1], "apply_overrides"), (
        "this test exists to exercise the FALLBACK; the minimal plugin must "
        "not implement the hook"
    )

    # A malformed override: validate_overrides rejects it before any file is
    # touched. Reaching that rejection proves the context arrived -- a missing
    # one raises TypeError before validation runs at all.
    with pytest.raises(ValueError) as excinfo:
        context.capabilities.override_scopes.apply(
            [{"not_a_driver_path": "x"}], case_root="/tmp", driver_context=context,
        )
    assert not isinstance(excinfo.value, TypeError), (
        "TypeError means the context never reached omnidriver.openfoam; "
        "ValueError means it did and the override was rejected on its merits"
    )


def test_the_fallback_refuses_cleanly_when_openfoam_is_not_installed(monkeypatch) -> None:
    """No omnidriver-openfoam, no plugin-implemented apply_overrides() hook:
    the fallback must raise a clean ValueError naming the gap, not a raw
    ModuleNotFoundError -- there is no neutral default for "patch a dict file
    whose syntax core does not know" (future/ENVIRONMENT_CONTRACT.md §10,
    Tier 3). ``sys.modules[name] = None`` is the standard way to make Python's
    import system raise ImportError for one module without touching any
    other test's already-imported state.
    """
    monkeypatch.setitem(sys.modules, "omnidriver.openfoam.apply_overrides", None)

    context = _context()
    with pytest.raises(ValueError, match="apply_overrides"):
        context.capabilities.override_scopes.apply(
            [], case_root="/tmp", driver_context=context,
        )


def test_custom_mutator_must_declare_its_complete_target_set(tmp_path: Path) -> None:
    class CustomMutator(minimal_plugin.MinimalTestPlugin):
        def apply_overrides(self, overrides, *, case_root, driver_context):
            del overrides, case_root, driver_context

    context = driver_context(CustomMutator(), source="test:custom-mutator")

    with pytest.raises(ValueError, match="get_override_target_paths"):
        context.capabilities.override_scopes.target_paths(
            [], case_root=tmp_path, driver_context=context,
        )


def test_custom_target_declaration_is_exposed_without_mutating(tmp_path: Path) -> None:
    class DeclaredMutator(minimal_plugin.MinimalTestPlugin):
        def apply_overrides(self, overrides, *, case_root, driver_context):
            del overrides, case_root, driver_context

        def get_override_target_paths(self, overrides, *, case_root, driver_context):
            del overrides, driver_context
            return (case_root / "system" / "fvSchemes",)

    context = driver_context(DeclaredMutator(), source="test:declared-mutator")

    assert context.capabilities.override_scopes.target_paths(
        [], case_root=tmp_path, driver_context=context,
    ) == (tmp_path / "system" / "fvSchemes",)
