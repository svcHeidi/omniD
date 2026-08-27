"""Tests for omnidriver.core.strict_planning's mesh-geometry adapter.

_mesh_geometry_diagnostics lives in core (it wraps detection into
StrictDiagnostics for the plan report and owns the exempt/env-var gating),
but its default detection backend is openfoam's mesh_geometry module -- a
genuinely non-OpenFOAM plugin would have to override
get_base_mesh_geometry_diagnostics itself (see compatibility.py). These
tests exercise that default path, so they need omnidriver.openfoam
installed even though the function under test is a core symbol.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import generic_openfoam_context
from omnidriver.core.strict_planning import _mesh_geometry_diagnostics

_FOAM_HEADER = (
    "FoamFile\n{\n version 2.0;\n format ascii;\n"
    ' arch "LSB;label=32;scalar=64";\n class vectorField;\n'
    " object points;\n}\n"
)


def _write_unit_mesh(case_root: Path) -> None:
    """A [0,1] unit-domain mesh: max_dim == 1.0."""
    pm = case_root / "constant" / "polyMesh"
    pm.mkdir(parents=True)
    pm.joinpath("points").write_text(_FOAM_HEADER + "\n2\n(\n(0 0 0)\n(1 1 1)\n)\n")


def test_mesh_adapter_flags_non_si(tmp_path: Path) -> None:
    pm = tmp_path / "constant" / "polyMesh"
    pm.mkdir(parents=True)
    pm.joinpath("points").write_text(
        _FOAM_HEADER + "\n2\n(\n(0 0 0)\n(50 50 50)\n)\n"
    )
    diags = _mesh_geometry_diagnostics(tmp_path, driver_context=generic_openfoam_context())
    codes = {d.code for d in diags}
    assert "mesh_not_si" in codes
    assert all(d.source == "mesh_geometry" for d in diags)


def test_exempt_short_circuits_unit_domain(tmp_path: Path) -> None:
    # A [0,1] mesh would classify "mm", but an exempt case must not be flagged.
    _write_unit_mesh(tmp_path)
    context = generic_openfoam_context()
    assert _mesh_geometry_diagnostics(tmp_path, exempt=False, driver_context=context) != ()  # baseline
    assert _mesh_geometry_diagnostics(tmp_path, exempt=True, driver_context=context) == ()
