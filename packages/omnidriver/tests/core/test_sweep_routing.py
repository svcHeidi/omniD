"""Tests routing of resolved sweep values to build_and_launch parameters.

Phase 2 Task M2: every test that asserted cardiacFoam's own routing
catalog (electro_selectors/electro_overrides shapes, dict-builder text
placement) moved to
packages/omnidriver-cardiacfoam/tests/test_sweep_routing.py. What
remains here is core's own refusal-by-name mechanism: routing consults
the SELECTED plugin rather than a hardcoded cardiac vocabulary, and a
plugin lacking route_sweep_case_values() is told so by name instead of
silently running cardiac validation over its axes.
"""

import pytest

from omnidriver.core.sweep.sweep_expansion import SweepValidationError
from omnidriver.sweep_routing import route_case_values
from omnidriver.core.plugin_interface import generic_openfoam_context


def test_routing_uses_the_selected_plugin_catalog():
    # Originally this asserted that "type" (a cardiac physicsProperties
    # selector) is "not a recognized selector" under the generic plugin's
    # catalog -- i.e. that routing consults the SELECTED plugin rather than a
    # hardcoded cardiac vocabulary.
    #
    # Gating legacy_route_sweep_case makes that point more strongly: the
    # generic plugin does not implement route_sweep_case_values() at all, so
    # routing refuses outright instead of running cardiac validation over a
    # non-cardiac plugin's axes. The refusal names the missing hook, so the
    # message tells a plugin author what to implement.
    with pytest.raises(SweepValidationError, match="route_sweep_case_values"):
        route_case_values(
            base={},
            resolved_axis_values={"type": "electroModel"},
            driver_context=generic_openfoam_context(),
        )
