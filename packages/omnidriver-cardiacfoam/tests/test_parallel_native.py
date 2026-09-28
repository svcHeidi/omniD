"""``niederer2011`` run serial and parallel (N=2) gives the same P1-P9 activation
times on the real solver; endTime 0.15 s so all nine points activate (P8 at 0.143 s).
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.activation_probes import ActivationProbeReader
from omnidriver.core.quantities import ReadRequest, read_quantities
from omnidriver.core.runtime.models import data_artifact_from_json
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from cardiacfoam_native import niederer_sweep, require_sourced_openfoam
from omnidriver.cardiacfoam.records import niederer_2011

pytestmark = pytest.mark.native

NAMES = tuple(str(k) for k in range(9))
DX_M = 0.0005
END_TIME_S = 0.15
RANKS = 2
# 1e-4 of deltaT: a decomposed solve differs only at the solver tolerance, and
# probes are written at writePrecision 6, so this requires equal written values.
TOLERANCE_S = 1e-9


def _case(output: Path):
    (case,) = build_sweep_context(output).cases
    document = json.loads((output / case.run_document_path).read_text())
    artifact = next(data_artifact_from_json(raw) for raw in document["expectedArtifacts"]
                    if raw["path_pattern"] == niederer_2011.POINTS_PATH)
    case_root = Path(case.case_root)
    quantities = {q.name: q for q in read_quantities(ActivationProbeReader(), case_root, artifact,
                                                     ReadRequest(names=NAMES))}
    return case_root, document, quantities


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    require_sourced_openfoam("blockMesh", "cardiacFoam", "decomposePar", "reconstructPar", "mpirun")
    serial_dir = tmp_path_factory.mktemp("serial")
    parallel_dir = tmp_path_factory.mktemp("parallel")
    with ThreadPoolExecutor(max_workers=2) as pool:
        serial = pool.submit(niederer_sweep, serial_dir, dx_values=(DX_M,), end_time=END_TIME_S)
        parallel = pool.submit(niederer_sweep, parallel_dir, dx_values=(DX_M,), end_time=END_TIME_S, extra={
            "parallel": True, "system/decomposeParDict:numberOfSubdomains": RANKS,
        })
        return _case(serial.result()), _case(parallel.result())


def test_serial_and_parallel_give_the_same_activation_times(runs):
    (_, _, serial), (_, _, parallel) = runs
    assert list(serial) == list(parallel) == list(NAMES)
    for name in NAMES:
        s, p = serial[name], parallel[name]
        assert s.status == p.status == "evaluated", (name, s, p)
        assert (s.unit, s.sampled_at) == (p.unit, p.sampled_at), name
        assert p.value == pytest.approx(s.value, abs=TOLERANCE_S), (name, s.value, p.value)


def test_the_parallel_run_ran_on_the_decomposed_ranks_and_says_so(runs):
    (serial_root, serial_doc, _), (parallel_root, parallel_doc, _) = runs
    steps = {step["id"]: step for step in parallel_doc["workflowDag"]["steps"]}
    assert (steps["solve"]["command"], steps["solve"]["args"]) == (
        "mpirun", ["-np", str(RANKS), "cardiacFoam", "-parallel"])
    assert steps["solve.decompose"]["consumes"] == ["system/decomposeParDict"]
    assert steps["samplePoints"]["depends_on"] == ["solve.reconstruct"]
    assert parallel_doc["resolvedEntry"]["parallel"]["requested"] is True
    log = (parallel_root / "workflow_logs" / "solve.attempt1.stdout.log").read_text()
    assert f"nProcs : {RANKS}" in log
    assert sorted(p.name for p in parallel_root.glob("processor*")) == [f"processor{k}" for k in range(RANKS)]
    assert "parallel" not in serial_doc["resolvedEntry"]
    assert [step["command"] for step in serial_doc["workflowDag"]["steps"]].count("mpirun") == 0
    assert not list(serial_root.glob("processor*"))
