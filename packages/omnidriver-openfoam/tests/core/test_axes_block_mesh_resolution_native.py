"""``block_mesh_resolution_axis`` against the REAL native cardiacFOAM
tutorials tree -- CLAUDE.md's "testing against real meshes": real case or
native-source drift gate, nothing invented. The native tutorials root comes
ONLY from ``OMNIDRIVER_NATIVE_TUTORIALS`` (supplied, never discovered); this
FAILS, not skips, when it is unset -- see ``_native_tutorials_root`` below,
copied from ``test_config_value_reader_contract.py``'s own established
pattern.

Two tests, matching the task's own two native checks:

1. ``block_mesh_resolution_axis`` against the real
   ``manufacturedSolutions/bathBidomain/system/blockMeshDict.3D`` with
   ``N=20`` produces a ``(20 20 20)`` patch. This file has THREE ``hex (``
   blocks (all currently ``80 80 80``), not one -- read directly below, not
   assumed.
2. The same axis, wired into a real ``TutorialRecord`` and run through
   ``record_execution.preview_record_case`` with the study value that
   reproduces the file's OWN current resolution (``80``), reports that
   patch ``"unchanged"`` -- design §4 step 7.

**Extended 2026-09-26 (P2,
``docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md``
§5e): several documents, over bath's three files and bidomain's.** Bath's
``system/blockMeshDict.1D``/``.2D``/``.3D`` each have THREE agreeing
``hex (`` blocks (``expected_blocks=3``), and each file refines a different
subset of directions -- ``.1D`` is ``(80 1 1)``, ``.2D`` is ``(80 80 1)``,
``.3D`` is ``(80 80 80)`` (read directly below, not assumed) -- exactly the
real shape owner decision (d) describes ("a direction whose current count
is 1 stays 1... reading which directions are refined FROM EACH FILE
ITSELF"). Bidomain's own ``system/blockMeshDict.1D``/``.2D``/``.3D`` each
have exactly ONE ``hex (`` block (``expected_blocks=1``), with three
different current resolutions again (``(1280 1 1)``/``(640 640 1)``/
``(20 20 20)``) -- the other real shape this axis must support: several
single-block documents under one axis instance.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from omnidriver.core.runtime import record_execution
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep
from omnidriver.openfoam.axes import block_mesh_resolution_axis
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

pytestmark = pytest.mark.native

_BATH_BIDOMAIN_RELPATH = "manufacturedSolutions/bathBidomain"
_BLOCK_MESH_DOCUMENT = "system/blockMeshDict.3D"


def _native_tutorials_root() -> Path:
    value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
    if not value:
        pytest.fail(
            "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
            "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
            "supplied explicitly via that environment variable -- it is never "
            "discovered. Run e.g.:\n"
            "  OMNIDRIVER_NATIVE_TUTORIALS=/path/to/tutorials "
            "pytest -m native"
        )
    root = Path(value)
    if not root.is_dir():
        pytest.fail(f"OMNIDRIVER_NATIVE_TUTORIALS={value!r} is not a directory")
    return root


def _read_current_hex_cell_counts(text: str) -> str:
    """Parse the (assumed uniform) current cell counts out of a real
    ``blockMeshDict``'s first ``hex (`` line -- test-only scaffolding, not
    part of the axis: a real ``ConfigValueCapability`` reader for
    ``"hex_cell_counts"`` is future wiring (step 4/5), out of this task's
    scope (only the axis itself)."""
    match = re.search(r"hex \([^)]*\)\s*\(([^)]*)\)\s*simpleGrading", text)
    assert match is not None, "fixture has no `hex (` block to read"
    return match.group(1)


def _isotropic(n, current, extents=None):
    del current, extents
    return (n, n, n)


def _stays_at_one(n, current, extents=None):
    """Owner decision (d): "a direction whose current count is 1 stays 1"."""
    del extents
    return tuple(n if c != 1 else 1 for c in current)


def test_block_mesh_resolution_axis_against_the_real_bath_bidomain_block_mesh_dict(tmp_path):
    root = _native_tutorials_root()
    real_document = root / _BATH_BIDOMAIN_RELPATH / _BLOCK_MESH_DOCUMENT
    assert real_document.is_file(), f"fixture path missing: {real_document}"
    real_text = real_document.read_text()

    # Read the real file's current resolution directly, rather than assuming
    # it (task instruction: "Read the real file to learn its current
    # counts; do not assume them"). Confirms this fixture really does have
    # more than one `hex (` block, all at the same current resolution.
    hex_lines = [line for line in real_text.splitlines() if "hex (" in line]
    assert len(hex_lines) == 3
    assert all(_read_current_hex_cell_counts(line) == "80 80 80" for line in hex_lines)

    staged_case_root = tmp_path / "case"
    staged_document = staged_case_root / _BLOCK_MESH_DOCUMENT
    staged_document.parent.mkdir(parents=True)
    staged_document.write_text(real_text)  # the native tree is never written

    axis = block_mesh_resolution_axis(
        "number_cells", documents=(_BLOCK_MESH_DOCUMENT,), resolution=_isotropic,
        expected_blocks=3,
    )
    result = axis.resolve(20, staged_case_root)

    assert len(result.patches) == 1
    patch = result.patches[0]
    assert patch.document == _BLOCK_MESH_DOCUMENT
    # Typed data (2026-09-25 correction, `axes/block_mesh_resolution.py`'s
    # own module docstring), not pre-joined text.
    assert patch.value == (20, 20, 20)
    # expected_blocks=3 travels through the patch's own key path (P2).
    assert patch.key_path == ("hex_cell_counts", "3")


# ---------------------------------------------------------------------------
# P2 (2026-09-26): several documents at once, over bath's three real
# `blockMeshDict.<dim>` files -- decision (d)'s own reusable resolution,
# "a direction whose current count is 1 stays 1", against real content.
# ---------------------------------------------------------------------------


def test_block_mesh_resolution_axis_over_all_three_real_bath_bidomain_documents(tmp_path):
    root = _native_tutorials_root()
    bath_root = root / _BATH_BIDOMAIN_RELPATH
    documents = (
        "system/blockMeshDict.1D",
        "system/blockMeshDict.2D",
        "system/blockMeshDict.3D",
    )

    staged_case_root = tmp_path / "case"
    real_current: dict[str, str] = {}
    for document in documents:
        real_document = bath_root / document
        assert real_document.is_file(), f"fixture path missing: {real_document}"
        real_text = real_document.read_text()
        hex_lines = [line for line in real_text.splitlines() if "hex (" in line]
        assert len(hex_lines) == 3, f"{document}: expected 3 hex ( blocks"
        counts = {_read_current_hex_cell_counts(line) for line in hex_lines}
        assert len(counts) == 1, f"{document}: its blocks disagree: {counts}"
        real_current[document] = next(iter(counts))

        staged_document = staged_case_root / document
        staged_document.parent.mkdir(parents=True, exist_ok=True)
        staged_document.write_text(real_text)  # the native tree is never written

    # Read directly from the real files, not assumed: each dimension refines
    # a different subset of directions.
    assert real_current == {
        "system/blockMeshDict.1D": "80 1 1",
        "system/blockMeshDict.2D": "80 80 1",
        "system/blockMeshDict.3D": "80 80 80",
    }

    axis = block_mesh_resolution_axis(
        "number_cells", documents=documents, resolution=_stays_at_one,
        expected_blocks=3,
    )
    result = axis.resolve(20, staged_case_root)

    by_document = {patch.document: patch.value for patch in result.patches}
    assert by_document == {
        "system/blockMeshDict.1D": (20, 1, 1),
        "system/blockMeshDict.2D": (20, 20, 1),
        "system/blockMeshDict.3D": (20, 20, 20),
    }
    assert all(patch.key_path == ("hex_cell_counts", "3") for patch in result.patches)


# ---------------------------------------------------------------------------
# P2 (2026-09-26): bidomain's own three real `blockMeshDict.<dim>`
# documents -- the other real shape, one block per document
# (`expected_blocks=1`), still handled under one axis instance.
# ---------------------------------------------------------------------------


_BIDOMAIN_RELPATH = "manufacturedSolutions/bidomain"


def test_block_mesh_resolution_axis_over_all_three_real_bidomain_documents(tmp_path):
    root = _native_tutorials_root()
    bidomain_root = root / _BIDOMAIN_RELPATH
    documents = (
        "system/blockMeshDict.1D",
        "system/blockMeshDict.2D",
        "system/blockMeshDict.3D",
    )

    staged_case_root = tmp_path / "case"
    real_current: dict[str, str] = {}
    for document in documents:
        real_document = bidomain_root / document
        assert real_document.is_file(), f"fixture path missing: {real_document}"
        real_text = real_document.read_text()
        hex_lines = [line for line in real_text.splitlines() if "hex (" in line]
        assert len(hex_lines) == 1, f"{document}: expected 1 hex ( block"
        real_current[document] = _read_current_hex_cell_counts(hex_lines[0])

        staged_document = staged_case_root / document
        staged_document.parent.mkdir(parents=True, exist_ok=True)
        staged_document.write_text(real_text)

    assert real_current == {
        "system/blockMeshDict.1D": "1280 1 1",
        "system/blockMeshDict.2D": "640 640 1",
        "system/blockMeshDict.3D": "20 20 20",
    }

    axis = block_mesh_resolution_axis(
        "number_cells", documents=documents, resolution=_stays_at_one,
    )
    result = axis.resolve(50, staged_case_root)

    by_document = {patch.document: patch.value for patch in result.patches}
    assert by_document == {
        "system/blockMeshDict.1D": (50, 1, 1),
        "system/blockMeshDict.2D": (50, 50, 1),
        "system/blockMeshDict.3D": (50, 50, 50),
    }
    # expected_blocks=1 (the default) -- the bare key path, unchanged.
    assert all(patch.key_path == ("hex_cell_counts",) for patch in result.patches)


# ---------------------------------------------------------------------------
# Test-only scaffolding for the full `preview_record_case` pipeline: a
# record-key validator, case-value comparator and config-value reader for
# this axis's own `("hex_cell_counts",)` patch shape. None of this lives in
# `axes/block_mesh_resolution.py` or in `OpenFOAMEnvironmentPlugin` -- wiring
# a real environment's `get_record_key_validator`/`get_case_value_comparator`
# /`get_config_value_reader` for tutorial-record studies is step 4/5's job
# (no real plugin implements any of the four record-pipeline hooks yet, by
# inspection), not this axis's. This proves the AXIS's own output correctly
# drives that pipeline once such an adapter exists, the same way core's own
# tests (`test_tutorial_records.py`) prove the pipeline with their own toy
# JSON-document adapter.
# ---------------------------------------------------------------------------


def _hex_cell_counts_validator(document, key_path, value):
    # P2 (2026-09-26): matched by PREFIX, not exact equality -- a patch
    # declaring `expected_blocks` > 1 now carries a second key-path segment
    # (`case_planning.hex_cell_counts_key_path`), and this test-only catalog
    # must recognise that shape too, the same way the real environment's
    # `_read_config_value_by_key_path` does.
    if key_path[:1] == ("hex_cell_counts",):
        # design §5's environment-owned-key exception: no full OpenFOAM key
        # catalog exists yet, so this is written (or, here, merely compared)
        # unvalidated rather than refused.
        return "hex_cell_counts", False
    raise KeyError(f"{document}:{'.'.join(key_path)} is not in this test's catalog")


def _hex_cell_counts_agree(value_kind, requested, current) -> bool:
    if current is None:
        return False
    # `requested` is the axis's own typed tuple of ints (2026-09-25
    # correction) -- space-join it the same way the real writer would
    # before comparing token-for-token against `current`'s text.
    if isinstance(requested, (tuple, list)):
        requested_text = " ".join(str(item) for item in requested)
    else:
        requested_text = str(requested)
    return requested_text.split() == str(current).split()


def _read_current_value(document_path: Path, key_path):
    if key_path[:1] != ("hex_cell_counts",):
        return None
    if not document_path.exists():
        return None
    return _read_current_hex_cell_counts(document_path.read_text())


class _RecordTestPlugin(OpenFOAMEnvironmentPlugin):
    """The real OpenFOAM environment plugin, plus the four tutorial-record
    hooks this test needs -- see the scaffolding note above for why they are
    supplied here rather than by the real plugin."""

    def __init__(self, record: TutorialRecord) -> None:
        self._record = record

    def get_tutorial_records(self):
        return {self._record.name: self._record}

    def get_record_key_validator(self):
        return _hex_cell_counts_validator

    def get_case_value_comparator(self):
        return _hex_cell_counts_agree

    def get_config_value_reader(self):
        return _read_current_value


def test_preview_record_case_reports_the_matching_resolution_as_unchanged():
    from omnidriver.core.plugin_interface import driver_context

    root = _native_tutorials_root()
    real_document = root / _BATH_BIDOMAIN_RELPATH / _BLOCK_MESH_DOCUMENT
    assert real_document.is_file(), f"fixture path missing: {real_document}"

    axis = block_mesh_resolution_axis(
        "number_cells", documents=(_BLOCK_MESH_DOCUMENT,), resolution=_isotropic,
        expected_blocks=3,
    )
    record = TutorialRecord(
        name="bathBidomainNativeTest",
        native_case_relpath=_BATH_BIDOMAIN_RELPATH,
        axes=(axis,),
        workflow_steps=(WorkflowStep(step_id="mesh", command=("blockMesh",)),),
    )
    context = driver_context(
        _RecordTestPlugin(record), source="test:native-block-mesh-preview",
    )

    # The real file's own current resolution, read directly rather than
    # assumed -- N=80 reproduces it via `lambda n: (n, n, n)`.
    preview = record_execution.preview_record_case(
        record,
        cases_root=root,
        study_by_source={"base": {"number_cells": 80}},
        driver_context=context,
    )

    patches = preview["patches"]
    assert len(patches) == 1
    assert patches[0]["document"] == _BLOCK_MESH_DOCUMENT
    assert patches[0]["value"] == (80, 80, 80)
    assert patches[0]["status"] == "unchanged"


def test_preview_record_case_reports_a_different_resolution_as_changed():
    """The contrast case: proves `"unchanged"` above is a real comparison,
    not every patch reported unchanged unconditionally."""
    from omnidriver.core.plugin_interface import driver_context

    root = _native_tutorials_root()
    real_document = root / _BATH_BIDOMAIN_RELPATH / _BLOCK_MESH_DOCUMENT
    assert real_document.is_file(), f"fixture path missing: {real_document}"

    axis = block_mesh_resolution_axis(
        "number_cells", documents=(_BLOCK_MESH_DOCUMENT,), resolution=_isotropic,
        expected_blocks=3,
    )
    record = TutorialRecord(
        name="bathBidomainNativeTest",
        native_case_relpath=_BATH_BIDOMAIN_RELPATH,
        axes=(axis,),
        workflow_steps=(WorkflowStep(step_id="mesh", command=("blockMesh",)),),
    )
    context = driver_context(
        _RecordTestPlugin(record), source="test:native-block-mesh-preview-changed",
    )

    preview = record_execution.preview_record_case(
        record,
        cases_root=root,
        study_by_source={"base": {"number_cells": 20}},
        driver_context=context,
    )

    patches = preview["patches"]
    assert len(patches) == 1
    assert patches[0]["value"] == (20, 20, 20)
    assert patches[0]["status"] == "changed"
