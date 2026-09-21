"""cardiacCore gains --apply by composition, not by writing an implementation.

Six one-line delegations were never written, so `legacy_apply_overrides`
raised and strict applying was refused for this adapter entirely -- while the
package maintained parallel override machinery reachable only through
`TutorialSpec.apply_case`.

``cardiaccore_stack_context`` composes the real installed OpenFOAM
environment adapter with ``CardiacCorePlugin``, mirroring how a production
``DriverContext`` for this plugin is built once it declares
``requires: [org.omnidriver.openfoam.environment]`` -- a bare
``driver_context(CardiacCorePlugin(), source=...)`` now raises, because that
declared requirement is unmet by a single-provider stack.

``test_applying_overrides_is_supported`` passes ``driver_context=`` to
``apply()`` explicitly: ``_OverrideScopeAdapter.apply`` has no default for
that keyword (see ``test_override_apply_threads_a_context.py`` -- omitting it
is a *deliberate* ``TypeError`` guard against a silently-resolved context),
so a call omitting it would fail for the wrong reason.
"""

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
    them now that cardiacCore declares ``requires:`` the environment id."""
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
    # `[]`, not `{}`: `apply_overrides.validate_overrides` requires a JSON
    # list of `{driver_path, value}` objects -- confirmed by running this
    # test with `{}` and getting `OverrideError`, not the `TypeError` the
    # (now-fixed) missing `driver_context=` produced.
    scopes.apply(
        [], case_root=tmp_case, driver_context=cardiaccore_stack_context,
    )  # must not raise
