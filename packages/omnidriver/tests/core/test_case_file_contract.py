"""Case-file declarations are consumed generically by Core."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from plugins.minimal_plugin import MinimalTestPlugin


def test_minimal_plugin_declares_no_case_files() -> None:
    context = driver_context(
        MinimalTestPlugin(), source="test:minimal-case-files",
    )
    contract = context.capabilities.case_files
    assert contract.required_files() == ()
    assert contract.conditional_files() == ()
    assert context.capabilities.case_runtime_conventions.conventions() == CaseRuntimeConventions()
    assert context.capabilities.case_introspection.selected_start_time(
        Path("case"), {}, driver_context=context,
    ) is None


def test_conditional_files_are_separated_from_required() -> None:
    """Exercises `_CaseFileContractAdapter`'s always/conditional split -- core
    mechanics, not solver vocabulary. ``MinimalTestPlugin(entrypoint=...)``
    makes the test-only ``run-test-case`` entrypoint explicit; the mechanic
    under test is that conditional files are excluded from ``required_files``.
    """
    contract = driver_context(
        MinimalTestPlugin(entrypoint="run-test-case"), source="test"
    ).capabilities.case_files
    assert "run-test-case" in contract.conditional_files()
    assert "run-test-case" not in contract.required_files()


def test_apply_returns_the_plugins_records() -> None:
    """The adapter must not swallow what the plugin reports it changed.

    Phase 0 Task 8 defect 1: ``_OverrideScopeAdapter.apply`` used to call the
    plugin hook and then unconditionally ``return ()``, discarding whatever
    records the hook reported.
    """
    from omnidriver.core import plugin_capabilities

    sentinel = ({"path": "constant/x", "key": "a", "old": "1", "new": "2"},)

    class _Plugin:
        def apply_overrides(self, overrides, *, case_root, driver_context):
            del overrides, case_root, driver_context
            return sentinel

        def get_override_target_paths(self, overrides, *, case_root, driver_context):
            del overrides, case_root, driver_context
            return ()

    adapter = plugin_capabilities._OverrideScopeAdapter(plugin=_Plugin())
    assert adapter.apply({}, case_root=None, driver_context=None) == sentinel


def test_openfoam_environment_hooks_thread_the_callers_context(tmp_path: Path) -> None:
    """The OpenFOAM environment plugin's ``apply_overrides``/
    ``get_override_target_paths`` hooks must resolve scopes and catalog
    entries from the *caller's* ``DriverContext``, not one they build from
    themselves.

    Phase 0 Task 8 defect 2: both hooks used to call
    ``make_driver_context(self, source="adapter:openfoam-environment")``,
    discarding whatever context the caller supplied. That self-built context
    always wraps the bare ``OpenFOAMEnvironmentPlugin``, whose catalog and
    override scopes are empty -- so a caller with richer vocabulary (the
    shape a cardiacFoam-contexted ``--apply`` would take, mirroring how
    ``get_loaded_environment``/``get_configured_environment`` already forward
    the context they are given a few lines below in openfoam/environment.py)
    would silently lose it.

    This is a behavioural test rather than the plan's ``inspect.getsource``
    source-text assertion: a source-grep only proves the string
    ``make_driver_context(`` is absent, not that the caller's context is
    actually the one consulted. The plugin below stands in for a
    cardiacFoam-ish caller -- it declares an override scope and a catalog
    entry the bare OpenFOAM environment plugin does not know about -- without
    importing ``omnidriver.cardiacfoam`` (openfoam must not know about
    cardiology; only the test simulates a caller that does). Before the fix
    this raises ``OverrideError: ... unknown scope token`` (or, before
    Step 4's signature change, ``TypeError`` for an unexpected
    ``driver_context`` keyword) because the substituted context's catalog and
    scopes are always empty; after the fix the caller's scope resolves.
    """
    pytest.importorskip(
        "omnidriver.openfoam.environment", reason="omnidriver-openfoam is not installed",
    )
    from omnidriver.core.contracts.dictionary import DictEntry
    from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
    from omnidriver.openfoam.apply_overrides import OverrideScope
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    class _CardiacIshPlugin(OpenFOAMEnvironmentPlugin):
        """A caller-side plugin with vocabulary the bare environment plugin
        lacks -- standing in for a cardiacFoam-contexted caller."""

        def get_dictionary_catalog(self):
            return DictionaryCatalog({
                "electroProperties": (
                    DictEntry(
                        driver_path="$ELECTRO_MODEL_COEFFS.myocardiumSolver",
                        description="test-only cardiac-ish entry",
                    ),
                ),
            })

        def get_override_scopes(self):
            return (
                OverrideScope(
                    token="ELECTRO_MODEL_COEFFS",
                    file_relpath="constant/electroProperties",
                    catalog_group="electroProperties",
                    resolve_entry=lambda dp, case_root: (None, "myocardiumSolver"),
                ),
            )

    caller_context = driver_context(
        _CardiacIshPlugin(), source="test:cardiac-ish-caller",
    )

    plugin = OpenFOAMEnvironmentPlugin()
    targets = plugin.get_override_target_paths(
        [{"driver_path": "$ELECTRO_MODEL_COEFFS.myocardiumSolver", "value": "eikonal"}],
        case_root=tmp_path,
        driver_context=caller_context,
    )
    assert targets == (tmp_path / "constant" / "electroProperties",)
