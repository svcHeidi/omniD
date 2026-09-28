"""``niedererNVersion`` run serial and parallel gives the same P1-P9
activation times, on the real binary (see docs/solver-learning/opencarp.md).

Both runs are the record unchanged at dx 500 um, dt 50 us, tend 150 ms, so
that all nine points activate. The parallel run asks with ``parallel: 2``:
openCARP has no decomposition dictionary, and no scheduler allocation is
ambient here, so the agent supplies N.

The environment is supplied, never discovered: the caller's PATH must reach
the launcher of the MPI openCARP was built against first (for the owner's
install, openCARP's bundled MPICH, ``/usr/local/lib/opencarp/lib/petsc/bin``),
and on a machine whose host name does not resolve, ``HYDRA_IFACE=lo0``.
Otherwise this test FAILS up front, naming the launcher check's own finding
(``opencarp_mpi_launcher_mismatch``, the diagnostic preflight refuses the plan
with). ``PETSC_OPTIONS=-log_view`` is set for both runs,
so each solve log states the size of the MPI world PETSc ran in.

Tolerance, 1e-5 ms absolute: ten units of the last digit the LAT file prints
(six decimals), a five-thousandth of ``dt``. openCARP's parallel solve
reduces in a different order, so the printed times may differ in that last
digit, not more.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.quantities import ReadRequest, load_point_reference, read_quantities
from omnidriver.opencarp.lat_reader import LatPerNodeReader
from opencarp_native import niederer_run, require_opencarp_mpi_launcher

pytestmark = pytest.mark.native_opencarp

REFERENCE = Path(__file__).resolve().parents[3] / "benchmarks" / "niederer2011.json"
RANKS = 2
TOLERANCE_MS = 1e-5
_MM_TO_UM = 1000.0


def _points() -> dict[str, tuple[float, float, float]]:
    reference = load_point_reference(REFERENCE)
    assert reference.length_unit == "mm"
    return {label: tuple(_MM_TO_UM * c for c in point.coordinates)
            for label, point in reference.points.items() if point.coordinates is not None}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    require_opencarp_mpi_launcher()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PETSC_OPTIONS", "-log_view")
        serial = niederer_run(tmp_path_factory.mktemp("serial"), dx=500.0, tend=150.0)
        parallel = niederer_run(tmp_path_factory.mktemp("parallel"), dx=500.0, tend=150.0,
                                extra={"parallel": RANKS})
    return serial, parallel


def _quantities(run, points):
    return {q.name: q for q in read_quantities(LatPerNodeReader(), run.case_root, run.lat_artifact,
                                               ReadRequest(names=tuple(points), points=points))}


def _document(run) -> dict:
    (path,) = run.output_dir.glob(f"{run.case_id}/run_document.json")
    return json.loads(path.read_text())


def test_serial_and_parallel_give_the_same_activation_times(runs):
    serial, parallel = runs
    points = _points()
    assert sorted(points) == [f"P{k}" for k in range(1, 10)]
    s, p = _quantities(serial, points), _quantities(parallel, points)
    for label in points:
        assert s[label].status == p[label].status == "evaluated", (label, s[label], p[label])
        assert (s[label].sampled_at, s[label].unit) == (p[label].sampled_at, p[label].unit), label
        assert p[label].value == pytest.approx(s[label].value, abs=TOLERANCE_MS), (label, s[label].value, p[label].value)


def test_the_outputs_keep_their_layout_and_location(runs):
    """Same files in the -simID directory, the LAT file one value per node in
    the serial node order, vm.igb the same header."""
    serial, parallel = runs
    out_s, out_p = serial.case_root / "out", parallel.case_root / "out"
    assert sorted(p.name for p in out_s.iterdir()) == sorted(p.name for p in out_p.iterdir())
    lat_s = (serial.case_root / serial.lat_artifact.path_pattern).read_text().split()
    lat_p = (parallel.case_root / parallel.lat_artifact.path_pattern).read_text().split()
    assert len(lat_s) == len(lat_p) == 41 * 15 * 7          # nodes at dx 500
    assert max(abs(float(a) - float(b)) for a, b in zip(lat_s, lat_p)) <= TOLERANCE_MS
    header = lambda path: path.read_bytes()[:1024]          # the igb header block
    assert header(out_s / "vm.igb") == header(out_p / "vm.igb")
    assert (out_s / "vm.igb").stat().st_size == (out_p / "vm.igb").stat().st_size


def test_the_parallel_run_was_one_mpi_world_of_the_requested_size(runs):
    serial, parallel = runs
    document = _document(parallel)
    (solve,) = [step for step in document["workflowDag"]["steps"] if step["id"] == "solve"]
    assert solve["command"] == "mpirun" and solve["args"][:3] == ["-np", str(RANKS), "openCARP"]
    assert document["resolvedEntry"]["parallel"] == {"requested": RANKS, "allocation": None}
    log = (parallel.case_root / "workflow_logs" / "solve.attempt1.stdout.log").read_text()
    assert f"with {RANKS} processors" in log                  # PETSc's own -log_view line
    assert log.count("GIT tag") == 1                          # one world, one header
    serial_log = (serial.case_root / "workflow_logs" / "solve.attempt1.stdout.log").read_text()
    assert "with 1 processor," in serial_log
    assert "parallel" not in _document(serial)["resolvedEntry"]
