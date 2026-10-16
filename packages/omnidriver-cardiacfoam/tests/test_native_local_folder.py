"""A tutorial's ``Allrun`` writes its options into ``local/``, which the case's dictionaries ``#includeIfPresent``: staging
drops a ``local/`` a native run left, and a patch keeps the include lines. The dictionaries are verbatim from
cardiacFOAM's ``manufacturedSolutions/monodomainPseudoECG/system`` (PR #59)."""

from __future__ import annotations

import shutil
from pathlib import Path

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.runtime.sweep_runner import _stage_entry_case
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.openfoam.mutators import update_foam_entry

_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:native_local_folder")
_FIXTURES = Path(__file__).parent / "fixtures" / "local_includes"


def _case(root: Path) -> Path:
    (root / "system").mkdir(parents=True)
    for name in ("blockMeshDict.3D", "controlDict"):
        shutil.copy(_FIXTURES / name, root / "system" / name)
    return root


def test_staging_drops_the_local_folder_a_native_run_left(tmp_path):
    source = _case(tmp_path / "source")
    (source / "local").mkdir()
    (source / "local" / "mesh").write_text("N 80;\n")
    staged = tmp_path / "scratch" / "case"

    _stage_entry_case(source, staged, driver_context=_CTX)

    assert (staged / "system" / "blockMeshDict.3D").is_file()
    assert not (staged / "local").exists()
    assert (source / "local" / "mesh").is_file()


def test_a_patch_keeps_the_include_lines(tmp_path):
    case = _case(tmp_path / "case")
    block_mesh, control = case / "system" / "blockMeshDict.3D", case / "system" / "controlDict"

    update_foam_entry(block_mesh, "N", "40")
    update_foam_entry(control, "deltaT", "0.000555")

    mesh_lines = block_mesh.read_text().splitlines()
    assert mesh_lines[mesh_lines.index("N    40;") + 1] == '#includeIfPresent "<case>/local/mesh"'
    assert "hex (0 1 2 3 4 5 6 7) ($N $N $N) simpleGrading (1 1 1)" in mesh_lines
    assert '#includeIfPresent "<case>/local/time"' in control.read_text().splitlines()
    assert "deltaT    0.000555;" in control.read_text().splitlines()
