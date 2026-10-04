"""``constant/prePacingProperties`` is judged against its catalogue document before a case runs."""

from __future__ import annotations

from pathlib import Path

from omnidriver.cardiacfoam.validation import case_diagnostics

HEADER = "FoamFile { version 2.0; format ascii; class dictionary; object x; }\n"


def _case(tmp_path: Path, *, solver: str = "monodomainSolver", pre_pacing: str = "") -> Path:
    constant = tmp_path / "constant"
    constant.mkdir()
    (constant / "electroProperties").write_text(
        HEADER + f"myocardiumSolver {solver};\n{solver}Coeffs {{ ionicModel BuenoOrovio; }}\n"
    )
    (constant / "physicsProperties").write_text(HEADER + "type electroModel;\n")
    if pre_pacing:
        (constant / "prePacingProperties").write_text(HEADER + pre_pacing + "\n")
    return tmp_path


def _messages(case: Path, document: str) -> set[str]:
    return {item.message for item in case_diagnostics(case) if item.source == f"constant/{document}"}


def test_a_value_outside_a_pre_pacing_menu_is_refused(tmp_path):
    case = _case(tmp_path, pre_pacing="singleCellIonicModel NoSuchModel;\nbatchedIntegrator rk4;")
    messages = _messages(case, "prePacingProperties")
    assert any(m.startswith("singleCellIonicModel is 'NoSuchModel', not one of the values") for m in messages)
    assert any(m.startswith("batchedIntegrator is 'rk4', not one of the values") for m in messages)


def test_a_region_block_is_judged_like_the_root(tmp_path):
    case = _case(tmp_path, pre_pacing="regions { epicardialCells { singleCellIonicModel NoSuchModel; maxBeats 5; } }")
    messages = _messages(case, "prePacingProperties")
    assert any(m.startswith("regions.epicardialCells.singleCellIonicModel is 'NoSuchModel'") for m in messages)
    assert not any("maxBeats" in m for m in messages)


def test_a_valid_pre_pacing_file_breaks_nothing(tmp_path):
    case = _case(tmp_path, pre_pacing="tolerance 1e-4;\nsingleCellIonicModel TNNPcompactBatched;\nsingleCellStimulus { stim_start 0; }")
    assert _messages(case, "prePacingProperties") == set()


def test_a_solver_that_never_reads_pre_pacing_is_not_judged_by_it(tmp_path):
    case = _case(tmp_path, solver="singleCellSolver", pre_pacing="singleCellIonicModel NoSuchModel;")
    assert _messages(case, "prePacingProperties") == set()

