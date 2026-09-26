"""cardiacFOAM's activation-time probe reader, over files a real run wrote.

``fixtures/niederer2011_probes/`` is a verbatim copy of what
``niederer2011``'s ``samplePoints`` and ``samplePointCentres`` steps write at
dx 0.5 mm, ``endTime`` 0.015 s (docs/solver-learning/cardiacfoam.md, section
Q, Q1-Q3). ``test_activation_probes_native.py`` re-runs the record and fails
if either file drifts from the solver's own output. Every refusal below
mutates one fact of that real output; nothing is invented from scratch.
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
CENTRES = tuple(f"postProcessing/Niedererpoints(Cx,Cy,Cz)/0/{c}" for c in ("Cx", "Cy", "Cz"))
NAMES = tuple(str(k) for k in range(9))
#: Q1: the header's configured locations, i.e. the native system/Niedererpoints.
HEADER = ((0.0, 0.0, 0.007), (0.0, 0.0, 0.0), (0.019999, 0.0, 0.007), (0.019999, 0.0, 0.0),
          (0.0, 0.003, 0.007), (0.0, 0.003, 0.0), (0.019999, 0.003, 0.007), (0.019999, 0.003, 0.0),
          (0.01, 0.0015, 0.0035))
#: Q3/Q4: the centres of the cells probes chose (cells 3120, 0, 3159, 39,
#: 3320, 200, 3359, 239, 1539 of the 40 x 6 x 14 mesh).
CENTRE_OF = ((0.00025, 0.00025, 0.00675), (0.00025, 0.00025, 0.00025), (0.01975, 0.00025, 0.00675),
             (0.01975, 0.00025, 0.00025), (0.00025, 0.00275, 0.00675), (0.00025, 0.00275, 0.00025),
             (0.01975, 0.00275, 0.00675), (0.01975, 0.00275, 0.00025), (0.00975, 0.00125, 0.00325))


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
        "s", frozenset({-1.0}), "cell-containing", "m", False)


def test_the_record_names_the_probe_format_and_writes_the_centres_it_reads():
    steps = {step.step_id: step for step in RECORD.workflow_steps}
    assert steps["samplePoints"].produced_format(POINTS) == ACTIVATION_PROBES_FORMAT
    assert steps["writeCellCentres"].command == ("postProcess", "-func", "writeCellCentres", "-latestTime")
    assert steps["samplePointCentres"].command == (
        "postProcess", "-func", "Niedererpoints(Cx,Cy,Cz)", "-latestTime")
    assert tuple(steps["samplePointCentres"].produces) == CENTRES
    assert all(steps["samplePointCentres"].produced_format(path) == "file" for path in CENTRES)
    for variant in RECORD.workflow_variants.values():
        order = list(variant)
        assert order.index("solve") < order.index("writeCellCentres") < order.index("samplePointCentres")


def test_nine_probes_are_read_in_seconds_at_their_containing_cells_centres(case_root):
    quantities = _read(case_root)
    assert list(quantities) == list(NAMES)
    for k, name in enumerate(NAMES):
        q = quantities[name]
        assert (q.unit, q.sampling_rule, q.sampled_at_unit, q.source_artifact) == ("s", "cell-containing", "m", POINTS)
        assert q.sampled_at == CENTRE_OF[k]
        assert q.sampled_at != HEADER[k]    # no probe here sits at a cell centre
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


def test_missing_cell_centres_are_refused_naming_the_step_that_writes_them(case_root):
    (case_root / CENTRES[1]).unlink()
    with pytest.raises(ValueError, match=r"Cy.*writeCellCentres"):
        ActivationProbeReader().read(case_root, _artifact(), ReadRequest(names=("0",)))


def test_cell_centres_probed_elsewhere_are_refused(case_root):
    _edit(case_root / CENTRES[0], "# Probe 8 (0.01 0.0015 0.0035)", "# Probe 8 (0.01 0.0015 0.003)")
    with pytest.raises(ValueError, match="probe 8.*not where"):
        ActivationProbeReader().read(case_root, _artifact(), ReadRequest(names=("0",)))


def test_cell_centres_from_another_time_are_refused(case_root):
    lines = (case_root / CENTRES[2]).read_text().splitlines(keepends=True)
    lines[-1] = lines[-1].replace("0.015 ", "0.01  ", 1)
    (case_root / CENTRES[2]).write_text("".join(lines))
    with pytest.raises(ValueError, match="time 0.01.*0.015"):
        ActivationProbeReader().read(case_root, _artifact(), ReadRequest(names=("0",)))
