"""``scripts/check-case-writes.py``: the static "records and axes write nothing"
gate. Here, not in core, since core's tests stay free of OpenFOAM vocabulary.
Repo-only: the lookup never raises at import time, so the test skips cleanly.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _find_repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "check-case-writes.py").is_file():
            return parent
    return None


_REPO_ROOT = _find_repo_root()

pytestmark = pytest.mark.skipif(
    _REPO_ROOT is None,
    reason=(
        "Requires the omnidriver monorepo checkout "
        "(scripts/check-case-writes.py not found from this test file)."
    ),
)


def _load_gate_module() -> ModuleType:
    path = _REPO_ROOT / "scripts" / "check-case-writes.py"
    spec = importlib.util.spec_from_file_location("check_case_writes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _violations_for(tmp_path: Path, source: str) -> list[str]:
    gate = _load_gate_module()
    module_path = tmp_path / "sample.py"
    module_path.write_text(source)
    return [msg for _key, msg in gate._check_file(module_path, tmp_path)]


def test_the_real_axes_and_records_trees_pass_the_gate():
    gate = _load_gate_module()
    assert gate.main() == 0


def test_scanned_roots_are_exactly_the_axes_records_and_planner_paths():
    gate = _load_gate_module()
    relpaths = {
        str(root.relative_to(_REPO_ROOT)) for root in gate.SCANNED_ROOTS
    }
    assert relpaths == {
        "packages/omnidriver-openfoam/src/omnidriver/openfoam/axes",
        "packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/records",
        "packages/omnidriver-openfoam/src/omnidriver/openfoam/case_planning.py",
        "packages/omnidriver-opencarp/src/omnidriver/opencarp/records",
        "packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/records",
    }


@pytest.mark.parametrize("source", [
    "from ..mutators import _format_value\n",
    "from .. import mutators\n",
    "from ..utils import set_delta_t as s\n",
])
def test_refuses_a_writer_module_reached_by_a_relative_import(tmp_path, source):
    """A relative import is resolved before matching, so it names the same module an absolute one does."""
    gate = _load_gate_module()
    axes = tmp_path / "src" / "omnidriver" / "openfoam" / "axes"
    axes.mkdir(parents=True)
    module_path = axes / "sample.py"
    module_path.write_text(source)
    messages = [msg for _key, msg in gate._check_file(module_path, axes)]
    assert any("a writer module" in msg for msg in messages), messages


def test_known_violations_is_empty():
    gate = _load_gate_module()
    assert gate.KNOWN_VIOLATIONS == frozenset()


def test_refuses_importing_update_foam_entry_from_mutators(tmp_path):
    violations = _violations_for(
        tmp_path,
        "from omnidriver.openfoam.mutators import update_foam_entry\n",
    )
    assert violations


def test_refuses_importing_anything_from_foam_backend(tmp_path):
    violations = _violations_for(
        tmp_path,
        "from omnidriver.openfoam.foam_backend import some_helper\n",
    )
    assert violations


def test_refuses_importing_apply_electro_property_overrides(tmp_path):
    violations = _violations_for(
        tmp_path,
        "from omnidriver.cardiacfoam.dict_builder import "
        "apply_electro_property_overrides\n",
    )
    assert violations


def test_refuses_importing_apply_physics_property_overrides(tmp_path):
    violations = _violations_for(
        tmp_path,
        "from omnidriver.cardiacfoam.dict_builder import "
        "apply_physics_property_overrides\n",
    )
    assert violations


def test_refuses_calling_apply_electro_property_overrides(tmp_path):
    violations = _violations_for(
        tmp_path,
        "def f(overrides):\n"
        "    apply_electro_property_overrides(overrides)\n",
    )
    assert violations


def test_refuses_importing_shutil(tmp_path):
    violations = _violations_for(tmp_path, "import shutil\n")
    assert violations


def test_refuses_shutil_copytree_call():
    """Importing `shutil` at all is forbidden, so the import alone refuses `copytree`."""
    gate = _load_gate_module()
    assert "shutil" in gate.FORBIDDEN_IMPORT_MODULES


def test_refuses_write_text(tmp_path):
    violations = _violations_for(
        tmp_path,
        "def f(path):\n"
        "    path.write_text('x')\n",
    )
    assert violations


def test_refuses_write_bytes(tmp_path):
    violations = _violations_for(
        tmp_path,
        "def f(path):\n"
        "    path.write_bytes(b'x')\n",
    )
    assert violations


def test_refuses_open_with_write_mode(tmp_path):
    violations = _violations_for(
        tmp_path,
        "def f():\n"
        "    open('f', 'w')\n",
    )
    assert violations


def test_refuses_open_with_append_mode_as_keyword(tmp_path):
    violations = _violations_for(
        tmp_path,
        "def f():\n"
        "    open('f', mode='a')\n",
    )
    assert violations


def test_allows_open_with_read_mode(tmp_path):
    violations = _violations_for(
        tmp_path,
        "def f():\n"
        "    open('f', 'r')\n"
        "    open('f')\n",
    )
    assert violations == []


def test_refuses_os_replace(tmp_path):
    violations = _violations_for(
        tmp_path,
        "import os\n"
        "def f(a, b):\n"
        "    os.replace(a, b)\n",
    )
    assert any("os.replace" in v for v in violations)


def test_refuses_os_rename(tmp_path):
    violations = _violations_for(
        tmp_path,
        "import os\n"
        "def f(a, b):\n"
        "    os.rename(a, b)\n",
    )
    assert any("os.rename" in v for v in violations)


def test_refuses_json_dump(tmp_path):
    violations = _violations_for(
        tmp_path,
        "import json\n"
        "def f(data, fh):\n"
        "    json.dump(data, fh)\n",
    )
    assert any("json.dump" in v for v in violations)


def test_refuses_foam_file_item_assignment(tmp_path):
    violations = _violations_for(
        tmp_path,
        "def f(path):\n"
        "    foam = FoamFile(path)\n"
        "    foam['key'] = 1\n",
    )
    assert any("FoamFile item assignment" in v for v in violations)


def test_refuses_foam_file_item_deletion(tmp_path):
    violations = _violations_for(
        tmp_path,
        "def f(path):\n"
        "    foam = FoamFile(path)\n"
        "    del foam['key']\n",
    )
    assert violations


def test_allows_reading_a_foam_file_item(tmp_path):
    """A read (`value = foam["key"]`, no assignment TARGET) is not a write."""
    violations = _violations_for(
        tmp_path,
        "def f(path):\n"
        "    foam = FoamFile(path)\n"
        "    value = foam['key']\n"
        "    return value\n",
    )
    assert violations == []


def test_type_checking_guarded_imports_are_exempt(tmp_path):
    violations = _violations_for(
        tmp_path,
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    import shutil\n",
    )
    assert violations == []


def test_a_clean_axis_style_module_passes(tmp_path):
    """Reads, returns patches and command arguments, writes nothing."""
    violations = _violations_for(
        tmp_path,
        "from pathlib import Path\n"
        "\n"
        "def resolve(value, staged_case_root):\n"
        "    contents = (Path(staged_case_root) / 'blockMeshDict').read_text()\n"
        "    return {'patches': (), 'command_arguments': {}}\n",
    )
    assert violations == []
