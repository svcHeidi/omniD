"""Tests routing of resolved sweep values to build_and_launch parameters.

Core delegates routing to the selected plugin and refuses when the plugin does
not implement ``route_sweep_case_values``.
"""

import pytest

from omnidriver.core.sweep.sweep_expansion import SweepValidationError
from omnidriver.sweep_routing import route_case_values
from omnidriver.core.plugin_interface import driver_context
from plugins.minimal_plugin import MinimalTestPlugin


def test_routing_uses_the_selected_plugin_catalog():
    with pytest.raises(SweepValidationError, match="route_sweep_case_values"):
        route_case_values(
            base={},
            resolved_axis_values={"type": "electroModel"},
            driver_context=driver_context(
                MinimalTestPlugin(), source="test:sweep-routing",
            ),
        )
