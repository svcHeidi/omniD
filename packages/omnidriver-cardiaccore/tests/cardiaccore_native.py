"""Supplied inputs for native cardiacCore tests, and the ``humanSlab``
conformance target.

A uniquely named module, not ``conftest`` (CLAUDE.md's conftest trap).
Nothing here is discovered: the native tree comes from
``OMNIDRIVER_CARDIACCORE_TREE`` (a clean native worktree/archive -- never
the owner's checkout, which has uncommitted work), the anatomy bundle from
``OMNIDRIVER_CARDIACCORE_ANATOMY``, and the OpenFOAM environment plus the
cardiacCore utilities from the shell the tests run in, already sourced and
on ``PATH``/``DYLD_LIBRARY_PATH`` (docs/solver-learning/cardiaccore.md).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from omnidriver.conformance import ConformanceTarget


def native_cardiaccore_tree() -> Path:
    """The supplied native cardiacCore worktree. FAILS, never skips, when
    unset: a ``native_cardiaccore`` test that cannot see the real tree
    proves nothing."""
    value = os.environ.get("OMNIDRIVER_CARDIACCORE_TREE")
    if not value:
        pytest.fail(
            "OMNIDRIVER_CARDIACCORE_TREE is not set. A test marked "
            "@pytest.mark.native_cardiaccore needs a clean native cardiacCore "
            "worktree (a git worktree or `git archive` of its own main), "
            "supplied explicitly via that environment variable -- never the "
            "owner's checkout, and never discovered. Run e.g.:\n"
            "  OMNIDRIVER_CARDIACCORE_TREE=/path/to/worktree "
            "OMNIDRIVER_CARDIACCORE_ANATOMY=/path/to/bundle "
            "pytest -m native_cardiaccore"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_CARDIACCORE_TREE={value!r} is not a directory")
    return root


def native_cardiaccore_anatomy() -> Path:
    """The supplied ``humanSlab`` anatomy bundle -- the mesh, ``fiber``,
    ``sheet`` and ``uvc_*`` fields that are not in the tracked case folder.
    FAILS, never skips, when unset."""
    value = os.environ.get("OMNIDRIVER_CARDIACCORE_ANATOMY")
    if not value:
        pytest.fail(
            "OMNIDRIVER_CARDIACCORE_ANATOMY is not set. A test marked "
            "@pytest.mark.native_cardiaccore needs the humanSlab anatomy "
            "bundle (constant/polyMesh, 0/fiber, 0/sheet, 0/uvc_*) supplied "
            "explicitly via that environment variable -- never discovered."
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_CARDIACCORE_ANATOMY={value!r} is not a directory")
    return root


def require_sourced_openfoam(*commands: str) -> None:
    """The calling shell has OpenFOAM sourced and ``commands`` (the
    cardiacCore utilities, built from ``OMNIDRIVER_CARDIACCORE_TREE``'s own
    committed source, never the owner's installed binaries) on its PATH.
    Checked up front so a missing environment fails naming the fix, rather
    than as C5-C11 verdicts about a plan that could not run."""
    if "WM_PROJECT_DIR" not in os.environ:
        pytest.fail(
            "WM_PROJECT_DIR is not set: run the native cardiacCore "
            "conformance tests from a shell that has sourced OpenFOAM, e.g. "
            "`bash -c 'source <OpenFOAM>/etc/bashrc && pytest -m "
            "native_cardiaccore ...'`"
        )
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        pytest.fail(
            f"not on PATH in the sourced OpenFOAM shell: {missing} -- build "
            "the cardiacCore utilities from OMNIDRIVER_CARDIACCORE_TREE's own "
            "committed main and put them first on PATH/DYLD_LIBRARY_PATH "
            "(docs/solver-learning/cardiaccore.md)"
        )


HUMAN_SLAB_UTILITIES = (
    "setCardiacConductivity", "setCardiacAnatomy", "setPurkinjeSlab", "setPurkinjeMorphometry",
)
TREE_UTILITIES = ("setCardiacConductivity", "setCardiacAnatomy", "generatePurkinjeTree")


def human_slab_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """``humanSlab``: the native ``cases/bivCase`` case folder plus the
    supplied anatomy bundle."""
    require_sourced_openfoam(*HUMAN_SLAB_UTILITIES)
    return ConformanceTarget(
        plugin="cardiaccore",
        record="humanSlab",
        cases_root=native_cardiaccore_tree(),
        scratch_root=tmp_path / "scratch",
        inputs={"anatomy": str(native_cardiaccore_anatomy())},
        base_study={},
        # Both keys already exist in the native dict (`thickness 0.1;`,
        # `multiplier 3.0;`): `setPurkinjeMorphometryDict` declares none at
        # all (relies on the compiled default), and the renderer can only
        # update an existing key, not insert one -- found running C7 for
        # real.
        patch=("system/setPurkinjeSlabDict:thickness", 0.2),
        untouched=("system/setCardiacAnatomyDict", ("zApicalMid",)),
        sweep_name="system/setPurkinjeSlabDict:multiplier",
        sweep_values=(2.0, 4.0),
        unknown_name="system/setPurkinjeSlabDict:thicknes",
        solver_command="setCardiacConductivity",
        environment={},
        # Real utilities over a real anatomy bundle; generous but bounded.
        timeout_s=900.0,
    )


def _idealized_target(
    record: str, tmp_path: Path, *, utilities: tuple[str, ...], timeout_s: float,
) -> ConformanceTarget:
    """Every idealized-heart variant shares one native mesh (no supplied
    input at all) and one physics phase (setCardiacConductivity +
    setCardiacAnatomy), so C4/C7's patch/sweep keys are the same real,
    pre-existing `setCardiacAnatomyDict` entries for all three."""
    require_sourced_openfoam(*utilities)
    return ConformanceTarget(
        plugin="cardiaccore",
        record=record,
        cases_root=native_cardiaccore_tree(),
        scratch_root=tmp_path / "scratch",
        base_study={},
        patch=("system/setCardiacAnatomyDict:zApicalMid", 0.30),
        untouched=("system/setCardiacAnatomyDict", ("zMidBasal",)),
        sweep_name="system/setCardiacAnatomyDict:zApexCap",
        sweep_values=(0.06, 0.10),
        unknown_name="system/setCardiacAnatomyDict:zApicalMi",
        solver_command="setCardiacConductivity",
        environment={},
        timeout_s=timeout_s,
    )


def idealized_heart_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """``idealizedHeart``: conductivity + anatomy + slab + morphometry, on
    the idealized mesh -- no supplied input needed."""
    return _idealized_target("idealizedHeart", tmp_path, utilities=HUMAN_SLAB_UTILITIES, timeout_s=300.0)


def idealized_heart_endocardial_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """``idealizedHeartEndocardial``: conductivity + anatomy +
    generatePurkinjeTree (LV/RV allLeaves+endocardial)."""
    return _idealized_target("idealizedHeartEndocardial", tmp_path, utilities=TREE_UTILITIES, timeout_s=300.0)


def idealized_heart_pig_transmural_conformance_target(tmp_path: Path) -> ConformanceTarget:
    """``idealizedHeartPigTransmural``: conductivity + anatomy + morphometry
    + generatePurkinjeTree (LV weightedField+transmural, RV
    allLeaves+transmural)."""
    return _idealized_target(
        "idealizedHeartPigTransmural", tmp_path,
        utilities=("setCardiacConductivity", "setCardiacAnatomy", "setPurkinjeMorphometry", "generatePurkinjeTree"),
        timeout_s=300.0,
    )
