"""Toy readers and a toy record for the quantities contract.

Core-owned claims only (units, sentinels, the reader contract, the
comparison): no geometry and no solver behaviour is asserted from these
files. Solver claims are tested against real binaries in each plugin's
package.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping

from omnidriver.core.quantities import RawSample
from omnidriver.core.tutorial_records import ProducedPath, TutorialRecord, WorkflowStep

from plugins.e2e_record_plugin import (
    E2ERecordPlugin, _known_catalog_validator, _number_cells_axis, _typed_agree,
)
from plugins.minimal_plugin import MinimalTestPlugin

VALUES_FORMAT = "toy_named_values"
GRID_FORMAT = "toy_grid_values"
QUANTITY_TOY_PLUGIN = "plugins.quantity_toy:QuantityToyPlugin"
UNREADABLE_PLUGIN = "plugins.quantity_toy:UnreadableFormatPlugin"
BAD_DECLARATION_PLUGIN = "plugins.quantity_toy:BadDeclarationPlugin"


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
