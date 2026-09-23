#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_solver_mesh_provisioning
#
# Description
#     Tests the myocardiumSolver-keyed mesh provisioning strategy for
#     from-scratch case_folder cases.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

import re

import pytest

from omnidriver.cardiacfoam.mesh_provisioning import provision_mesh
from omnidriver.openfoam.mesh_provisioning import default_block_mesh_dict_text


def _cell_counts(text: str) -> tuple[int, int, int]:
    match = re.search(r"hex \([^)]*\)\s*\((\d+)\s+(\d+)\s+(\d+)\)", text)
    assert match is not None, text
    return tuple(int(g) for g in match.groups())


def test_provision_mesh_spatial_solver_honours_dx(tmp_path):
    case_dir = tmp_path / "case"
    provision_mesh(case_dir=case_dir, myocardium_solver="monodomainSolver", dx_m=0.0004)
    text = (case_dir / "system" / "blockMeshDict").read_text()
    default_cells = _cell_counts(default_block_mesh_dict_text())
    assert _cell_counts(text)[0] > default_cells[0]


def test_provision_mesh_rejects_dx_for_meshless_solver(tmp_path):
    # singleCellSolver has no spatial geometry at all -- dx would silently
    # have zero effect, same silent-no-op failure mode this whole fix pass
    # exists to close off.
    case_dir = tmp_path / "case"
    with pytest.raises(ValueError, match="dx"):
        provision_mesh(case_dir=case_dir, myocardium_solver="singleCellSolver", dx_m=0.0004)


def test_provision_mesh_copies_the_bundled_single_cell_polymesh(tmp_path):
    # The 1-cell polyMesh fixture ships with the plugin, so this also pins
    # that the packaged fixture path still resolves.
    case_dir = tmp_path / "case"
    needs_block_mesh = provision_mesh(
        case_dir=case_dir, myocardium_solver="singleCellSolver",
    )
    assert needs_block_mesh is False
    poly_mesh = case_dir / "constant" / "polyMesh"
    for name in ("points", "faces", "owner", "neighbour", "boundary"):
        assert (poly_mesh / name).is_file(), name


def test_provision_mesh_leaves_an_unknown_solver_to_the_caller(tmp_path):
    case_dir = tmp_path / "case"
    assert provision_mesh(case_dir=case_dir, myocardium_solver="futureSolver") is False
    assert not (case_dir / "system" / "blockMeshDict").exists()
    assert not (case_dir / "constant" / "polyMesh").exists()


def test_provision_mesh_dry_run_writes_nothing_for_a_meshless_solver(tmp_path):
    """R3 finding 8 (2026-09-23): `dry_run=True` must not write the bundled
    polyMesh fixture -- `build_and_launch`'s dry_run promise ("writes the
    dicts and returns without further effect") was broken by an
    unconditional `provision_mesh` call."""
    case_dir = tmp_path / "case"
    needs_block_mesh = provision_mesh(
        case_dir=case_dir, myocardium_solver="singleCellSolver", dry_run=True,
    )
    assert needs_block_mesh is False
    assert not (case_dir / "constant" / "polyMesh").exists()


def test_provision_mesh_dry_run_writes_nothing_for_a_spatial_solver(tmp_path):
    case_dir = tmp_path / "case"
    needs_block_mesh = provision_mesh(
        case_dir=case_dir, myocardium_solver="monodomainSolver", dry_run=True,
    )
    assert needs_block_mesh is True
    assert not (case_dir / "system" / "blockMeshDict").exists()


def test_provision_mesh_dry_run_still_rejects_dx_for_meshless_solver(tmp_path):
    """Validation is not part of the filesystem effect `dry_run` skips."""
    case_dir = tmp_path / "case"
    with pytest.raises(ValueError, match="dx"):
        provision_mesh(
            case_dir=case_dir, myocardium_solver="singleCellSolver",
            dx_m=0.0004, dry_run=True,
        )


def test_provision_mesh_refuses_a_partially_authored_mesh(tmp_path):
    """R3 finding 8, fixed 2026-09-23 (Task 12, batch P2-H): the old
    `all(...)` skip guard silently overwrote every one of the five polyMesh
    files whenever even one was missing -- a hand-authored mesh missing, say,
    only its `boundary` file got the other four silently replaced too. A
    partial set must now refuse instead of guessing which provenance wins."""
    case_dir = tmp_path / "case"
    poly_mesh = case_dir / "constant" / "polyMesh"
    poly_mesh.mkdir(parents=True)
    (poly_mesh / "points").write_text("hand-authored, not the fixture\n")

    with pytest.raises(ValueError, match="partially authored"):
        provision_mesh(case_dir=case_dir, myocardium_solver="singleCellSolver")

    # Refusing, not completing it behind the caller's back either direction.
    assert (poly_mesh / "points").read_text() == "hand-authored, not the fixture\n"
    assert not (poly_mesh / "faces").exists()


def test_meshless_polymesh_fixture_matches_the_bundled_files(tmp_path):
    from omnidriver.cardiacfoam.mesh_provisioning import meshless_polymesh_fixture

    provision_mesh(case_dir=tmp_path, myocardium_solver="singleCellSolver")
    poly_mesh = tmp_path / "constant" / "polyMesh"
    fixture = meshless_polymesh_fixture()
    assert set(fixture) == {"points", "faces", "owner", "neighbour", "boundary"}
    for name, content in fixture.items():
        assert (poly_mesh / name).read_text() == content
