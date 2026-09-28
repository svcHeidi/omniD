"""cardiacCore gains ``--apply`` by composition, not by writing an
implementation: six one-line delegations replace parallel override
machinery reachable only through ``TutorialSpec.apply_case``."""

import inspect

import pytest

from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


def test_the_plugin_no_longer_embeds_an_environment_adapter():
    source = inspect.getsource(CardiacCorePlugin)
    assert "OpenFOAMEnvironmentPlugin()" not in source, (
        "a provider must not embed another provider"
    )
    assert "_openfoam" not in source


@pytest.fixture
def cardiaccore_stack_context():
    """A composed :class:`DriverContext` over the real environment adapter
    and :class:`CardiacCorePlugin`, exactly as a real installation composes
    them: cardiacCore declares ``requires:`` the environment id, so a bare
    ``driver_context(CardiacCorePlugin(), source=...)`` raises."""
    return driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test",
    )


@pytest.fixture
def tmp_case(tmp_path):
    """A minimal case directory -- override application must not require any
    particular dictionary to already exist on disk."""
    case_root = tmp_path / "case"
    case_root.mkdir()
    return case_root


def test_applying_overrides_is_supported(cardiaccore_stack_context, tmp_case):
    scopes = cardiaccore_stack_context.capabilities.override_scopes
    # `[]`, not `{}`: `validate_overrides` requires a JSON list of
    # `{driver_path, value}` objects. Passing `driver_context=` explicitly
    # is required too -- `_OverrideScopeAdapter.apply` has no default for
    # it, a deliberate guard against a silently-resolved context.
    scopes.apply(
        [], case_root=tmp_case, driver_context=cardiaccore_stack_context,
    )  # must not raise
