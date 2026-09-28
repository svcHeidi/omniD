"""The activation-probe reader against a real ``niederer2011`` run (hex, dx 0.5 mm, native ``endTime`` 0.015 s): nine quantities in seconds.
Probes sample at their configured locations: the native ``system/Niedererpoints`` sets ``interpolationScheme cellPoint`` (offset 0) and is the drift gate.
Every file read is written by the real solver or by OpenFOAM's ``postProcess`` on a copy (see docs/solver-learning/cardiacfoam.md)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from foamlib import FoamFile

from omnidriver.cardiacfoam.activation_probes import ActivationProbeReader
from omnidriver.core.quantities import ReadRequest, converted, read_quantities
from omnidriver.openfoam.probes import parse_probe_series
from cardiacfoam_native import NIEDERER_2011_RELPATH, native_tutorials_root, niederer_run, require_sourced_openfoam

pytestmark = pytest.mark.native

NAMES = tuple(str(k) for k in range(9))
_TESTS = Path(__file__).resolve().parent
READER_FIXTURE = _TESTS / "fixtures" / "niederer2011_probes"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    return niederer_run(tmp_path_factory.mktemp("niederer2011"), dx=0.0005, end_time=0.015)


@pytest.fixture(scope="module")
def copy(run, tmp_path_factory) -> Path:
    """A copy of the run's case, so ``postProcess`` never writes into the run the other tests read."""
    require_sourced_openfoam("postProcess")
    case_root, _ = run
    target = tmp_path_factory.mktemp("copy") / "case"
    shutil.copytree(case_root, target)
    return target


def _post_process(case: Path, *args: str) -> str:
    proc = subprocess.run(["postProcess", *args, "-latestTime"], cwd=case, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    return proc.stdout + proc.stderr


def _native_probe_locations() -> list[tuple[float, float, float]]:
    raw = FoamFile(native_tutorials_root() / NIEDERER_2011_RELPATH / "system" / "Niedererpoints")["probeLocations"]
    return [tuple(float(v) for v in xyz) for xyz in raw]


def test_the_probe_file_is_read_as_seconds_at_the_probe_location(run):
    case_root, artifact = run
    quantities = {q.name: q for q in read_quantities(ActivationProbeReader(), case_root, artifact, ReadRequest(names=NAMES))}
    assert list(quantities) == list(NAMES)
    header = [at for _, at in parse_probe_series((case_root / artifact.path_pattern).read_text(), source="run").locations]
    assert header == _native_probe_locations()     # the drift gate against the native source
    for k, name in enumerate(NAMES):
        q = quantities[name]
        assert (q.unit, q.sampling_rule, q.sampled_at_unit) == ("s", "point", "m")
        assert q.sampled_at == header[k]    # cellPoint: offset 0
    assert quantities["0"].status == "evaluated"
    assert quantities["0"].value == pytest.approx(0.00119496, abs=5e-9)   # dx 0.5 mm


def test_a_probe_never_reached_is_not_reached(run):
    """At dx 0.5 mm and 0.015 s only probe 0 (inside the stimulus) has activated; the rest hold cardiacFOAM's -1."""
    case_root, artifact = run
    series = parse_probe_series((case_root / artifact.path_pattern).read_text(), source="run")
    assert series.rows[-1][1:] == (-1.0,) * 8
    for q in read_quantities(ActivationProbeReader(), case_root, artifact, ReadRequest(names=NAMES[1:])):
        assert (q.status, q.value) == ("not_reached", None)
        assert (converted(q, "ms").status, converted(q, "ms").value) == ("not_reached", None)


def test_the_probe_parser_refuses_a_vector_field(copy):
    """``C`` is written ad hoc (the record's workflow does not); values are not pinned, since cellPoint blends them."""
    _post_process(copy, "-func", "writeCellCentres")
    _post_process(copy, "-func", "Niedererpoints(C)")
    text = (copy / "postProcessing" / "Niedererpoints(C)" / "0" / "C").read_text()
    with pytest.raises(ValueError, match="vector or tensor"):
        parse_probe_series(text, source="C")


def test_a_probe_outside_the_mesh_is_marked_not_found(copy):
    """``Cx`` is written ad hoc only to have a field to probe; (1, 1, 1) m lies outside the slab."""
    _post_process(copy, "-func", "writeCellCentres")
    _post_process(copy, "-func", "Niedererpoints(Cx,probeLocations=((1 1 1) (0 0 0)))")
    text = (copy / "postProcessing" / "Niedererpoints(Cx,probeLocations=((111)(000)))" / "0" / "Cx").read_text()
    assert parse_probe_series(text, source="Cx").not_found == frozenset({0})


def test_the_committed_fixtures_are_what_the_solver_writes(run):
    """The unit tests' fixture (``test_activation_probes.py``) is this run's own probe output and ``system/Niedererpoints``."""
    case_root, _ = run
    for fixture in sorted(p for p in READER_FIXTURE.rglob("*") if p.is_file()):
        relpath = fixture.relative_to(READER_FIXTURE)
        assert (case_root / relpath).read_text() == fixture.read_text(), relpath
