"""niedererNVersion's two mesher axes reach one step together."""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.tutorial_records import TutorialRecordError, resolve_case_patches
from omnidriver.opencarp.records.niederer_n_version import RECORD

MESH = RECORD.workflow_steps[0]


def _mesh_argv(study):
    _, arguments, replacements = resolve_case_patches(
        RECORD, study_by_source={"base": study}, staged_case_root=Path("/nonexistent"),
        direct_key_validator=lambda document, key_path, value: ("scalar", True),
    )
    return MESH.argv(arguments.get("mesh", ()), replacements.get("mesh"))


def test_dx_alone_runs_mesher_with_its_default_imbrication():
    argv = _mesh_argv({"dx": 500.0})
    assert argv[-8:] == ("-fibers.imbrication", "0", "-resolution[0]", "500.0", "-resolution[1]", "500.0", "-resolution[2]", "500.0")


def test_dx_and_imbrication_compose_on_the_mesh_step():
    argv = _mesh_argv({"dx": 200.0, "fibers.imbrication": 90})
    assert argv.count("-fibers.imbrication") == 1
    assert argv[argv.index("-fibers.imbrication") + 1] == "90.0"
    assert argv[argv.index("-resolution[0]") + 1] == "200.0"


def test_a_non_finite_imbrication_is_refused():
    with pytest.raises(TutorialRecordError, match="fibers.imbrication"):
        _mesh_argv({"dx": 500.0, "fibers.imbrication": float("nan")})


def test_the_replaced_imbrication_keeps_its_declared_slot_before_the_resolution():
    argv = _mesh_argv({"dx": 500.0, "fibers.imbrication": 90})
    assert argv[-8:] == ("-fibers.imbrication", "90.0", "-resolution[0]", "500.0", "-resolution[1]", "500.0", "-resolution[2]", "500.0")
    assert argv[:-8][-2:] == ("-mesh", "slab")


def test_the_axes_state_their_units_and_a_positive_resolution():
    axes = {axis.name: axis.to_json() for axis in RECORD.axes}
    assert (axes["dx"]["unit"], axes["dx"]["exclusive_minimum"]) == ("um", 0)
    assert axes["fibers.imbrication"]["unit"] == "deg"
    for value in (0, -500.0):
        with pytest.raises(TutorialRecordError, match=r"axis 'dx' is .*outside its bounds: must be more than 0"):
            _mesh_argv({"dx": value})
