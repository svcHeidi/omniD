"""cardiacFoam's `build_and_launch` splits into `build_case` + orchestration.

Phase 2 Task 9 (docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md):
the second vertical slice, one synthesis path. `build_and_launch` used to
write five files with bare `write_text` -- `constant/electroProperties`,
`constant/physicsProperties`, `system/fvSchemes`, `system/fvSolution`,
`system/controlDict` -- then provision a mesh and mutate `controlDict` a
SECOND time via `update_control_dict`. Every one of those five is a
framework-authored input; `build_case(...) -> CaseWritePlan` now resolves and
renders all of them (plus a conditional `system/blockMeshDict`) as one
reviewable plan, and `build_and_launch` commits it through
`commit_case_write` before provisioning the mesh and (if not `dry_run`)
launching.

`test_build_and_launch_produces_this_exact_case` is the characterization:
captured against the pre-migration `build_and_launch`, commit `dc7fbef`
(2026-09-23, HEAD at the start of this task), by running the OLD code
(`git stash` of this migration's changes) against the exact scenario below
and hashing every file `build_and_launch` left behind. It must pass
unchanged. `.omnidriver/` is excluded from the comparison: it is new
bookkeeping this migration adds (the transaction journal and the completed-
transaction record), not a case input, and its own transaction id is
random per run.
"""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.dict_builder import build_and_launch, build_case
from omnidriver.core.case_write import CaseMutationRequest

#: Captured 2026-09-23 against commit dc7fbef (pre-Task-9 `build_and_launch`,
#: run via `git stash` of this task's changes), for:
#:   electro_selectors={"myocardiumSolver": "monodomainSolver",
#:                       "ionicModel": "TNNP", "tissue": "epicardialCells"}
#:   physics_selectors={"type": "electroModel"}
#:   delta_t=2e-4, end_time=0.5, dx=0.0004, dry_run=True
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
            continue  # new bookkeeping this migration adds, not a case input
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
    """Characterization. Content digests and modes, not existence -- a
    migration that produced six empty files would pass an existence check."""
    result = _scenario(tmp_path)
    digests, modes = _case_digests_and_modes(tmp_path)
    assert digests == EXPECTED_DIGESTS
    assert modes == EXPECTED_MODES
    assert result["status"] == "dry_run_complete"
    assert result["needs_block_mesh"] is True


def test_build_and_launch_declares_the_same_workflow_effects(tmp_path):
    """Declared workflow effects, not just bytes -- a synthesis producing
    identical bytes but declaring different steps is not parity."""
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        delta_t=2e-4, end_time=0.5, dx=0.0004, driver_context=own_driver_context(),
    )
    authored = {f.path for f in plan.files}
    assert authored == set(EXPECTED_DIGESTS)


# --------------------------------------------------------------------------
# The new path
# --------------------------------------------------------------------------


def test_synthesis_refuses_without_a_source_artifact():
    """`synthesize` with no declared source is not a supported mode. The
    refuted draft treated synthesis and patching as one operation at
    different arities, which is how asset-free synthesis looked supported."""
    with pytest.raises(ValueError, match="source artifact"):
        CaseMutationRequest(
            mode="synthesize", case_root=Path("/tmp/case"), adapter_id="org.cardiacfoam",
            workflow="entry", source_artifacts=(), parameters=(),
            requested_by="test",
        )


def test_controldict_is_rendered_once_with_both_effects(tmp_path):
    """Today `controlDict` is written from a template and then mutated a
    second time. One rendering carries both -- the plan shows the final
    content, and there is exactly one `RenderedFile` for the path."""
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
    """Phase 3 Task 10 (bypass 5): `Allrun` is not a second write bolted on
    after `build_and_launch` returns -- `include_allrun=True` makes it one
    more `RenderedFile` in the exact same `CaseWritePlan` `build_case`
    resolves and renders, alongside the dictionaries, so `build_and_launch`'s
    one `commit_case_write` call commits both in the same transaction. A
    failure between two separate writes -- the pre-migration shape, a bare
    `write_text` after `build_and_launch` had already returned -- could leave
    a case with inputs but no runnable `Allrun`; a single `CaseWritePlan`
    cannot leave that half-written state, since `commit_case_write` commits
    every one of its `files` together."""
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
    """Default `include_allrun=False` -- every existing caller of `build_case`
    (this test module's own characterizations, direct callers other than
    `sweep.py::materialize_case`) is unaffected."""
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", "tissue": "epicardialCells"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        driver_context=own_driver_context(),
    )
    assert "Allrun" not in {f.path for f in plan.files}


def test_an_existing_case_is_not_silently_overwritten(tmp_path):
    """`overwrite=False` raises FileExistsError, preserved exactly (see
    `build_case`'s docstring): the pre-existing regression test
    `test_dict_builder.py::test_existing_case_dir_is_not_overwritten_without_consent`
    asserts that specific type, so this migration keeps it rather than
    routing this particular guard through the channel as a precondition."""
    (tmp_path / "constant").mkdir(parents=True)
    (tmp_path / "constant" / "electroProperties").write_text("# pre-existing\n")
    with pytest.raises(FileExistsError, match="electroProperties"):
        build_and_launch(
            electro_selectors={"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
            physics_selectors={"type": "electroModel"}, case_dir=tmp_path, dry_run=True,
        )


def test_a_failed_synthesis_leaves_no_partial_case(tmp_path, monkeypatch):
    """The old path wrote electroProperties, then physicsProperties, then
    three system files in sequence. A failure partway through left a case
    that looked built. Through the channel, an injected failure mid-commit
    rolls back every file this transaction touched."""
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
    # Unchanged from before this migration.
    # Corrected 2026-09-24 (Phase 3 Task 10, bypass 5): `include_allrun`
    # added, keyword-only, defaulting False -- sweep.py::materialize_case
    # is the one caller that sets it, folding its Allrun write into this
    # same commit. Every parameter this test originally pinned is still
    # here, in the same order; only the new one is added, before
    # `driver_context` (which stays last, matching every other call site's
    # `build_case`/`build_and_launch` keyword-argument ordering).
    assert list(signature.parameters) == [
        "electro_selectors", "physics_selectors", "case_dir", "electro_overrides",
        "physics_overrides", "overwrite", "dry_run", "pre_solve_commands",
        "openfoam_bashrc", "delta_t", "end_time", "dx", "include_allrun",
        "driver_context",
    ]


def test_a_controldict_patch_targets_only_the_key_explicitly_given(tmp_path):
    """`update_control_dict`'s pre-migration per-key `is not None` guard:
    passing only `delta_t` must not also force `endTime` to the default."""
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
    """Mirrors the pre-migration behaviour this characterizes: a controlDict
    that already exists (overwrite=False) is left alone except for the keys
    explicitly given."""
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


# --------------------------------------------------------------------------
# Meshless-solver polyMesh migration (Task 12, batch P2-H)
# --------------------------------------------------------------------------


def test_meshless_solver_polymesh_is_written_through_the_channel(tmp_path):
    """Characterization: the bundled single-cell polyMesh, now folded into
    `build_case`'s own plan instead of a direct `provision_mesh` call, must
    produce byte-identical content to
    `mesh_provisioning.meshless_polymesh_fixture()` -- and must actually go
    through `commit_case_write` (a completed-transaction record under
    `.omnidriver/`), not merely happen to look the same.

    Calls `build_case`/`commit_case_write` directly rather than
    `build_and_launch(dry_run=False, ...)`: no existing test in this package
    exercises `build_and_launch`'s real (non-dry-run) path at all, because it
    also launches the solver, which this environment cannot do. This is the
    same split `build_and_launch` itself uses internally."""
    from omnidriver.cardiacfoam.mesh_provisioning import meshless_polymesh_fixture
    from omnidriver.cardiacfoam.own_context import own_driver_context
    from omnidriver.core.case_transaction import commit_case_write

    context = own_driver_context()
    plan = build_case(
        {
            "myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov",
            "tissue": "myocyte",
        },
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        dry_run=False, driver_context=context,
    )
    poly_mesh_targets = {f.path for f in plan.files if f.path.startswith("constant/polyMesh/")}
    assert poly_mesh_targets == {f"constant/polyMesh/{name}" for name in meshless_polymesh_fixture()}

    record = commit_case_write(plan, driver_context=context, execution_env=None)
    assert record.status == "committed"

    poly_mesh = tmp_path / "constant" / "polyMesh"
    fixture = meshless_polymesh_fixture()
    for name, content in fixture.items():
        assert (poly_mesh / name).read_text() == content

    completed_dir = tmp_path / ".omnidriver" / "case-transactions"
    assert completed_dir.is_dir() and list(completed_dir.glob("*.json"))


def test_meshless_solver_polymesh_still_writes_nothing_under_dry_run_true_is_unchanged(tmp_path):
    """Not a new test of the dry_run behaviour itself (see
    test_dict_builder.py::TestBuildAndLaunchMeshProvisioning) -- a guard that
    this migration did not quietly turn dry_run into a real write, called
    directly through build_case (the function this migration actually
    changed) rather than only through build_and_launch."""
    from omnidriver.cardiacfoam.own_context import own_driver_context

    plan = build_case(
        {"myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov", "tissue": "myocyte"},
        physics_selectors={"type": "electroModel"}, case_dir=tmp_path,
        dry_run=True, driver_context=own_driver_context(),
    )
    assert not any(f.path.startswith("constant/polyMesh/") for f in plan.files)


def test_meshless_solver_polymesh_refuses_a_partial_mesh_before_planning(tmp_path):
    (tmp_path / "constant" / "polyMesh").mkdir(parents=True)
    (tmp_path / "constant" / "polyMesh" / "points").write_text("hand-authored\n")
    with pytest.raises(ValueError, match="partially authored"):
        build_and_launch(
            electro_selectors={
                "myocardiumSolver": "singleCellSolver", "ionicModel": "AlievPanfilov",
                "tissue": "myocyte",
            },
            physics_selectors={"type": "electroModel"}, case_dir=tmp_path, dry_run=True,
        )
    # Refused before any write -- not even electroProperties/physicsProperties
    # from the same plan landed.
    assert not (tmp_path / "constant" / "electroProperties").exists()
