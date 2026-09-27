"""cardiacFOAM's activation-time probe reader, over files a real run wrote.

``fixtures/niederer2011_probes/`` holds ``postProcessing/Niedererpoints/0/
activationTime``, a verbatim copy of what ``niederer2011``'s ``samplePoints``
step writes at dx 0.5 mm, ``endTime`` 0.015 s (docs/solver-learning/
cardiacfoam.md, section Q, Q1), plus ``system/Niedererpoints`` declaring
``interpolationScheme cellPoint`` (Q9, 2026-09-27), the scheme this reader
requires.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.activation_probes import ACTIVATION_PROBES_FORMAT, ActivationProbeReader
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.records.niederer_2011 import RECORD
from omnidriver.core.quantities import ReadRequest, check_reader, converted, read_quantities
from omnidriver.core.runtime.models import DataArtifact

FIXTURE = Path(__file__).parent / "fixtures" / "niederer2011_probes"
POINTS = "postProcessing/Niedererpoints/0/activationTime"
NAMES = tuple(str(k) for k in range(9))
#: Q1: the header's configured locations, i.e. the native system/Niedererpoints.
HEADER = ((0.0, 0.0, 0.007), (0.0, 0.0, 0.0), (0.019999, 0.0, 0.007), (0.019999, 0.0, 0.0),
          (0.0, 0.003, 0.007), (0.0, 0.003, 0.0), (0.019999, 0.003, 0.007), (0.019999, 0.003, 0.0),
          (0.01, 0.0015, 0.0035))


@pytest.fixture
def case_root(tmp_path: Path) -> Path:
    root = tmp_path / "case"
    shutil.copytree(FIXTURE, root)
    return root


def _artifact() -> DataArtifact:
    return DataArtifact(artifact_id="record.samplePoints.0", path_pattern=POINTS, format=ACTIVATION_PROBES_FORMAT)


def _read(case_root: Path, names=NAMES):
    return {q.name: q for q in read_quantities(ActivationProbeReader(), case_root, _artifact(), ReadRequest(names=names))}


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def test_the_plugin_reads_its_probe_format_and_nothing_else():
    plugin = CardiacFoamPlugin()
    reader = plugin.get_artifact_value_reader(ACTIVATION_PROBES_FORMAT)
    assert isinstance(reader, ActivationProbeReader)
    assert plugin.get_artifact_value_reader("file") is None
    check_reader(reader, artifact_format=ACTIVATION_PROBES_FORMAT)
    assert (reader.value_unit, reader.sentinels, reader.sampling_rule, reader.coordinate_unit, reader.takes_points) == (
        "s", frozenset({-1.0}), "point", "m", False)


def test_the_record_names_the_probe_format_and_has_no_cell_centre_steps():
    steps = {step.step_id: step for step in RECORD.workflow_steps}
    assert steps["samplePoints"].produced_format(POINTS) == ACTIVATION_PROBES_FORMAT
    assert "writeCellCentres" not in steps
    assert "samplePointCentres" not in steps
    for variant in RECORD.workflow_variants.values():
        assert "writeCellCentres" not in variant
        assert "samplePointCentres" not in variant


def test_nine_probes_are_read_in_seconds_at_the_probe_location(case_root):
    quantities = _read(case_root)
    assert list(quantities) == list(NAMES)
    for k, name in enumerate(NAMES):
        q = quantities[name]
        assert (q.unit, q.sampling_rule, q.sampled_at_unit, q.source_artifact) == ("s", "point", "m", POINTS)
        assert q.sampled_at == HEADER[k]    # cellPoint: offset 0
    assert (quantities["0"].status, quantities["0"].value) == ("evaluated", 0.00119496)


def test_minus_one_second_is_not_reached_never_minus_1000_ms(case_root):
    quantities = _read(case_root)
    for name in NAMES[1:]:
        assert (quantities[name].status, quantities[name].value) == ("not_reached", None)
        in_ms = converted(quantities[name], "ms")
        assert (in_ms.status, in_ms.value, in_ms.unit) == ("not_reached", None, "ms")
    assert converted(quantities["0"], "ms").value == pytest.approx(1.19496)


def test_a_name_that_is_no_probe_is_refused_by_name(case_root):
    with pytest.raises(ValueError, match=r"'P1'.*probes \['0'"):
        ActivationProbeReader().read(case_root, _artifact(), ReadRequest(names=("P1",)))


def test_a_probe_openfoam_did_not_find_is_refused_by_name(case_root):
    _edit(case_root / POINTS, "# Probe 3 (0.019999 0 0)", "# Probe 3 (0.019999 0 0)  # Not Found")
    with pytest.raises(ValueError, match="probe '3'.*Not Found"):
        ActivationProbeReader().read(case_root, _artifact(), ReadRequest(names=("3",)))


def test_a_cell_scheme_probe_is_refused_by_name(case_root):
    """OpenFOAM's own default (no ``interpolationScheme``, or any value
    other than ``cellPoint``) is refused: a ``cell`` probe's location is the
    containing cell's centre, which this reader does not report."""
    _edit(case_root / "system" / "Niedererpoints", "interpolationScheme cellPoint;\n", "")
    with pytest.raises(ValueError, match="interpolationScheme 'cell'.*cellPoint.*cell's centre"):
        ActivationProbeReader().read(case_root, _artifact(), ReadRequest(names=("0",)))
