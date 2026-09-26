"""OpenFOAM strict-planning conventions are adapter-owned.

Corrected 2026-09-26 (spec 2026-09-26 A7): this covered strict_planning's
old name-based exemption heuristic (deleted), which exempted an entry from
mesh-scale checks by matching "manufactured"/"verification" in its name.
That exemption-by-name is deleted; the replacement,
``strict_planning._mesh_geometry_exempt``, asks only the plugin's own
``is_nondimensional_case`` hook (which the plain OpenFOAM environment
adapter does not implement) or ``generic_case``. The two tests that
exercised the name heuristic through this adapter are gone -- the
adapter contributed nothing name-specific, and the hook-only behaviour is
proved once, adapter-neutrally, by
``packages/omnidriver/tests/core/test_mesh_geometry_exemption.py``. Only
the env-var skip, which the adapter's own diagnostics feed into, stays
here.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.strict_planning import _mesh_geometry_diagnostics
from omnidriver.openfoam.environment import openfoam_environment_context


def test_mesh_gate_skipped_by_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SKIP_GEOMETRY_DIAGNOSTICS", "1")
    assert _mesh_geometry_diagnostics(tmp_path, driver_context=openfoam_environment_context()) == ()
