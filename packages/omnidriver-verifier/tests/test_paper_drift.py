"""The temporal ladder equals the owner's paper matrix, read from a verbatim extract of its results CSV."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from omnidriver.verifier.problem import load_problem

FIXTURE = Path(__file__).parent / "fixtures" / "paper" / "temporal_full_matrix_cases.csv"
SCHEMES = {("godunov", "Euler"), ("godunov", "backward"), ("sbdf2", "Euler"), ("sbdf2", "backward")}


def _paper() -> tuple[str, list[dict[str, str]]]:
    header, *lines = FIXTURE.read_text().splitlines()
    assert header.startswith("# ") and "sha256" in header
    return header, list(csv.DictReader(lines))


def _dts(rows: list[dict[str, str]], dimension: str, cells: int, scheme: tuple[str, str]) -> set[float]:
    return {float(row["dt"]) for row in rows
            if (row["dimension"], int(row["cells"]), row["coupling"], row["ddt"]) == (dimension, cells, *scheme)}


def test_the_ladder_cites_the_digest_of_the_csv_the_fixture_extracts():
    header, _ = _paper()
    digest = header.split("sha256 ")[1].split(",")[0]
    assert digest in " ".join(load_problem("fda_monodomain")["provenance"]["refinement"])


@pytest.mark.parametrize("dimension", [1, 2])
def test_every_scheme_pair_runs_the_ladders_dt_at_its_mesh_in_the_paper(dimension):
    ladder = load_problem("fda_monodomain")["refinement"]["temporal"]
    _, rows = _paper()
    for scheme in SCHEMES:
        paper = _dts(rows, f"{dimension}D", ladder["cells_per_axis"][str(dimension)], scheme)
        # The paper's 2D sbdf2 x backward also runs two finer levels; the ladder is the five every pair shares.
        assert set(ladder["dt"]) <= paper, (dimension, scheme)
        assert paper == set(ladder["dt"]) or (dimension, scheme) == (2, ("sbdf2", "backward"))


def test_the_ladders_steps_reach_the_end_time_at_every_dt():
    problem = load_problem("fda_monodomain")
    ladder = problem["refinement"]["temporal"]
    assert all(steps * dt == pytest.approx(problem["time"]["end"]) for dt, steps in zip(ladder["dt"], ladder["steps"]))


def test_the_excluded_3d_rows_are_the_papers_sbdf2_backward_only_at_their_mesh():
    excluded = load_problem("fda_monodomain")["refinement"]["temporal"]["excluded"]["3"]
    _, rows = _paper()
    three = [row for row in rows if row["dimension"] == "3D"]
    assert {(row["coupling"], row["ddt"]) for row in three} == {("sbdf2", "backward")}
    assert {int(row["cells"]) for row in three} == {excluded["cells_per_axis"]}
    assert {float(row["dt"]) for row in three} == set(excluded["dt"])
