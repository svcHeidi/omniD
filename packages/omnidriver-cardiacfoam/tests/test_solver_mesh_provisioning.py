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
#     Corrected 2026-09-24 (Phase 3 Task 10): two tests deleted here,
#     `test_provision_mesh_spatial_solver_honours_dx` and
#     `test_provision_mesh_dry_run_writes_nothing_for_a_spatial_solver`,
#     exercised only `provision_mesh`'s own `BLOCK_MESH_SOLVERS` branch,
#     which had zero production callers and was deleted alongside them (see
#     `mesh_provisioning.py`'s own dated correction). Per this phase's rule
#     of mapping every deleted test's behaviour to a surviving test or
#     stating it is gone:
#       - "dx controls the generated blockMeshDict's cell count for a
#         spatial solver" survives, at the pure-function level, in
#         `omnidriver-openfoam/tests/core/test_mesh_provisioning.py::
#         test_dx_controls_cell_count_finer_mesh_for_smaller_dx`, and, at
#         the write-path level (the live channel this behaviour actually
#         reaches production through), in `test_dict_builder.py::
#         test_dx_kwarg_controls_generated_block_mesh_resolution`.
#       - "dry_run does not write blockMeshDict for a spatial solver" does
#         NOT survive anywhere, and is correctly gone, not merely
#         unmapped: it was a property of `provision_mesh`'s own dead
#         branch specifically. The live path,
#         `dict_builder.build_case`/`resolve_synthesis_mutation`, has never
#         had this property -- its `blockMeshDict` content target is
#         unconditional on `dry_run` (only the meshless polyMesh fixture is
#         `dry_run`-gated there, via `include_meshless_polymesh`), and
#         `test_dx_kwarg_controls_generated_block_mesh_resolution` itself
#         calls `build_and_launch(..., dry_run=True, ...)` and asserts
#         `system/blockMeshDict` WAS written -- the opposite of what the
#         deleted test pinned. No test should assert the deleted
#         behaviour, because it was never true of the code that is
#         actually reachable.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

import pytest

from omnidriver.cardiacfoam.mesh_provisioning import provision_mesh


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
