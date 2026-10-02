"""cardiacFoam's `build_and_launch` splits into `build_case` + orchestration.
`build_case` renders every framework-authored input as one `CaseWritePlan`, committed through `commit_case_write`.
`.omnidriver/` is excluded from digests: it is transaction bookkeeping with a random id, not a case input.
"""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.dict_builder import build_and_launch, build_case
from omnidriver.core.case_write import CaseMutationRequest

#: Digests of the case ``_scenario`` builds.
EXPECTED_DIGESTS = {
    "constant/electroProperties": "d03af090622600d49d9c9685b7c209e6a485e74ae7ef5e148ed69b2a0db3d9b2",
    "constant/physicsProperties": "7be93ad559071b564d00f9595041df7ba0910caf2cb825b23a4d1ec111182e32",
    "system/blockMeshDict": "81783926ddf0c830840994a77b66fdf73c960bad880e2e7e1612484df5362f88",
    "system/controlDict": "624478df4ba7261af7577f9fd6096137e9e8242b27f12715a9420f8bd097ee97",
    "system/fvSchemes": "07d2738605e03c6af45e65a03f81f44050a5f00da893913fdc4432b9e1f65253",
    "system/fvSolution": "627007aa123b3b5cb5ca96ff5e4f732639a0b28d00f1597cb4544ed147643d10",
}
EXPECTED_MODES = {path: "0o644" for path in EXPECTED_DIGESTS}


def _case_digests_and_modes(case_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    digests: dict[str, str] = {}
    modes: dict[str, str] = {}
    for path in sorted(case_dir.rglob("*")):
        if not path.is_file():
            continue
        relpath = str(path.relative_to(case_dir))
        if relpath.startswith(".omnidriver"):
            continue  # transaction bookkeeping, not a case input
        digests[relpath] = hashlib.sha256(path.read_bytes()).hexdigest()
        modes[relpath] = oct(path.stat().st_mode & 0o777)
    return digests, modes


def _scenario(case_dir: Path) -> dict:
    return build_and_launch(
        electro_selectors={
            "myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP",
            "tissue": "epicardialCells",
        },
        physics_selectors={"type": "electroModel"},
        case_dir=case_dir, dry_run=True, delta_t=2e-4, end_time=0.5, dx=0.0004,
    )


def test_build_and_launch_produces_this_exact_case(tmp_path):
    """Content digests and modes, not existence: six empty files would pass an existence check."""
    result = _scenario(tmp_path)
    digests, modes = _case_digests_and_modes(tmp_path)
    assert digests == EXPECTED_DIGESTS
    assert modes == EXPECTED_MODES
    assert result["status"] == "dry_run_complete"
    assert result["needs_block_mesh"] is True


def test_build_and_launch_declares_the_same_workflow_effects(tmp_path):
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        delta_t=2e-4, end_time=0.5, dx=0.0004, driver_context=own_driver_context(),
    )
    authored = {f.path for f in plan.files}
    assert authored == set(EXPECTED_DIGESTS)


def test_synthesis_refuses_without_a_source_artifact():
    with pytest.raises(ValueError, match="source artifact"):
        CaseMutationRequest(
            mode="synthesize", case_root=Path("/tmp/case"), adapter_id="org.cardiacfoam",
            workflow="entry", source_artifacts=(), parameters=(),
            requested_by="test",
        )


def test_controldict_is_rendered_once_with_both_effects(tmp_path):
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        delta_t=2e-4, end_time=0.5, driver_context=own_driver_context(),
    )
    control_dict_files = [f for f in plan.files if f.path == "system/controlDict"]
    assert len(control_dict_files) == 1
    content = control_dict_files[0].content.decode()
    assert "0.0002" in content
    assert "0.5" in content


def test_allrun_joins_the_same_plan_build_case_returns(tmp_path):
    """One plan is one transaction, so a case cannot end up with inputs but no runnable `Allrun`."""
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        include_allrun=True, driver_context=own_driver_context(),
    )
    paths = {f.path for f in plan.files}
    assert "Allrun" in paths
    assert paths == {
        "constant/electroProperties", "constant/physicsProperties",
        "system/fvSchemes", "system/fvSolution", "system/controlDict",
        "system/blockMeshDict", "Allrun",
    }
    allrun_file = next(f for f in plan.files if f.path == "Allrun")
    assert allrun_file.content == b"#!/bin/sh\nblockMesh\ncardiacFoam\n"
    assert allrun_file.mode == 0o755
    assert allrun_file.exists_before is False


def test_build_case_without_include_allrun_does_not_author_it(tmp_path):
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        driver_context=own_driver_context(),
    )
    assert "Allrun" not in {f.path for f in plan.files}


def test_an_existing_case_is_not_silently_overwritten(tmp_path):
    """`overwrite=False` raises FileExistsError, the type `test_existing_case_dir_is_not_overwritten_without_consent` asserts."""
    (tmp_path / "constant").mkdir(parents=True)
    (tmp_path / "constant" / "electroProperties").write_text("# pre-existing\n")
    with pytest.raises(FileExistsError, match="electroProperties"):
        build_and_launch(
            electro_selectors={"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
            physics_selectors={"type": "electroModel"}, case_dir=tmp_path, dry_run=True,
        )


def test_a_failed_synthesis_leaves_no_partial_case(tmp_path, monkeypatch):
    from omnidriver.core import case_transaction

    real_write_one = case_transaction._write_one
    calls = {"n": 0}

    def _die_on_third_write(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("simulated failure")
        return real_write_one(*args, **kwargs)

    monkeypatch.setattr(case_transaction, "_write_one", _die_on_third_write)
    with pytest.raises(case_transaction.CaseTransactionError):
        build_and_launch(
            electro_selectors={"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
            physics_selectors={"type": "electroModel"}, case_dir=tmp_path, dry_run=True,
        )
    assert not (tmp_path / "constant" / "electroProperties").exists()
    assert not (tmp_path / "constant" / "physicsProperties").exists()


def test_build_case_keeps_the_signature_build_and_launch_needs(tmp_path):
    signature = inspect.signature(build_and_launch)
    assert list(signature.parameters) == [
        "electro_selectors", "physics_selectors", "case_dir", "electro_overrides",
        "physics_overrides", "overwrite", "dry_run", "delta_t", "end_time",
        "dx", "include_allrun", "driver_context",
    ]


def test_a_controldict_patch_targets_only_the_key_explicitly_given(tmp_path):
    """Passing only `delta_t` must not also force `endTime` to the default."""
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        delta_t=3e-4, driver_context=own_driver_context(),
    )
    content = next(f for f in plan.files if f.path == "system/controlDict").content.decode()
    assert "0.0003" in content
    assert "endTime         1.0;" in content  # untouched template alignment


def test_a_pre_existing_control_dict_is_only_patched_not_replaced(tmp_path):
    (tmp_path / "system").mkdir(parents=True)
    (tmp_path / "system" / "controlDict").write_text("deltaT    0.05;\nendTime   1.0;\n")
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        delta_t=2e-4, end_time=0.5, driver_context=own_driver_context(),
    )
    control_dict_files = [f for f in plan.files if f.path == "system/controlDict"]
    assert len(control_dict_files) == 1
    assert control_dict_files[0].content == b"deltaT    0.0002;\nendTime    0.5;\n"


def test_blockmeshdict_never_clobbers_a_hand_authored_one(tmp_path):
    (tmp_path / "system").mkdir(parents=True)
    (tmp_path / "system" / "blockMeshDict").write_text("// pre-existing custom mesh\n")
    (tmp_path / "constant").mkdir(parents=True)
    (tmp_path / "constant" / "electroProperties").write_text("# pre-existing\n")
    build_and_launch(
        electro_selectors={"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path, dry_run=True,
        overwrite=True,
    )
    assert (tmp_path / "system" / "blockMeshDict").read_text() == "// pre-existing custom mesh\n"


# Single-cell solver meshing


def test_single_cell_solver_block_mesh_dict_is_written_through_the_channel(tmp_path):
    """Calls `build_case`/`commit_case_write` directly: non-dry-run `build_and_launch` would also launch the solver."""
    from omnidriver.cardiacfoam.own_context import own_driver_context
    from omnidriver.core.case_transaction import commit_case_write
    from omnidriver.openfoam.mesh_provisioning import single_cell_block_mesh_dict_text

    context = own_driver_context()
    plan = build_case(
        {
            "myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov",
            "tissue": "myocyte",
        },
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        dry_run=False, driver_context=context,
    )
    block_mesh_targets = {f.path: f.content for f in plan.files if f.path == "system/blockMeshDict"}
    assert block_mesh_targets == {"system/blockMeshDict": single_cell_block_mesh_dict_text().encode()}
    assert not any(f.path.startswith("constant/polyMesh/") for f in plan.files)

    record = commit_case_write(plan, driver_context=context)
    assert record.status == "committed"
    assert (tmp_path / "system" / "blockMeshDict").read_text() == single_cell_block_mesh_dict_text()
    assert not (tmp_path / "constant" / "polyMesh").exists()

    completed_dir = tmp_path / ".omnidriver" / "case-transactions"
    assert completed_dir.is_dir() and list(completed_dir.glob("*.json"))


def test_single_cell_solver_block_mesh_dict_is_not_dry_run_gated(tmp_path):
    """`blockMeshDict` is a case input, not a launch effect."""
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        dry_run=True, driver_context=own_driver_context(),
    )
    assert any(f.path == "system/blockMeshDict" for f in plan.files)
