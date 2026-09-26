"""The quantities contract: units, sentinels before conversion, the reader
declaration (spec 2026-09-26 §3, §4)."""
from __future__ import annotations

import pytest

from omnidriver.core.quantities import (
    Quantity, QuantityReadError, ReadRequest, ReaderDeclarationError, UnitError,
    check_reader, convert, converted, read_quantities,
)
from omnidriver.core.runtime.models import DataArtifact
from plugins.quantity_toy import (
    GRID_FORMAT, VALUES_FORMAT, ToyNearestRowReader, ToyRowReader, _FurlongReader, write_toy_values,
)

ROWS = DataArtifact(artifact_id="record.solve.0", path_pattern="values.txt", format=VALUES_FORMAT)
GRID = DataArtifact(artifact_id="record.solve.0", path_pattern="grid.txt", format=GRID_FORMAT)


def test_the_table_converts_within_a_dimension():
    assert convert(1.5, "s", "ms") == pytest.approx(1500.0)
    assert convert(250.0, "us", "ms") == pytest.approx(0.25)
    assert convert(3.5, "mm", "um") == 3500.0
    assert convert(0.007, "m", "mm") == pytest.approx(7.0)
    assert convert(2.0, "cm", "mm") == 20.0


def test_a_conversion_across_dimensions_is_refused():
    with pytest.raises(UnitError, match=r"'ms' \(time\).*'mm' \(length\)"):
        convert(1.0, "ms", "mm")


def test_an_unknown_unit_is_refused_by_name():
    with pytest.raises(UnitError, match="'msec'"):
        convert(1.0, "msec", "ms")


def test_a_sentinel_is_resolved_before_conversion(tmp_path):
    """-1 s means never reached. It is never -1000 ms."""
    write_toy_values(tmp_path / "values.txt", {"a": ("0.0015", (0, 0, 0.007)), "b": ("-1", (0.02, 0.003, 0))})
    a, b = read_quantities(ToyRowReader(), tmp_path, ROWS, ReadRequest(names=("a", "b")))
    assert (b.status, b.value, b.unit) == ("not_reached", None, "s")
    shown = converted(b, "ms")
    assert (shown.status, shown.value, shown.unit) == ("not_reached", None, "ms")
    assert converted(a, "ms").value == pytest.approx(1.5)
    assert (a.sampled_at, a.sampled_at_unit, a.sampling_rule, a.source_artifact) == (
        (0.0, 0.0, 0.007), "m", "toy-row", "values.txt",
    )


def test_a_not_reached_quantity_still_refuses_an_inconvertible_unit(tmp_path):
    write_toy_values(tmp_path / "values.txt", {"b": ("-1", (0, 0, 0))})
    (b,) = read_quantities(ToyRowReader(), tmp_path, ROWS, ReadRequest(names=("b",)))
    with pytest.raises(UnitError):
        converted(b, "mm")


def test_a_name_the_reader_does_not_return_is_refused_by_name(tmp_path):
    write_toy_values(tmp_path / "values.txt", {"a": ("0.1", (0, 0, 0))})
    with pytest.raises(QuantityReadError, match="'z'"):
        read_quantities(ToyRowReader(), tmp_path, ROWS, ReadRequest(names=("a", "z")))


def test_points_given_to_a_reader_that_takes_none_are_refused(tmp_path):
    write_toy_values(tmp_path / "values.txt", {"a": ("0.1", (0, 0, 0))})
    with pytest.raises(QuantityReadError, match="takes no points"):
        read_quantities(ToyRowReader(), tmp_path, ROWS, ReadRequest(names=("a",), points={"a": (0, 0, 0)}))


def test_a_point_reader_needs_a_point_for_every_name(tmp_path):
    (tmp_path / "grid.txt").write_text("0 0 0 1.0\n1 0 0 2.0\n")
    with pytest.raises(QuantityReadError, match="'far'"):
        read_quantities(ToyNearestRowReader(), tmp_path, GRID, ReadRequest(names=("far",)))
    (q,) = read_quantities(ToyNearestRowReader(), tmp_path, GRID,
                           ReadRequest(names=("far",), points={"far": (0.9, 0.0, 0.0)}))
    assert (q.value, q.unit, q.sampled_at, q.sampled_at_unit) == (2.0, "ms", (1.0, 0.0, 0.0), "mm")


def test_a_reader_declaration_core_cannot_use_is_refused():
    with pytest.raises(ReaderDeclarationError, match="'furlong'"):
        check_reader(_FurlongReader(), artifact_format="toy")

    class NoPoints(ToyNearestRowReader):
        coordinate_unit = None

    with pytest.raises(ReaderDeclarationError, match="takes points"):
        check_reader(NoPoints(), artifact_format="toy")

    class TimeCoordinates(ToyRowReader):
        coordinate_unit = "ms"

    with pytest.raises(ReaderDeclarationError, match="length"):
        check_reader(TimeCoordinates(), artifact_format="toy")


@pytest.mark.parametrize(("kwargs", "match"), [
    ({"status": "evaluated", "value": None}, "exactly when"),
    ({"status": "not_reached", "value": 1.0}, "exactly when"),
    ({"status": "not_evaluated", "value": None, "reason": None}, "reason"),
    ({"status": "done", "value": None}, "status"),
])
def test_a_quantity_states_its_status_consistently(kwargs, match):
    base = dict(name="a", unit="s", source_artifact="values.txt", sampled_at=None,
                sampled_at_unit=None, sampling_rule="toy-row")
    with pytest.raises(ValueError, match=match):
        Quantity(**{**base, **kwargs})
