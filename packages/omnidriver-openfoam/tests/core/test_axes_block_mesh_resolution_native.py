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
   assumed -- which is exactly why the axis itself never checks a
   document's hex-block count (see ``axes/block_mesh_resolution.py``'s
   module docstring): a strict eager check here would refuse this real,
   legitimate document before ever computing a patch value for it.
2. The same axis, wired into a real ``TutorialRecord`` and run through
   ``record_execution.preview_record_case`` with the study value that
   reproduces the file's OWN current resolution (``80``), reports that
   patch ``"unchanged"`` -- design §4 step 7.
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


def test_block_mesh_resolution_axis_against_the_real_bath_bidomain_block_mesh_dict(tmp_path):
    root = _native_tutorials_root()
    real_document = root / _BATH_BIDOMAIN_RELPATH / _BLOCK_MESH_DOCUMENT
    assert real_document.is_file(), f"fixture path missing: {real_document}"
    real_text = real_document.read_text()

    # Read the real file's current resolution directly, rather than assuming
    # it (task instruction: "Read the real file to learn its current
    # counts; do not assume them"). Confirms this fixture really does have
    # more than one `hex (` block, all at the same current resolution --
    # the exact reason the axis itself never checks the block count (see
    # ``axes/block_mesh_resolution.py``'s module docstring).
    hex_lines = [line for line in real_text.splitlines() if "hex (" in line]
    assert len(hex_lines) == 3
    assert all(_read_current_hex_cell_counts(line) == "80 80 80" for line in hex_lines)

    staged_case_root = tmp_path / "case"
    staged_document = staged_case_root / _BLOCK_MESH_DOCUMENT
    staged_document.parent.mkdir(parents=True)
    staged_document.write_text(real_text)  # the native tree is never written

    axis = block_mesh_resolution_axis(
        "number_cells", document=_BLOCK_MESH_DOCUMENT, resolution=lambda n: (n, n, n),
    )
    result = axis.resolve(20, staged_case_root)

    assert len(result.patches) == 1
    patch = result.patches[0]
    assert patch.document == _BLOCK_MESH_DOCUMENT
    assert patch.value == "20 20 20"


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
    if key_path == ("hex_cell_counts",):
        # design §5's environment-owned-key exception: no full OpenFOAM key
        # catalog exists yet, so this is written (or, here, merely compared)
        # unvalidated rather than refused.
        return "hex_cell_counts", False
    raise KeyError(f"{document}:{'.'.join(key_path)} is not in this test's catalog")


def _hex_cell_counts_agree(value_kind, requested, current) -> bool:
    if current is None:
        return False
    return str(requested).split() == str(current).split()


def _read_current_value(document_path: Path, key_path):
    if key_path != ("hex_cell_counts",):
        return None
    if not document_path.exists():
        return None
    return _read_current_hex_cell_counts(document_path.read_text())


class _RecordTestPlugin(OpenFOAMEnvironmentPlugin):
    """The real OpenFOAM environment plugin, plus the four tutorial-record
    hooks this test needs -- see the scaffolding note above for why they are
    supplied here rather than by the real plugin."""

    def __init__(self, record: TutorialRecord, axis) -> None:
        self._record = record
        self._axis = axis

    def get_tutorial_records(self):
        return {self._record.name: self._record}

    def get_axis_catalog(self):
        return {self._axis.name: self._axis}

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
        "number_cells", document=_BLOCK_MESH_DOCUMENT, resolution=lambda n: (n, n, n),
    )
    record = TutorialRecord(
        name="bathBidomainNativeTest",
        native_case_relpath=_BATH_BIDOMAIN_RELPATH,
        allowed_axes=frozenset({"number_cells"}),
        workflow_steps=(WorkflowStep(step_id="mesh", command=("blockMesh",)),),
    )
    context = driver_context(
        _RecordTestPlugin(record, axis), source="test:native-block-mesh-preview",
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
    assert patches[0]["value"] == "80 80 80"
    assert patches[0]["status"] == "unchanged"


def test_preview_record_case_reports_a_different_resolution_as_changed():
    """The contrast case: proves `"unchanged"` above is a real comparison,
    not every patch reported unchanged unconditionally."""
    from omnidriver.core.plugin_interface import driver_context

    root = _native_tutorials_root()
    real_document = root / _BATH_BIDOMAIN_RELPATH / _BLOCK_MESH_DOCUMENT
    assert real_document.is_file(), f"fixture path missing: {real_document}"

    axis = block_mesh_resolution_axis(
        "number_cells", document=_BLOCK_MESH_DOCUMENT, resolution=lambda n: (n, n, n),
    )
    record = TutorialRecord(
        name="bathBidomainNativeTest",
        native_case_relpath=_BATH_BIDOMAIN_RELPATH,
        allowed_axes=frozenset({"number_cells"}),
        workflow_steps=(WorkflowStep(step_id="mesh", command=("blockMesh",)),),
    )
    context = driver_context(
        _RecordTestPlugin(record, axis), source="test:native-block-mesh-preview-changed",
    )

    preview = record_execution.preview_record_case(
        record,
        cases_root=root,
        study_by_source={"base": {"number_cells": 20}},
        driver_context=context,
    )

    patches = preview["patches"]
    assert len(patches) == 1
    assert patches[0]["value"] == "20 20 20"
    assert patches[0]["status"] == "changed"
