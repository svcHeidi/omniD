"""Phase 3 Task 3: `set_delta_t`/`set_end_time` grow a resolver each.

Characterization tests pin the exact bytes today's writers produce (content
digests, not existence -- an existence check passes for an empty file).

**Corrected 2026-09-23 (Phase 3 Task 6's completion):** `set_end_time` is
retired -- Task 6 migrated its last caller onto `plan_end_time`, and
`grep -rn "set_end_time(" packages/*/src/` (excluding this module's own
former definition) returns zero. `set_delta_t`'s own characterization stays:
it keeps one caller, `niederer_2012.py`'s `mesh_family == "tet"` branch
(a source-artifact route that never migrates onto the channel), so it is not
yet retired.

The rest are the failing-then-passing tests for the pure planners,
`plan_delta_t`/`plan_end_time`: they must address `system/controlDict`'s real
`deltaT`/`endTime` keys, refuse a non-finite value at construction (the same
guard every other `ParameterAssignment` gets, per the Phase 2 decision that
closed R2 finding 4), and touch no file at all -- asserted on a directory
snapshot, since purity is what makes calling a planner free.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from omnidriver.core.case_write import ParameterAssignment
from omnidriver.openfoam.utils import set_delta_t

try:
    # Imported this way, rather than folded into the module-level import
    # above, so the characterization tests below (which need only the
    # existing writers) can still be collected and run against a checkout
    # that predates this task's planners -- proving they pass BEFORE the
    # change, not merely after it. See this task's report for the revert
    # that confirms exactly the planner tests fail without `utils.py`'s
    # change, no more and no fewer.
    from omnidriver.openfoam.utils import plan_delta_t, plan_end_time
except ImportError:
    plan_delta_t = plan_end_time = None

_CONTROL_DICT_TEMPLATE = (
    "FoamFile\n{\n    version 2.0;\n    class dictionary;\n    object controlDict;\n}\n"
    "application     cardiacFoam;\n"
    "startFrom       latestTime;\n"
    "startTime       0;\n"
    "stopAt          endTime;\n"
    "endTime         1;\n"
    "deltaT          1e-06;\n"
    "writeControl    adjustableRunTime;\n"
    "writeInterval   0.1;\n"
)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _snapshot(directory) -> dict:
    """A digest per file under `directory`, keyed by relative path -- proves
    a call touched nothing, not merely that one particular file is absent."""
    return {
        str(path.relative_to(directory)): _digest(path.read_text())
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


# ---------------------------------------------------------------------------
# Characterization: today's writers, pinned by content digest.
# ---------------------------------------------------------------------------


#: `update_foam_entry` rewrites a whole-line entry as `<indent><key>    <value>;`
#: -- four spaces, not the original column alignment (verified against the
#: actual writer, not assumed: the template's `deltaT          1e-06;`
#: becomes `deltaT    0.001;`, and `endTime         1;` becomes
#: `endTime    250.0;`, `str(250.0)` carrying its `.0` through unchanged).
_EXPECTED_AFTER_DELTA_T = _CONTROL_DICT_TEMPLATE.replace(
    "deltaT          1e-06;", "deltaT    0.001;"
)


def test_set_delta_t_characterization_spelled_as_exponent(tmp_path):
    """`set_delta_t(..., 1e-3)` today. Pinned by content digest, not a
    substring or existence check."""
    path = tmp_path / "controlDict"
    path.write_text(_CONTROL_DICT_TEMPLATE)
    set_delta_t(path, 1e-3)
    assert _digest(path.read_text()) == _digest(_EXPECTED_AFTER_DELTA_T)


def test_set_delta_t_characterization_spelled_as_decimal(tmp_path):
    """`set_delta_t(..., 0.001)` -- the same float as `1e-3` -- today."""
    path = tmp_path / "controlDict"
    path.write_text(_CONTROL_DICT_TEMPLATE)
    set_delta_t(path, 0.001)
    assert _digest(path.read_text()) == _digest(_EXPECTED_AFTER_DELTA_T)


def test_both_spellings_of_the_same_float_write_identical_bytes_today(tmp_path):
    """`1e-3` and `0.001` are the same Python float (`1e-3 == 0.001`), and
    `_format_value` renders it with `str()` -- so today's writer already
    collapses both spellings to the same output. This is the characterization
    this task's Step 2 asks for: capturing that collapse, not merely one
    value, is what proves nothing regresses when the planners are added."""
    path_a = tmp_path / "a" / "controlDict"
    path_b = tmp_path / "b" / "controlDict"
    path_a.parent.mkdir()
    path_b.parent.mkdir()
    path_a.write_text(_CONTROL_DICT_TEMPLATE)
    path_b.write_text(_CONTROL_DICT_TEMPLATE)

    set_delta_t(path_a, 1e-3)
    set_delta_t(path_b, 0.001)

    assert _digest(path_a.read_text()) == _digest(path_b.read_text())


# ---------------------------------------------------------------------------
# The planners: pure, typed, no filesystem access.
# ---------------------------------------------------------------------------


def test_plan_delta_t_addresses_control_dict_delta_t():
    assignment = plan_delta_t(1e-3, owner="test.owner")
    assert isinstance(assignment, ParameterAssignment)
    assert assignment.document == "system/controlDict"
    assert assignment.key_path == ("deltaT",)
    assert assignment.value_kind == "scalar"
    assert assignment.value == 1e-3
    assert assignment.source == "case"


def test_plan_end_time_addresses_control_dict_end_time():
    assignment = plan_end_time(250.0, owner="test.owner")
    assert isinstance(assignment, ParameterAssignment)
    assert assignment.document == "system/controlDict"
    assert assignment.key_path == ("endTime",)
    assert assignment.value_kind == "scalar"
    assert assignment.value == 250.0
    assert assignment.source == "case"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_plan_delta_t_refuses_non_finite_value(bad):
    with pytest.raises(ValueError):
        plan_delta_t(bad, owner="test.owner")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_plan_end_time_refuses_non_finite_value(bad):
    with pytest.raises(ValueError):
        plan_end_time(bad, owner="test.owner")


def test_plan_delta_t_refuses_a_rendered_string_rather_than_coercing_it():
    """A bare `controlDict` scalar has no literal grammar to parse (no
    dimension brackets), so there is nothing to parse a string INTO -- the
    planner must refuse it, not silently `float()` it and discard the
    original spelling. Coercing here would be exactly the silent-lossy-
    conversion defect this repository's own literals work exists to avoid."""
    with pytest.raises(ValueError):
        plan_delta_t("1e-3", owner="test.owner")


def test_plan_end_time_refuses_a_rendered_string_rather_than_coercing_it():
    with pytest.raises(ValueError):
        plan_end_time("1.0", owner="test.owner")


def test_plan_delta_t_value_survives_either_spelling_of_the_same_float():
    """`1e-3` and `0.001` are the same float; the planner must not lose or
    re-derive the value it was given -- it carries it through unchanged."""
    assert plan_delta_t(1e-3, owner="test.owner").value == 0.001
    assert plan_delta_t(0.001, owner="test.owner").value == 1e-3


def test_plan_delta_t_touches_no_file(tmp_path):
    """Purity is what makes a dry run free: calling the planner must not
    create, modify, or delete anything on disk. Asserted on a full directory
    snapshot (content digests), not a single path's existence -- an existence
    check would pass even if some OTHER file were touched."""
    (tmp_path / "system").mkdir()
    control_dict = tmp_path / "system" / "controlDict"
    control_dict.write_text(_CONTROL_DICT_TEMPLATE)
    before = _snapshot(tmp_path)

    plan_delta_t(1e-3, owner="test.owner")
    plan_end_time(250.0, owner="test.owner")

    after = _snapshot(tmp_path)
    assert after == before


def test_plan_delta_t_qualified_id_is_the_concrete_key():
    # Matches `resolve_entry_overrides`'s established convention: the
    # concrete dotted key path, not an abstract template.
    assert plan_delta_t(1e-3, owner="test.owner").qualified_id == "deltaT"


def test_plan_end_time_qualified_id_is_the_concrete_key():
    assert plan_end_time(250.0, owner="test.owner").qualified_id == "endTime"
