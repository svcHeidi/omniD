"""Task 10: the four duplicate intakes Phase 0 deferred until providers could
compose (Tasks 6-9 built that composition).

1. Two independently-authored "what may config contain" schemas
   (``OverrideSchemaCapability.config_schema()`` vs
   ``RunDocumentConfigurationCapability.schema()``) collapse to one source.
2. ``CardiacFoamPlugin.get_capabilities()`` no longer assembles the whole
   manifest itself and hands it back to core -- core builds it from
   capabilities it already holds.
3. ``registry._is_case_directory``'s ``has_case_marker(...) or
   _has_entrypoint(...)`` collapses into one composed
   ``case_compatibility.is_case(...)``.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def stack_context():
    """A composed :class:`DriverContext` over the real, installed OpenFOAM
    environment adapter and :class:`CardiacCorePlugin`.

    Mirrors ``cardiaccore_stack_context`` in
    ``packages/omnidriver-cardiaccore/tests/test_apply_works_through_the_stack.py``
    -- the established pattern this brief points to for composing real
    installed adapters via ``driver_context(*providers, source=...)``, rather
    than wrapping a single-provider fixture or fabricating a test double.
    cardiacCore is picked over cardiacFoam deliberately: cardiacFoam's
    ``get_override_schema`` always answers with real, tutorial-specific
    content (by design -- see
    ``omnidriver-cardiacfoam/tests/test_override_schema_capability.py``), so
    it never exercises the "no plugin-specific answer" branch
    ``test_config_schema_has_one_source`` targets; cardiacCore's does, for an
    unrecognized tutorial name.

    Skips (does not error) when the sibling packages are not installed --
    this module also lives under core's own test tree, which the "core
    alone" verification shape (CLAUDE.md) runs without them installed.
    """
    pytest.importorskip("omnidriver.cardiaccore")
    pytest.importorskip("omnidriver.openfoam")
    from omnidriver.cardiaccore.plugin import CardiacCorePlugin
    from omnidriver.core.plugin_interface import driver_context
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    return driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test:deferred-duplicate-intakes",
    )


def test_config_schema_has_one_source(stack_context):
    """Two capabilities answered "what may config contain"."""
    caps = stack_context.capabilities
    assert (
        caps.override_schema.config_schema("any", {})
        == caps.run_document_configuration.schema()
    ), "the two config schemas must no longer be independently authored"


def test_core_builds_the_capability_manifest(stack_context):
    """The plugin must not assemble what core can compose.

    The round trip delivered six declarations to core twice, and the manifest
    copy was what landed in the identity digest.
    """
    import inspect
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    source = inspect.getsource(CardiacFoamPlugin.get_capabilities)
    assert "build_capability_manifest" not in source


def test_a_case_is_recognised_by_one_predicate(stack_context):
    caps = stack_context.capabilities
    assert hasattr(caps.case_compatibility, "is_case")
