"""The Niederer campaign's oblique-wall study: ``campaign.sh oblique`` and ``oblique_summarize.py``.

Both tests are reader and wiring tests on small trees written here. The
activation times in them are made up to have known differences; they are not
solver evidence and say nothing about any wall treatment.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _find_campaign() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        campaign = parent / "benchmarks" / "niederer2011" / "campaign"
        if (campaign / "campaign.sh").is_file():
            return campaign
    return None


_CAMPAIGN = _find_campaign()

pytestmark = pytest.mark.skipif(
    _CAMPAIGN is None,
    reason="Requires the omnidriver monorepo checkout (benchmarks/niederer2011/campaign not found from this test file).",
)

_NATIVE_STUDY_DIR = "NiedererEtAl2011verification/setup/studies/obliqueWall"
_PATCH = "constant/electroProperties:monodomainSolverCoeffs."
_CONDUCTIVITY = {"dimensions": [-1, -3, 3, 0, 0, 2, 0], "value": [0.07551194956, 0.05790577195, 0, 0.07551194956, 0, 0.01760617761]}
_GRID = {
    "dx": [0.0005, 0.0005, 0.0005, 0.0002, 0.0002, 0.0002, 0.0001, 0.0001, 0.0001],
    "system/controlDict:deltaT": [5e-05, 1e-05, 5e-06, 5e-05, 1e-05, 5e-06, 5e-05, 1e-05, 5e-06],
    "system/controlDict:endTime": [0.2, 0.2, 0.2, 0.08, 0.08, 0.08, 0.075, 0.075, 0.075],
}


def _native_study() -> dict:
    return {
        "base": {
            "entry": "niederer2011", "cases_root": "tutorials", "mesh": "hex",
            _PATCH + "conductivity": _CONDUCTIVITY,
            _PATCH + "sealedHeartBoundary": True, _PATCH + "sealedWallTrace": "conormal",
            _PATCH + "timeCouplingScheme": "sbdf2", "system/fvSchemes:ddtSchemes.default": "backward",
        },
        "sweep": {"mode": "zip", "independent": _GRID},
    }


@pytest.fixture
def stubbed_campaign(tmp_path):
    """A copy of the campaign scripts whose ``python -m omnidriver`` records its arguments instead of running."""
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    for name in ("campaign.sh", "level_study.py"):
        (campaign / name).write_bytes((_CAMPAIGN / name).read_bytes())
        (campaign / name).chmod(0o755)
    tutorials = tmp_path / "tutorials"
    study_dir = tutorials / _NATIVE_STUDY_DIR
    study_dir.mkdir(parents=True)
    (study_dir / "sweep_hex_oblique_sbdf2_AB.json").write_text(json.dumps(_native_study(), indent=2) + "\n")
    stub = tmp_path / "python"
    stub.write_text(
        '#!/bin/bash\nif [ "$1" = -m ] && [ "$2" = omnidriver ]; then printf "%s\\n" "$@" > "$STUB_ARGS"; exit 0; fi\n'
        f'exec {sys.executable} "$@"\n'
    )
    stub.chmod(0o755)
    (tmp_path / "bashrc").write_text("")
    env = {**os.environ, "PYTHON": str(stub), "OMNIDRIVER_NATIVE_TUTORIALS": str(tutorials),
           "OPENFOAM_BASHRC": str(tmp_path / "bashrc"), "STUB_ARGS": str(tmp_path / "args")}
    return campaign, tutorials, env, tmp_path / "args"


def _oblique(stubbed, *arguments):
    campaign, _, env, _ = stubbed
    return subprocess.run([str(campaign / "campaign.sh"), "oblique", *arguments], env=env, capture_output=True, text=True)


def test_oblique_writes_the_native_rows_and_base_for_one_dx(stubbed_campaign):
    campaign, tutorials, _, args = stubbed_campaign
    result = _oblique(stubbed_campaign, "sbdf2", "AB", "0.2", "8")
    assert result.returncode == 0, result.stderr
    study = json.loads((campaign / "runs/studies/cardiacfoam_obliqueWall_sbdf2_AB_dx0.2_np8.json").read_text())
    native = _native_study()
    # What the level study may add: the absolute cases_root and the rank count.
    expected_base = {**native["base"], "cases_root": str(tutorials.resolve()), "system/decomposeParDict:numberOfSubdomains": 8}
    assert study["base"] == expected_base and list(study["base"]) == list(expected_base)
    assert study["sweep"]["mode"] == "zip"
    assert study["sweep"]["independent"] == {key: values[3:6] for key, values in _GRID.items()}
    arguments = args.read_text().split()
    assert arguments[arguments.index("--output-dir") + 1] == str(campaign / "runs/oblique/sbdf2/AB/dx0.2")
    assert "--parallel" in arguments


def test_oblique_with_a_time_step_runs_that_case_into_its_own_directory(stubbed_campaign):
    campaign, _, _, args = stubbed_campaign
    result = _oblique(stubbed_campaign, "sbdf2", "AB", "0.5", "1", "0.05")
    assert result.returncode == 0, result.stderr
    study = json.loads((campaign / "runs/studies/cardiacfoam_obliqueWall_sbdf2_AB_dx0.5_dt0.05_np1.json").read_text())
    assert study["sweep"]["independent"] == {key: values[:1] for key, values in _GRID.items()}
    arguments = args.read_text().split()
    assert arguments[arguments.index("--output-dir") + 1] == str(campaign / "runs/oblique/sbdf2/AB/dx0.5_dt0.05")
    assert "--parallel" not in arguments


@pytest.mark.parametrize("arguments", [("godunov", "AB", "0.5"), ("sbdf2", "AB", "0.3"), ("sbdf2", "AB")])
def test_oblique_refuses_what_it_has_no_study_or_level_for(stubbed_campaign, arguments):
    result = _oblique(stubbed_campaign, *arguments)
    assert result.returncode == 2 and "campaign.sh:" in result.stderr


# -- the summary ------------------------------------------------------------------------------

_CELLS = 16
_SHAPE = (4, 2, 2)


def _foam_list(values) -> str:
    return f"internalField   nonuniform List<scalar> \n{len(values)}\n(\n" + "\n".join(f"{v:.6f}" for v in values) + "\n)\n;\n"


def _write_case(sweep: Path, case_id: str, *, dt_s: float, status: str, field_s, wall_type: str, base: dict, scheme: str) -> None:
    case = sweep / "cases" / case_id
    for sub in ("system", "constant", "postProcessing/Niedererpoints/0", "postProcessing/Niedererlines/0", "0.2"):
        (case / sub).mkdir(parents=True)
    nx, ny, nz = _SHAPE
    (case / "system/blockMeshDict").write_text(f"blocks\n(\nhex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)\n);\n")
    sealed = "yes" if base[_PATCH + "sealedHeartBoundary"] else "no"
    (case / "constant/electroProperties").write_text(
        "monodomainSolverCoeffs\n{\n"
        f"    sealedHeartBoundary    {sealed};\n    sealedWallTrace    {base[_PATCH + 'sealedWallTrace']};\n"
        f"    conductivity    [-1 -3 3 0 0 2 0] (0.07551194956 0.05790577195 0 0.07551194956 0 0.01760617761);\n"
        f"    timeCouplingScheme    {scheme};\n}}\n")
    ddt = base["system/fvSchemes:ddtSchemes.default"]
    (case / "system/fvSchemes").write_text(f"ddtSchemes\n{{\n    //default         CrankNicolson 1.0;\n    default    {ddt}; // 2nd order\n}}\n")
    (case / "0.2/activationTime").write_text(_foam_list(field_s) + "boundaryField\n{\n}\n")
    (case / "0.2/Vm").write_text(f"{_foam_list([0.0] * _CELLS)}boundaryField\n{{\n    walls\n    {{\n        type            {wall_type};\n    }}\n}}\n")
    probes = [-1.0 if i == 1 else float(field_s[15]) for i in range(9)]  # P2 never reached; the others are the last cell's time
    header = "# Time " + " ".join(str(i) for i in range(9))
    (case / "postProcessing/Niedererpoints/0/activationTime").write_text(f"{header}\n0.2 " + " ".join(map(str, probes)) + "\n")
    (case / "postProcessing/Niedererlines/0/activationTime").write_text("# Time 0 1\n0.2 0.001 " + str(float(field_s[15])) + "\n")
    (case / "workflow_state.json").write_text(json.dumps({"status": status, "steps": [
        {"step_id": "solve", "command": "cardiacFoam", "args": [],
         "started_at": "2026-01-01T00:00:00+00:00", "finished_at": "2026-01-01T00:01:30+00:00"}]}))


def _write_sweep(runs: Path, scheme: str, variant: str, cases: list[dict], base: dict) -> None:
    sweep = runs / scheme / variant / "dx0.5"
    for index, case in enumerate(cases, start=1):
        case_id = f"case_{index:04d}"
        _write_case(sweep, case_id, base=base, scheme=scheme, **case["files"])
    manifest = {"base_study": base, "cases": [
        {"case_id": f"case_{index:04d}", "workflow_state_path": f"cases/case_{index:04d}/workflow_state.json",
         "resolved_axis_values": {"dx": 0.0005, "system/controlDict:deltaT": case["files"]["dt_s"], "system/controlDict:endTime": 0.2}}
        for index, case in enumerate(cases, start=1)]}
    (sweep / "sweep_manifest.json").write_text(json.dumps(manifest))


def _base(seal: bool, trace: str, scheme: str, ddt: str) -> dict:
    return {_PATCH + "conductivity": _CONDUCTIVITY, _PATCH + "sealedHeartBoundary": seal, _PATCH + "sealedWallTrace": trace,
            _PATCH + "timeCouplingScheme": scheme, "system/fvSchemes:ddtSchemes.default": ddt}


def _load_summarizer():
    spec = importlib.util.spec_from_file_location("oblique_summarize", _CAMPAIGN / "oblique_summarize.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_summary_reads_a_partial_tree_and_reports_what_is_missing(tmp_path, capsys):
    runs = tmp_path / "oblique"
    reference = [0.010 + 0.001 * i for i in range(_CELLS)]
    other = [t + 0.0005 * (1 + i / 15) for i, t in enumerate(reference)]  # later by 0.5 to 1 ms, most at the last cell
    unreached = [-1.0 if i == 3 else t for i, t in enumerate(other)]
    zero, conormal = _base(False, "zeroGradient", "godunov", "Euler"), _base(True, "conormal", "godunov", "Euler")
    _write_sweep(runs, "godunov", "0", [
        {"files": dict(dt_s=5e-05, status="completed", field_s=reference, wall_type="zeroGradient")},
        {"files": dict(dt_s=1e-05, status="completed", field_s=reference, wall_type="zeroGradient")}], zero)
    _write_sweep(runs, "godunov", "AB", [
        {"files": dict(dt_s=5e-05, status="completed", field_s=other, wall_type="conormalZeroFlux")},
        # a cell never activates, and the wall is not the conormal one the study asked for
        {"files": dict(dt_s=1e-05, status="completed", field_s=unreached, wall_type="zeroGradient")}], conormal)
    _write_sweep(runs, "godunov", "A", [
        {"files": dict(dt_s=5e-05, status="running", field_s=reference, wall_type="zeroGradient")}],
                 _base(True, "zeroGradient", "godunov", "Euler"))

    assert _load_summarizer().main(["--runs", str(runs)]) == 0
    out = capsys.readouterr().out
    # Probes: P2 never activated is a dash; P8 is the last cell's time in ms, not converted from the sentinel.
    probe_row = next(line for line in out.splitlines() if line.startswith("| godunov | 0 | 0.5 | 0.05 |") and "—" in line)
    assert "25.000" in probe_row and "-1" not in probe_row
    # AB - 0 at dt 0.05: the last cell is 1.000 ms later and carries the maximum.
    difference = next(line for line in out.splitlines() if line.startswith("| godunov | 0.5 | 0.05 | AB − 0 |"))
    cells = [c.strip() for c in difference.split("|")]
    assert cells[5] == "+1.000" and cells[6] == "+1.000" and "yes" in cells
    # The dt 0.01 pair exists over the 15 cells both activated.
    assert any(line.startswith("| godunov | 0.5 | 0.01 | AB − 0 |") for line in out.splitlines())
    assert "| 200 | 175.0 |" in out  # end time and margin of the last cell (25 ms)
    assert "1 cell(s) never activated" in out
    assert "Vm wall patch types ['zeroGradient'], expected conormalZeroFlux" in out
    assert "running: left out of the comparisons" in out
    assert not any(line.startswith("| godunov | 0.5 | 0.05 | A − 0 |") for line in out.splitlines())
    missing = out[out.index("## Missing"):]
    assert "- sbdf2/AB/dx0.1: Δt 0.05, 0.01, 0.005" in missing and "- godunov/0/dx0.5: Δt 0.005" in missing
    assert "- godunov/A/dx0.5: Δt 0.05, 0.01, 0.005" in missing


def test_the_summary_refuses_a_directory_that_does_not_exist(tmp_path, capsys):
    assert _load_summarizer().main(["--runs", str(tmp_path / "none")]) == 1
    assert "is not a directory" in capsys.readouterr().err
