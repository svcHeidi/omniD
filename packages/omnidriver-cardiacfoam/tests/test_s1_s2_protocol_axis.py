"""Step 4b (pilot ``restitutionCurves``): the S1-S2 protocol axis.

Owner instruction for step 4b, item 2: "an S1-S2 protocol axis: a mapping
value (the protocol's parameters) gives the singleCellStimulus keys it sets
plus the derived ``system/controlDict:endTime`` and ``writeAfterTime``,
using the old module's arithmetic, not new formulas. An axis must not
silently read case values that the same study could also patch directly;
take the protocol as the axis value."

"The old module's arithmetic" is
``cardiacfoam.tutorials.restitution_curves._plan_case``/``make_spec``
(deleted alongside this pilot, once parity is proven):

    write_after_time_s = (s1_interval_ms * (n_s1 - 1)) / 1000.0 - 2.0
    end_time = (
        (s1_interval_ms * (n_s1 - 1) + s2_interval_ms * n_s2) / 1000.0
        + 2.0  # end_time_buffer_s, never varied by any real study
    )

This module's tests recompute those same two formulas independently (not by
importing the now-deleted old module) and check the axis's output against
them -- byte-for-byte parity against the real native case is proven
separately, by the native parity test/evidence for the whole record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.cardiacfoam.records.s1_s2_protocol_axis import s1_s2_protocol_axis

_ELECTRO_DOCUMENT = "constant/electroProperties"
_CONTROL_DICT_DOCUMENT = "system/controlDict"
_SCOPE = ("singleCellSolverCoeffs",)


def _axis():
    return s1_s2_protocol_axis(
        "s1s2Protocol", electro_document=_ELECTRO_DOCUMENT, scope=_SCOPE,
    )


def _staged_case(tmp_path: Path) -> Path:
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "system").mkdir(parents=True)
    (case_root / "constant" / "electroProperties").write_text("myocardiumSolver singleCellSolver;\n")
    (case_root / "system" / "controlDict").write_text("application cardiacFoam;\n")
    return case_root


def _protocol(**overrides):
    protocol = {
        "s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2, "s2_interval_ms": 1500,
    }
    protocol.update(overrides)
    return protocol


def test_axis_declares_a_mapping_value_kind():
    axis = _axis()
    assert axis.value_kind == "mapping"


def test_the_native_default_protocol_reproduces_the_checked_in_case(tmp_path):
    """s1=2000, n_s1=10, s2=250, n_s2=2 is the combination the CHECKED-IN
    native electroProperties/controlDict hold today (writeAfterTime 16.0,
    endTime 20.5) -- the exact old-module arithmetic, reproduced here."""
    axis = _axis()
    case_root = _staged_case(tmp_path)

    result = axis.resolve(
        _protocol(s1_interval_ms=2000, s2_interval_ms=250), case_root,
    )

    by_key_path = {patch.key_path: patch for patch in result.patches}
    assert by_key_path[("singleCellSolverCoeffs", "singleCellStimulus", "stim_period_S1")].value == 2000
    assert by_key_path[("singleCellSolverCoeffs", "singleCellStimulus", "nstim1")].value == 10
    assert by_key_path[("singleCellSolverCoeffs", "singleCellStimulus", "stim_period_S2")].value == 250
    assert by_key_path[("singleCellSolverCoeffs", "singleCellStimulus", "nstim2")].value == 2
    write_after_time = by_key_path[("singleCellSolverCoeffs", "writeAfterTime")]
    assert write_after_time.value == pytest.approx(16.0)
    assert write_after_time.document == _ELECTRO_DOCUMENT
    end_time = by_key_path[("endTime",)]
    assert end_time.value == pytest.approx(20.5)
    assert end_time.document == _CONTROL_DICT_DOCUMENT


def test_the_driver_config_protocol_computes_the_old_arithmetic(tmp_path):
    """The native ``driver_config.json``'s own real intent (TWorld, s1=1000,
    n_s1=10, n_s2=2), for the smallest S2 in its list (250)."""
    axis = _axis()
    case_root = _staged_case(tmp_path)

    result = axis.resolve(
        _protocol(s1_interval_ms=1000, n_s1=10, n_s2=2, s2_interval_ms=250),
        case_root,
    )

    by_key_path = {patch.key_path: patch for patch in result.patches}
    write_after_time = by_key_path[("singleCellSolverCoeffs", "writeAfterTime")].value
    end_time = by_key_path[("endTime",)].value
    assert write_after_time == pytest.approx((1000 * 9) / 1000.0 - 2.0)
    assert end_time == pytest.approx((1000 * 9 + 250 * 2) / 1000.0 + 2.0)


def test_a_protocol_missing_a_required_key_is_refused_by_name(tmp_path):
    axis = _axis()
    case_root = _staged_case(tmp_path)

    with pytest.raises(ValueError, match="s2_interval_ms"):
        axis.resolve(
            {"s1_interval_ms": 1000, "n_s1": 10, "n_s2": 2}, case_root,
        )
