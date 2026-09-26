"""Toy readers and a toy record for the quantities contract.

Core-owned claims only (units, sentinels, the reader contract, the
comparison): no geometry and no solver behaviour is asserted from these
files. Solver claims are tested against real binaries in each plugin's
package.
"""
from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path
from typing import Mapping

from omnidriver.core.quantities import RawSample
from omnidriver.core.runtime.models import DataArtifact
from omnidriver.core.runtime.sweep_manifest import CaseManifestEntry, SweepManifest, write_manifest
from omnidriver.core.tutorial_records import ProducedPath, TutorialRecord, WorkflowStep

from plugins.e2e_record_plugin import (
    E2ERecordPlugin, _known_catalog_validator, _number_cells_axis, _typed_agree,
)
from plugins.minimal_plugin import MinimalTestPlugin

_CITE = {"source_id": "toy", "where": "this file"}

VALUES_FORMAT = "toy_named_values"
GRID_FORMAT = "toy_grid_values"
QUANTITY_TOY_PLUGIN = "plugins.quantity_toy:QuantityToyPlugin"
DIFFERENT_VERSION_QUANTITY_TOY_PLUGIN = "plugins.quantity_toy:DifferentVersionQuantityToyPlugin"
RAISING_READER_PLUGIN = "plugins.quantity_toy:RaisingReaderPlugin"
UNREADABLE_PLUGIN = "plugins.quantity_toy:UnreadableFormatPlugin"
BAD_DECLARATION_PLUGIN = "plugins.quantity_toy:BadDeclarationPlugin"
NO_WHERE_READER_PLUGIN = "plugins.quantity_toy:NoWhereReaderPlugin"


class ToyRowReader:
    """``<name> <value> <x> <y> <z>`` rows: seconds, ``-1`` never reached, metres.
    Samples where the file says it sampled, so it takes no points."""

    value_unit = "s"
    sentinels = frozenset({-1.0})
    sampling_rule = "toy-row"
    coordinate_unit = "m"
    takes_points = False

    def read(self, case_root, artifact, request):
        rows = {}
        for line in (Path(case_root) / artifact.path_pattern).read_text().splitlines():
            if line.strip():
                name, value, x, y, z = line.split()
                rows[name] = RawSample(name=name, value=float(value), sampled_at=(float(x), float(y), float(z)))
        return tuple(rows[name] for name in request.names if name in rows)


class ToyNearestRowReader:
    """``<x> <y> <z> <value>`` rows in mm and ms; samples the row nearest each supplied point."""

    value_unit = "ms"
    sentinels = frozenset({-1.0})
    sampling_rule = "toy-nearest-row"
    coordinate_unit = "mm"
    takes_points = True

    def read(self, case_root, artifact, request):
        rows = []
        for line in (Path(case_root) / artifact.path_pattern).read_text().splitlines():
            if line.strip():
                x, y, z, value = (float(v) for v in line.split())
                rows.append(((x, y, z), value))
        samples = []
        for name in request.names:
            target = request.points[name]
            point, value = min(rows, key=lambda row: math.dist(row[0], target))
            samples.append(RawSample(name=name, value=value, sampled_at=point))
        return tuple(samples)


class _FurlongReader(ToyRowReader):
    value_unit = "furlong"


class _NoWhereRowReader(ToyRowReader):
    """Same contract as ``ToyRowReader`` (``takes_points = False``), but
    never reports where it sampled -- proof that a self-sampling reader's
    sample without ``sampled_at`` is a named gap when the request gives
    *expected* points to check it against (I3, controller review
    2026-09-26). It is not an I1 case: I1 is about a *points-taking*
    reader; this reader never takes points at all."""

    def read(self, case_root, artifact, request):
        return tuple(
            RawSample(name=sample.name, value=sample.value)
            for sample in ToyRowReader.read(self, case_root, artifact, request)
        )


class _RaisingReader(ToyRowReader):
    """Declares the same contract as ``ToyRowReader``, but ``.read`` always
    raises a non-``ValueError`` exception: proof that ANY reader exception
    becomes a named ``not_evaluated`` gap, not a crash (N3, controller
    review 2026-09-26)."""

    def read(self, case_root, artifact, request):
        raise OSError("disk fell over")


def write_toy_values(path: Path, rows: Mapping[str, tuple[str, tuple[float, float, float]]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{name} {value} {x} {y} {z}\n" for name, (value, (x, y, z)) in rows.items()))
    return path


TOY_QUANTITY_RECORD = TutorialRecord(
    name="toyQuantities",
    native_case_relpath="toyQuantities",
    allowed_axes=frozenset({"number_cells"}),
    workflow_steps=(WorkflowStep(
        step_id="solve", command=("cp", "seed/values.txt", "values.txt"),
        consumes=("constant/mesh.json", "seed/values.txt"),
        produces=(ProducedPath("values.txt", format=VALUES_FORMAT),),
    ),),
)


def write_quantity_toy_case(cases_root: Path, values_text: str) -> Path:
    import json

    native = cases_root / "toyQuantities"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1", "label": "toy"}))
    (native / "seed").mkdir()
    (native / "seed" / "values.txt").write_text(values_text)
    return native


class QuantityToyPlugin(E2ERecordPlugin):
    _READERS = {VALUES_FORMAT: ToyRowReader(), GRID_FORMAT: ToyNearestRowReader()}

    def __init__(self) -> None:
        MinimalTestPlugin.__init__(
            self,
            solver_commands=frozenset({"cp"}),
            tutorial_records={"toyQuantities": TOY_QUANTITY_RECORD},
            axis_catalog={"number_cells": _number_cells_axis()},
            record_key_validator=_known_catalog_validator,
            case_value_comparator=_typed_agree,
        )

    def get_artifact_value_reader(self, artifact_format: str):
        return self._READERS.get(artifact_format)


class RaisingReaderPlugin(QuantityToyPlugin):
    """Same tutorial record and axes as ``QuantityToyPlugin``, but its values
    reader always raises ``OSError`` -- see ``_RaisingReader``."""

    _READERS = {VALUES_FORMAT: _RaisingReader()}


class NoWhereReaderPlugin(QuantityToyPlugin):
    """Same tutorial record and axes as ``QuantityToyPlugin``, but its values
    reader never reports where it sampled -- see ``_NoWhereRowReader``."""

    _READERS = {VALUES_FORMAT: _NoWhereRowReader()}


class DifferentVersionQuantityToyPlugin(QuantityToyPlugin):
    """Same class family, a genuinely different declared version -- unlike
    two distinct classes sharing ``MinimalTestPlugin``'s hardcoded
    ``plugin_id``, this changes ``capability_digest`` (its payload embeds
    each provider's version; see ``provider_identity.build_stack_identity``),
    so the shared ``stack_identity_mismatch`` check catches it (B1,
    controller review 2026-09-26)."""

    @property
    def plugin_version(self) -> str:
        return "9.9.9"


class UnreadableFormatPlugin(E2ERecordPlugin):
    """Declares a format on toyTutorial's output and has no reader for it."""

    def get_tutorial_records(self) -> dict:
        record = super().get_tutorial_records()["toyTutorial"]
        step = record.workflow_steps[0]
        import dataclasses

        step = dataclasses.replace(step, produces=(ProducedPath("solved.marker", format="toy_unreadable"),))
        return {"toyTutorial": dataclasses.replace(record, workflow_steps=(step,))}


class BadDeclarationPlugin(UnreadableFormatPlugin):
    """Has a reader for the format, whose value unit is not in core's table."""

    def get_artifact_value_reader(self, artifact_format: str):
        return _FurlongReader() if artifact_format == "toy_unreadable" else None


def write_toy_reference(path: Path, *, quantity_unit: str = "ms") -> Path:
    path.write_text(json.dumps({
        "schema_version": 1, "id": "toy-reference", "version": "1",
        "sources": [{"id": "toy", "citation": "the toy's own definition", "accessed": True}],
        "quantity": {"name": "first crossing", "definition": "the toy's value", "unit": quantity_unit, "source": _CITE},
        "frame": {"length_unit": "m", "definition": "the toy's frame", "stated_by_source": True, "source": _CITE},
        "points": [
            {"label": "A", "definition": "row a", "coordinates": [0, 0, 0.007], "source": _CITE},
            {"label": "B", "definition": "row b", "coordinates": [0.02, 0.003, 0], "source": _CITE},
            {"label": "Q", "definition": "not settled", "coordinates": None, "unresolved": "the toy never says", "source": _CITE},
        ],
    }))
    return path


def write_toy_sweep(output_dir: Path, cases: Mapping[str, str | None], *, plugin: str = QUANTITY_TOY_PLUGIN,
                    status: str = "completed", artifact_format: str = VALUES_FORMAT) -> Path:
    """A sweep output in the shape sweep_run leaves: manifest, run documents
    carrying the planning stack's identity, workflow states with digests,
    and each case's ``values.txt`` (``None``: the run wrote none)."""
    from omnidriver.core.plugin_interface import load_plugin_context

    identity = load_plugin_context(plugin).identity.to_json()
    artifact = DataArtifact(artifact_id="record.solve.0", path_pattern="values.txt",
                            format=artifact_format, produced_by="solve")
    entries = []
    for case_id, text in cases.items():
        case_root = output_dir / "cases" / case_id
        case_root.mkdir(parents=True)
        if text is not None:
            (case_root / "values.txt").write_text(text)
        (case_root / "run_document.json").write_text(json.dumps({
            "plugin": identity, "launch": {"caseRoot": str(case_root)},
            "expectedArtifacts": [dataclasses.asdict(artifact)],
        }))
        (case_root / "workflow_state.json").write_text(json.dumps({
            "status": status, "workflow_digest": f"sha256:plan-{case_id}",
            "resume_snapshot": {"aggregate_digest": f"sha256:inputs-{case_id}"},
        }))
        entries.append(CaseManifestEntry(
            case_id=case_id, resolved_axis_values={}, override_hash="sha256:none",
            run_document_path=f"cases/{case_id}/run_document.json",
            workflow_state_path=f"cases/{case_id}/workflow_state.json",
            status=status, outcome="fresh", started_at=None, updated_at="2026-09-26T00:00:00+00:00",
        ))
    write_manifest(output_dir / "sweep_manifest.json", SweepManifest(
        schema_version="1.0", sweep_spec_hash="sha256:toy", created_at="2026-09-26T00:00:00+00:00",
        updated_at="2026-09-26T00:00:00+00:00", cases=entries,
    ))
    return output_dir
