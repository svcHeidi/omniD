"""``block_mesh_resolution_axis`` against the REAL native cardiacFOAM
tutorials tree. ``OMNIDRIVER_NATIVE_TUTORIALS`` supplies the root (never
discovered); FAILS, not skips, when unset.
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
    """Parse the current cell counts out of a real `blockMeshDict`'s first
    `hex (` line -- test-only scaffolding, not part of the axis."""
    match = re.search(r"hex \([^)]*\)\s*\(([^)]*)\)\s*simpleGrading", text)
    assert match is not None, "fixture has no `hex (` block to read"
    return match.group(1)


def _isotropic(n, current, extents=None):
    del current, extents
    return (n, n, n)


def _stays_at_one(n, current, extents=None):
    """A direction whose current count is 1 stays 1."""
    del extents
    return tuple(n if c != 1 else 1 for c in current)


def test_block_mesh_resolution_axis_against_the_real_bath_bidomain_block_mesh_dict(tmp_path):
    root = _native_tutorials_root()
    real_document = root / _BATH_BIDOMAIN_RELPATH / _BLOCK_MESH_DOCUMENT
    assert real_document.is_file(), f"fixture path missing: {real_document}"
    real_text = real_document.read_text()

    # Read the real file's current resolution directly rather than assuming
    # it; confirms this fixture has more than one `hex (` block, all at the
    # same current resolution.
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
    # Typed data, not pre-joined text.
    assert patch.value == (20, 20, 20)
    # expected_blocks=3 travels through the patch's own key path.
    assert patch.key_path == ("hex_cell_counts", "3")


# ---------------------------------------------------------------------------
# Several documents at once, over bath's three real `blockMeshDict.<dim>`
# files -- the reusable "a direction whose current count is 1 stays 1"
# resolution, against real content.
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
# Bidomain's own three real `blockMeshDict.<dim>` documents -- the other
# real shape, one block per document (expected_blocks=1), still handled
# under one axis instance.
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
# `axes/block_mesh_resolution.py` or in `OpenFOAMEnvironmentPlugin`; this
# proves the AXIS's own output correctly drives that pipeline, the same way
# core's own `test_tutorial_records.py` proves the pipeline with a toy JSON
# adapter.
# ---------------------------------------------------------------------------


def _hex_cell_counts_validator(document, key_path, value):
    # Matched by PREFIX, not exact equality: a patch declaring
    # `expected_blocks` > 1 carries a second key-path segment
    # (`case_planning.hex_cell_counts_key_path`), which this test-only
    # catalog must recognise too, the same way the real environment's
    # `_read_config_value_by_key_path` does.
    if key_path[:1] == ("hex_cell_counts",):
        # Environment-owned-key exception: no full OpenFOAM key catalog
        # exists yet, so this is compared unvalidated rather than refused.
        return "hex_cell_counts", False
    raise KeyError(f"{document}:{'.'.join(key_path)} is not in this test's catalog")


def _hex_cell_counts_agree(value_kind, requested, current) -> bool:
    if current is None:
        return False
    # `requested` is the axis's own typed tuple of ints -- space-join it the
    # same way the real writer would before comparing token-for-token
    # against `current`'s text.
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
    """The real OpenFOAM environment plugin, plus the tutorial-record hooks
    this test needs (see the scaffolding note above)."""

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


# ---------------------------------------------------------------------------
# extents, read from the real native files: the Niederer slab is 20x3x7 mm
# under `scale 0.001`; bidomain's `.3D` is the unit cube with no `scale`.
# ---------------------------------------------------------------------------

_NIEDERER_BLOCK_MESH = "NiedererEtAl2011verification/system/blockMeshDict"
_BIDOMAIN_BLOCK_MESH_3D = "manufacturedSolutions/bidomain/system/blockMeshDict.3D"


def _dx_resolution(dx, current, extents):
    from omnidriver.openfoam.mesh_provisioning import cell_counts_from_dx

    del current
    return cell_counts_from_dx(dx, extents)


def _extent(path: Path) -> tuple[float, float, float]:
    from omnidriver.openfoam.case_planning import read_hex_block_extent_m

    extent = read_hex_block_extent_m(path)
    assert extent is not None, path
    return extent


def test_the_extent_is_each_real_documents_own_in_metres(tmp_path):
    """The reason ``extents`` exists: a ``resolution`` converting a cell
    size (niederer2011's ``dx``) must see the document's own geometry. One
    ``dx``, two real documents, two different counts."""
    root = _native_tutorials_root()
    assert _extent(root / _NIEDERER_BLOCK_MESH) == pytest.approx((0.02, 0.003, 0.007))
    assert _extent(root / _BIDOMAIN_BLOCK_MESH_3D) == pytest.approx((1.0, 1.0, 1.0))

    niederer = block_mesh_resolution_axis(
        "dx", documents=("system/blockMeshDict",), resolution=_dx_resolution, value_kind="scalar",
    )
    bidomain = block_mesh_resolution_axis(
        "dx", documents=("system/blockMeshDict.3D",), resolution=_dx_resolution, value_kind="scalar",
    )
    assert niederer.resolve(0.0005, root / "NiedererEtAl2011verification").patches[0].value == (40, 6, 14)
    assert niederer.resolve(0.001, root / "NiedererEtAl2011verification").patches[0].value == (20, 3, 7)
    assert bidomain.resolve(0.1, root / "manufacturedSolutions/bidomain").patches[0].value == (10, 10, 10)


def _niederer_copy(tmp_path: Path, edit) -> Path:
    """The real Niederer ``blockMeshDict`` with its scaling line edited, and
    nothing else changed."""
    text = (_native_tutorials_root() / _NIEDERER_BLOCK_MESH).read_text()
    assert text.count("scale   0.001;") == 1, "the native file's scale line moved"
    target = tmp_path / "blockMeshDict"
    target.write_text(edit(text))
    return target


def test_convert_to_meters_is_read_when_scale_is_absent(tmp_path):
    """OpenFOAM's ``blockMesh::readPointTransforms`` reads the scale with
    ``dict.findCompat("scale", {{"convertToMeters", 1012}})``: the pre-2010
    keyword is still honoured."""
    path = _niederer_copy(tmp_path, lambda text: text.replace("scale   0.001;", "convertToMeters 0.001;"))
    assert _extent(path) == pytest.approx((0.02, 0.003, 0.007))


def test_scale_wins_when_both_keywords_are_present(tmp_path):
    """``dictionary::csearchCompat`` (``src/OpenFOAM/db/dictionary/
    dictionaryCompat.C``) returns ``scale`` when it is found, and looks at
    ``convertToMeters`` only when it is not."""
    path = _niederer_copy(
        tmp_path, lambda text: text.replace("scale   0.001;", "convertToMeters 1;\nscale   0.001;"),
    )
    assert _extent(path) == pytest.approx((0.02, 0.003, 0.007))


def test_a_non_positive_scale_means_no_scaling_as_in_blockmesh(tmp_path):
    """``readScaling`` applies a scalar only when ``val > 0``; otherwise the
    scaling stays uniform 1."""
    path = _niederer_copy(tmp_path, lambda text: text.replace("scale   0.001;", "scale   0;"))
    assert _extent(path) == pytest.approx((20.0, 3.0, 7.0))


def test_a_scale_this_reader_cannot_parse_is_refused_by_name(tmp_path):
    """``readScaling`` also takes a vector (per-component scaling). This
    text reader reads a scalar only, so it refuses anything else by name
    rather than reading it as 1.0."""
    path = _niederer_copy(tmp_path, lambda text: text.replace("scale   0.001;", "scale   (0.001 0.001 0.001);"))
    from omnidriver.openfoam.case_planning import read_hex_block_extent_m

    with pytest.raises(ValueError, match=r"'scale'.*\(0\.001 0\.001 0\.001\)"):
        read_hex_block_extent_m(path)
