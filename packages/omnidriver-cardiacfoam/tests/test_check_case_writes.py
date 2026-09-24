"""``scripts/check-case-writes.py``: the static gate for design §5's
"records and axes write nothing" rule
(docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md).

This test lives here (not under ``packages/omnidriver`` -- core stays free
of cardiac/OpenFOAM vocabulary, including its own tests) even though the
gate itself scans BOTH ``omnidriver-openfoam/.../axes`` and
``omnidriver-cardiacfoam/.../records``: it is a single repo-level script,
like ``check-import-boundaries.py``, with no one package that owns it
alone.

Repo-only: the gate script lives at ``scripts/check-case-writes.py``, a
sibling of the packages, not inside any installed package -- unreachable
from a standalone wheel install. Per CLAUDE.md's own trap note, the lookup
below never raises at import time; it only returns ``None``, and the
skip marker (not a module-scope raise) is what makes this test skip cleanly
outside the monorepo checkout.
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


# ---------------------------------------------------------------------------
# The real tree passes.
# ---------------------------------------------------------------------------


def test_the_real_axes_and_records_trees_pass_the_gate():
    gate = _load_gate_module()
    assert gate.main() == 0


def test_scanned_roots_are_exactly_the_axes_and_records_directories():
    gate = _load_gate_module()
    relpaths = {
        str(root.relative_to(_REPO_ROOT)) for root in gate.SCANNED_ROOTS
    }
    assert relpaths == {
        "packages/omnidriver-openfoam/src/omnidriver/openfoam/axes",
        "packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/records",
    }


def test_known_violations_is_empty():
    gate = _load_gate_module()
    assert gate.KNOWN_VIOLATIONS == frozenset()


# ---------------------------------------------------------------------------
# Every forbidden form fails the gate.
# ---------------------------------------------------------------------------


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
    """The whole `shutil` module is forbidden to import at all (the same
    "forbid the whole module" shape check-import-boundaries.py uses for
    `foamlib`) -- reaching `copytree` needs importing it first, so the
    import violation alone already refuses this whole shape."""
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
    """The shape a real axis module actually takes: reads, returns patches
    and command arguments, writes nothing."""
    violations = _violations_for(
        tmp_path,
        "from pathlib import Path\n"
        "\n"
        "def resolve(value, staged_case_root):\n"
        "    contents = (Path(staged_case_root) / 'blockMeshDict').read_text()\n"
        "    return {'patches': (), 'command_arguments': {}}\n",
    )
    assert violations == []
