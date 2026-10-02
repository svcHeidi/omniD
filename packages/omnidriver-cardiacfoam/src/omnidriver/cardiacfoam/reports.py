"""cardiacFoam's report catalog.

Accessed through ``driver_context.capabilities.report_catalog.reports()``.
"""

from __future__ import annotations

from omnidriver.core.report_catalog import ReportDefinition, STUB_URL, URL_TEMPLATE

CARDIAC_REPORTS: tuple[ReportDefinition, ...] = (
    ReportDefinition(
        id="vm-field-3d",
        title="Vm field (3D)",
        kind="iframe",
        url_template=URL_TEMPLATE,
        applicable_when=None,  # always available post-completion
        show_by_default=True,
        description=(
            "Volumetric Vm field rendered by 4Dpapers from the run's "
            "foam/VTK output."
        ),
    ),
    ReportDefinition(
        id="activation-map",
        title="Activation map",
        kind="iframe",
        url_template=URL_TEMPLATE,
        applicable_when=None,
        show_by_default=True,
        description=(
            "Local activation time map. Useful for checking conduction "
            "patterns and reentry."
        ),
    ),
    ReportDefinition(
        id="stub",
        title="Stub (4Dpapers not running)",
        kind="iframe",
        url_template=STUB_URL,
        applicable_when=None,
        show_by_default=False,
        description=(
            "Bundled fallback that renders when the 4Dpapers backend is "
            "not reachable. Visible for diagnostics, not by default."
        ),
    ),
)
