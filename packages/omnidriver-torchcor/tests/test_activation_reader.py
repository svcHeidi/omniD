from __future__ import annotations

import math
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from omnidriver.core.quantities import ReadRequest
from omnidriver.core.quantities.reading import check_reader
from omnidriver.torchcor.activation_reader import ACTIVATION_FORMAT, NearestNodeReader

FIXTURE = Path(__file__).parent / "fixtures" / "activation_times.dat"
ARTIFACT = SimpleNamespace(path_pattern="out/activation_times.dat", format=ACTIVATION_FORMAT)


def _case(tmp_path: Path, text: str | None = None) -> Path:
    (tmp_path / "out").mkdir()
    target = tmp_path / ARTIFACT.path_pattern
    if text is None:
        shutil.copy(FIXTURE, target)
    else:
        target.write_text(text)
    return tmp_path


def _read(case_root: Path, points: dict) -> dict:
    samples = NearestNodeReader().read(case_root, ARTIFACT, ReadRequest(names=tuple(points), points=points))
    return {s.name: s for s in samples}


def test_the_declaration_is_one_core_can_use():
    check_reader(NearestNodeReader(), artifact_format=ACTIVATION_FORMAT)


def test_the_corners_are_nodes_and_read_the_runs_own_values_G1(tmp_path):
    read = _read(_case(tmp_path), {"P1": (0.0, 0.0, 0.0), "P8": (20.0, 7.0, 3.0)})
    assert (read["P1"].value, read["P1"].sampled_at) == (0.955, (0.0, 0.0, 0.0))
    assert (read["P8"].value, read["P8"].sampled_at) == (40.325, (20.0, 7.0, 3.0))


def test_a_point_between_nodes_reads_the_nearest_and_says_where(tmp_path):
    (sample,) = _read(_case(tmp_path), {"P9": (10.0, 3.5, 1.5)}).values()
    rows = [tuple(map(float, line.split())) for line in FIXTURE.read_text().splitlines()[1:]]
    nearest = min(rows, key=lambda row: math.dist(row[:3], (10.0, 3.5, 1.5)))
    assert sample.sampled_at == nearest[:3] != (10.0, 3.5, 1.5)
    assert sample.value == nearest[3]


def test_never_activated_passes_through_as_the_sentinel(tmp_path):
    case = _case(tmp_path, "2\n0.000000 0.000000 0.000000 0.955000\n1.000000 0.000000 0.000000 -1.000000\n")
    assert _read(case, {"far": (1.0, 0.0, 0.0)})["far"].value == -1.0
    assert -1.0 in NearestNodeReader.sentinels


def test_a_count_line_that_disagrees_with_the_rows_is_refused(tmp_path):
    case = _case(tmp_path, "3\n0.000000 0.000000 0.000000 0.955000\n")
    with pytest.raises(ValueError, match="declares 3"):
        _read(case, {"P1": (0.0, 0.0, 0.0)})


def test_a_file_without_a_count_line_is_refused(tmp_path):
    case = _case(tmp_path, "0.000000 0.000000 0.000000 0.955000\n")
    with pytest.raises(ValueError, match="count"):
        _read(case, {"P1": (0.0, 0.0, 0.0)})


def test_the_plugin_reads_only_its_own_format():
    from omnidriver.torchcor.plugin import TorchCorPlugin

    assert isinstance(TorchCorPlugin().get_artifact_value_reader(ACTIVATION_FORMAT), NearestNodeReader)
    assert TorchCorPlugin().get_artifact_value_reader("opencarp_lat_per_node") is None
