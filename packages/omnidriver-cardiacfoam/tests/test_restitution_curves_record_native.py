"""Step 4b (pilot) of docs/superpowers/specs/2026-09-24-tutorials-are-pointers-
design.md against the REAL native cardiacFOAM tutorials tree (CLAUDE.md's
"testing against real meshes": real case or native-source drift gate,
nothing invented). ``OMNIDRIVER_NATIVE_TUTORIALS`` is supplied, never
discovered -- every test here FAILS, not skips, when it is unset (pattern
copied from ``test_record_key_validation_native.py``).

Covers the two native-evidence claims design step 4b's own instructions
make:

1. **The zero-changes design test (design §6).** ``restitutionCurves``,
   previewed with NO study values at all against the real native case,
   proposes ZERO changed patches -- the native case IS the default, with no
   Python restating it.
2. **The catalog migration's own native confirmation.** The ionic model
   catalog's ``single_cell_stimulus_amplitude`` field docstring claims
   ``TWorld`` reads ``60`` and ``BuenoOrovio`` reads ``0.4`` against real
   checked-in cases -- checked here against BOTH real files (``singleCell``'s
   own default case for ``TWorld``, ``restitutionCurves_s1s2Protocol``'s own
   default case for ``BuenoOrovio``), and cross-checked against the
   ``ionicModel`` axis's own output for each.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.records.restitution_curves import AXES, RECORD
from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.runtime import record_execution

pytestmark = pytest.mark.native

_RESTITUTION_CURVES_RELPATH = "electrophysiologyProtocols/restitutionCurves_s1s2Protocol"
_SINGLE_CELL_RELPATH = "electrophysiologyProtocols/singleCell"


def _native_tutorials_root() -> Path:
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly via that environment variable -- it is never "
            "discovered. Run e.g.:\n"
            "  OMNIDRIVER_NATIVE_TUTORIALS=/path/to/tutorials "
            "pytest -m native"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_NATIVE_TUTORIALS={value!r} is not a directory")
    return root


def _cardiac_stack():
    return load_discovered_plugin("cardiacfoam")


def _read_stim_amplitude(case_root: Path) -> float:
    text = (case_root / "constant" / "electroProperties").read_text()
    match = re.search(r"stim_amplitude\s+([^\s;]+);", text)
    assert match is not None, f"fixture {case_root} has no stim_amplitude entry"
    return float(match.group(1))


def _read_ionic_model(case_root: Path) -> str:
    text = (case_root / "constant" / "electroProperties").read_text()
    match = re.search(r"ionicModel\s+([^\s;]+);", text)
    assert match is not None, f"fixture {case_root} has no ionicModel entry"
    return match.group(1)


# ---------------------------------------------------------------------------
# 1. Design §6's own per-tutorial test: zero changes with no study values.
# ---------------------------------------------------------------------------


def test_restitution_curves_preview_with_no_study_values_shows_zero_changes():
    tutorials_root = _native_tutorials_root()
    case_root = tutorials_root / _RESTITUTION_CURVES_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    context = _cardiac_stack()

    preview = record_execution.preview_record_case(
        RECORD, cases_root=tutorials_root, study_by_source={},
        driver_context=context,
    )

    assert preview["patches"] == [], (
        "the native case is the default: an empty study must propose "
        f"nothing, got {preview['patches']!r}"
    )
    assert preview["workflow_step_ids"] == ["mesh", "solve"]


# ---------------------------------------------------------------------------
# 2. The catalog migration's native confirmation: TWorld 60, BuenoOrovio 0.4.
# ---------------------------------------------------------------------------


def test_the_single_cell_native_case_confirms_tworld_sixty():
    tutorials_root = _native_tutorials_root()
    case_root = tutorials_root / _SINGLE_CELL_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    assert _read_ionic_model(case_root) == "TWorld"
    native_amplitude = _read_stim_amplitude(case_root)
    assert native_amplitude == 60.0

    axis = AXES["ionicModel"]
    result = axis.resolve("TWorld", case_root)
    by_key_path = {patch.key_path: patch for patch in result.patches}
    axis_amplitude = by_key_path[
        ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude")
    ].value
    assert axis_amplitude == native_amplitude


def test_the_restitution_curves_native_case_confirms_buenoorovio_zero_point_four():
    tutorials_root = _native_tutorials_root()
    case_root = tutorials_root / _RESTITUTION_CURVES_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    assert _read_ionic_model(case_root) == "BuenoOrovio"
    native_amplitude = _read_stim_amplitude(case_root)
    assert native_amplitude == 0.4

    axis = AXES["ionicModel"]
    result = axis.resolve("BuenoOrovio", case_root)
    by_key_path = {patch.key_path: patch for patch in result.patches}
    axis_amplitude = by_key_path[
        ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude")
    ].value
    assert axis_amplitude == native_amplitude


# ---------------------------------------------------------------------------
# 3. commit_record_case against the real cardiac stack + real OpenFOAM
#    dictionary renderer (regression test for the snapshot_root/case_root
#    conflation this pilot found -- see record_execution.commit_record_case's
#    own updated docstring/comment).
# ---------------------------------------------------------------------------


def test_commit_record_case_writes_a_real_case_via_the_real_renderer(tmp_path):
    tutorials_root = _native_tutorials_root()
    case_root = tutorials_root / _RESTITUTION_CURVES_RELPATH
    assert case_root.is_dir(), f"fixture case missing: {case_root}"
    context = _cardiac_stack()
    staged_case_root = tmp_path / "staged"

    result = record_execution.commit_record_case(
        RECORD, cases_root=tutorials_root, staged_case_root=staged_case_root,
        study_by_source={
            "base": {
                "ionicModel": "TWorld",
                "constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells",
            },
            "sweep": {
                "s1s2Protocol": {
                    "s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2,
                    "s2_interval_ms": 250,
                },
            },
        },
        driver_context=context,
    )

    assert result.status == "committed"
    written = (staged_case_root / "constant" / "electroProperties").read_text()
    assert "ionicModel    TWorld;" in written
    assert "stim_amplitude    60.0;" in written
    control_dict = (staged_case_root / "system" / "controlDict").read_text()
    # end_time = (1000 * 9 + 250 * 2) / 1000.0 + 2.0 == 11.5 (the old
    # module's own arithmetic, s1_s2_protocol_axis.py's docstring).
    assert re.search(r"endTime\s+11\.5;", control_dict)
