"""Provenance declarations' shapes."""

from __future__ import annotations


def test_extra_provenance_paths_is_annotated_as_dependencies():
    """A bare Path can only omit, and omission reads as nothing-to-check."""
    import typing
    from omnidriver.core import plugin_interface

    hints = typing.get_type_hints(
        plugin_interface.SolverPlugin.get_extra_provenance_paths, vars(plugin_interface), include_extras=True,
    )
    assert "RuntimeDependency" in str(hints["return"]), (
        f"annotation is {hints['return']!r}, not a RuntimeDependency tuple"
    )


def test_the_named_catalogues_do_not_hand_out_a_live_catalog():
    """One of the model catalogues is mutated at import."""
    import pytest
    pytest.importorskip("omnidriver.cardiacfoam")
    from omnidriver.cardiacfoam import ionic_model_catalog
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    named = CardiacFoamPlugin().get_named_catalogs()
    assert named["ionic_model_catalog"]["ionic_models"] is not ionic_model_catalog.IONIC_MODEL_CATALOG
