"""The point-sampling reference loader: form and citations, never truth."""
from __future__ import annotations

import json

import pytest

from omnidriver.core.quantities import PointReferenceError, load_point_reference
from plugins.quantity_toy import write_toy_reference


def _edit(path, change):
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))
    return path


def test_a_reference_loads_with_its_digest_and_unresolved_points(tmp_path):
    reference = load_point_reference(write_toy_reference(tmp_path / "r.json"))
    assert (reference.reference_id, reference.quantity_unit, reference.length_unit) == ("toy-reference", "ms", "m")
    assert reference.points["A"].coordinates == (0.0, 0.0, 0.007)
    assert reference.points["Q"].coordinates is None and reference.points["Q"].unresolved == "the toy never says"
    assert reference.digest.startswith("sha256:")


@pytest.mark.parametrize(("change", "match"), [
    (lambda d: d["points"][2].pop("unresolved"), "unresolved"),
    (lambda d: d["points"][0].update(unresolved="but it has coordinates"), "points/0"),
    (lambda d: d["points"].append(dict(d["points"][0])), "'A'.*more than once"),
    (lambda d: d["points"][0]["source"].update(source_id="elsewhere"), "'elsewhere'"),
    (lambda d: d["frame"].update(length_unit="ms"), "length"),
    (lambda d: d["quantity"].update(unit="msec"), "'msec'"),
    (lambda d: d.update(published_values=[{"label": "A", "kind": "range", "unit": "ms", "conditions": "c",
                                            "range": [2.0, 1.0], "source": {"source_id": "toy", "where": "x"}}]), "range"),
    (lambda d: d.update(published_values=[{"label": "Z", "kind": "value", "unit": "ms", "conditions": "c",
                                            "value": 1.0, "source": {"source_id": "toy", "where": "x"}}]), "'Z'"),
    (lambda d: d.update(tolerances=[]), "tolerances"),
])
def test_a_malformed_reference_is_refused_by_name(tmp_path, change, match):
    path = _edit(write_toy_reference(tmp_path / "r.json"), change)
    with pytest.raises(PointReferenceError, match=match):
        load_point_reference(path)
