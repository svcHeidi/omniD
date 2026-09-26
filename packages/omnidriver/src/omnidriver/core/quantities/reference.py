"""A point-sampling reference: named points, and where every fact came from.

Schema: ``omnidriver/schemas/point-reference.schema.json`` (packaged). The
loader checks form and citations, and computes nothing. Whether a value is
the source's own is a review question, answered by each file's ``sources``.
A point the source does not settle has ``coordinates: null`` and says why;
the comparison refuses to use it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Iterator, Mapping

import jsonschema

from .errors import PointReferenceError, UnitError
from .model import Point
from .units import check_convertible, dimension_of

_SCHEMA = json.loads(resources.files("omnidriver.schemas").joinpath("point-reference.schema.json").read_text())


@dataclass(frozen=True)
class ReferencePoint:
    label: str
    coordinates: Point | None
    unresolved: str | None


@dataclass(frozen=True)
class PointReference:
    reference_id: str
    version: str
    path: str
    digest: str
    quantity_name: str
    quantity_unit: str
    length_unit: str
    points: Mapping[str, ReferencePoint]


def schema_errors(document: Any, schema: Mapping[str, Any]) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    return sorted(
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(document)
    )


def _citations(document: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, str]]]:
    yield "quantity", document["quantity"]["source"]
    yield "frame", document["frame"]["source"]
    for point in document["points"]:
        yield f"point {point['label']!r}", point["source"]
    for index, value in enumerate(document.get("published_values", ())):
        yield f"published value {index}", value["source"]


def load_point_reference(path: str | Path) -> PointReference:
    path = Path(path)
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise PointReferenceError(f"cannot read the reference {path}: {exc}") from exc
    errors = schema_errors(document, _SCHEMA)
    if errors:
        raise PointReferenceError(f"{path} is not a point reference: " + "; ".join(errors))
    source_ids = [source["id"] for source in document["sources"]]
    if len(set(source_ids)) != len(source_ids):
        raise PointReferenceError(f"{path}: source ids repeat: {source_ids}")
    for where, citation in _citations(document):
        if citation["source_id"] not in source_ids:
            raise PointReferenceError(
                f"{path}: {where} cites {citation['source_id']!r}, which 'sources' does not declare ({source_ids})"
            )
    labels = [point["label"] for point in document["points"]]
    repeated = sorted({label for label in labels if labels.count(label) > 1})
    if repeated:
        raise PointReferenceError(f"{path}: point {repeated[0]!r} is declared more than once")
    unit = document["quantity"]["unit"]
    try:
        dimension_of(unit)
        if dimension_of(document["frame"]["length_unit"]) != "length":
            raise PointReferenceError(f"{path}: frame length_unit {document['frame']['length_unit']!r} is not a length")
        for value in document.get("published_values", ()):
            check_convertible(value["unit"], unit)
    except UnitError as exc:
        raise PointReferenceError(f"{path}: {exc}") from exc
    for value in document.get("published_values", ()):
        if value["label"] not in labels:
            raise PointReferenceError(f"{path}: a published value names point {value['label']!r}, which is not declared")
        if "range" in value and value["range"][0] > value["range"][1]:
            raise PointReferenceError(f"{path}: published range {value['range']} for {value['label']!r} is reversed")
    points = {
        point["label"]: ReferencePoint(
            label=point["label"],
            coordinates=tuple(float(c) for c in point["coordinates"]) if point["coordinates"] is not None else None,
            unresolved=point.get("unresolved"),
        )
        for point in document["points"]
    }
    return PointReference(
        reference_id=document["id"], version=document["version"], path=str(path),
        digest="sha256:" + hashlib.sha256(raw).hexdigest(), quantity_name=document["quantity"]["name"],
        quantity_unit=unit, length_unit=document["frame"]["length_unit"], points=points,
    )
