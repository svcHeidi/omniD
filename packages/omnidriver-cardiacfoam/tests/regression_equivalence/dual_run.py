"""Drive each regression case through the agent's own run path and require its
outputs to match the committed reference within the case's tolerances. Solver
work is gated by :func:`solver_available`; the pure helpers run anywhere.
"""
from __future__ import annotations

import functools
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from regression_equivalence.tutorials_tree import tutorials_root
from regression_equivalence.registry import RegressionCase


@dataclass(frozen=True)
class ReferencePoint:
    data_file: str
    time: float
    variable: str
    expected: float
    tolerance: float


def parse_columnar_reference(text: str) -> list[ReferencePoint]:
    """Parse `file time variable expected tolerance` rows; [] for any other layout."""
    points: list[ReferencePoint] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split()
        if len(cols) < 5:
            return []
        data_file, time, variable, expected, tolerance = cols[:5]
        try:
            points.append(
                ReferencePoint(
                    data_file, float(time), variable,
                    float(expected), float(tolerance),
                )
            )
        except ValueError:
            return []
    return points


def read_series_value(
    text: str, target_time: float, variable: str, *, time_atol: float = 1e-9
) -> float | None:
    """Mirrors the awk extractor in the cases' regressionTest.sh (header row, time in column 1)."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    header = lines[0].split()
    try:
        col = header.index(variable)
    except ValueError:
        return None
    best_diff = float("inf")
    best_val: float | None = None
    for row in lines[1:]:
        cells = row.split()
        if len(cells) <= col:
            continue
        try:
            t = float(cells[0])
            v = float(cells[col])
        except ValueError:
            continue
        diff = abs(t - target_time)
        if diff < best_diff:
            best_diff = diff
            best_val = v
    if best_val is None or best_diff > time_atol:
        return None
    return best_val


def values_agree(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance


@dataclass(frozen=True)
class ManufacturedReferencePoint:
    kind: str
    key: str
    metric: str
    expected: float
    tolerance: float


def parse_manufactured_reference(text: str) -> list[ManufacturedReferencePoint]:
    points = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split()
        if len(cols) < 5:
            return []
        kind, key, metric, expected, tolerance = cols[:5]
        if kind not in ("summary", "error", "pseudoECG"):
            return []
        try:
            points.append(
                ManufacturedReferencePoint(
                    kind, key, metric, float(expected), float(tolerance)
                )
            )
        except ValueError:
            return []
    return points


def find_manufactured_error_file(case_path: Path) -> Path | None:
    for f in case_path.glob("postProcessing/*.dat"):
        text = f.read_text(errors="ignore").lower()
        if "manufactured solution error summary" in text.replace("-", " ") or "manufactured activation time summary" in text.replace("-", " "):
            return f
    for f in case_path.glob("processor*/postProcessing/*.dat"):
        text = f.read_text(errors="ignore").lower()
        if "manufactured solution error summary" in text.replace("-", " ") or "manufactured activation time summary" in text.replace("-", " "):
            return f
    return None


def extract_summary_value(text: str, key: str) -> float | None:
    for line in text.splitlines():
        if key == "cells" and "Number of cells" in line:
            return float(line.split("=")[1].strip())
        if key == "cellsPerDirection" and line.startswith("# cellsPerDirection "):
            return float(line.split()[2])
        if key == "finalTime" and "Final simulation time" in line:
            return float(line.split("=")[1].strip())
        if key == "finalTime" and line.startswith("# time "):
            return float(line.split()[2])
    return None


def extract_error_metric(text: str, key: str, metric: str) -> float | None:
    col = {"L1": 1, "L2": 2, "Linf": 3}.get(metric)
    if col is None: return None
    for line in text.splitlines():
        parts = line.split()
        if not parts: continue
        if parts[0] == key and len(parts) > col:
            try:
                return float(parts[col])
            except ValueError:
                pass
    return None


def find_pseudo_ecg_file(case_path: Path) -> Path | None:
    for name in ["pseudoECG.dat", "eikonalECG.dat"]:
        for p in [case_path / "postProcessing" / name] + list(case_path.glob(f"processor*/postProcessing/{name}")):
            if p.exists(): return p
    return None


def extract_pseudo_ecg_value(text: str, key: str) -> float | None:
    lines = text.splitlines()
    if not lines: return None
    header = lines[0].split()
    col = -1
    for i, h in enumerate(header):
        if h == key or h == f"numeric_{key}":
            col = i - 1 if header[0] == "#" else i
            break
    if col < 0: return None
    
    for line in reversed(lines):
        if line.startswith("#"): continue
        parts = line.split()
        if len(parts) > col:
            try:
                return float(parts[col])
            except ValueError:
                pass
    return None


def _check_manufactured_reference(case_path: Path, points: list[ManufacturedReferencePoint]) -> tuple[bool, str]:
    problems = []
    checks = 0
    error_file = find_manufactured_error_file(case_path)
    error_text = error_file.read_text(errors="ignore") if error_file else ""
    
    ecg_file = find_pseudo_ecg_file(case_path)
    ecg_text = ecg_file.read_text(errors="ignore") if ecg_file else ""
    
    for p in points:
        checks += 1
        val = None
        if p.kind == "summary":
            if error_text: val = extract_summary_value(error_text, p.key)
        elif p.kind == "error":
            if error_text: val = extract_error_metric(error_text, p.key, p.metric)
        elif p.kind == "pseudoECG":
            if ecg_text: val = extract_pseudo_ecg_value(ecg_text, p.key)
            
        if val is None:
            problems.append(f"{p.kind} {p.key} {p.metric}: missing in agent output")
        elif not values_agree(val, p.expected, p.tolerance):
            problems.append(f"{p.kind} {p.key} {p.metric}: agent={val} expected={p.expected} tol={p.tolerance}")
            
    if problems:
        return False, "\n".join(problems)
    return True, f"{checks} reference points reproduced within tolerance"


# Write times carry a small offset from the requested grid (1.5000010, not
# 1.5); this exceeds that offset but stays below the write interval.
TIME_MATCH_ATOL = 1e-2


@dataclass(frozen=True)
class ReproResult:
    case_dir: str
    driver: str
    # "reproduced": agent output matches committed reference within tolerance.
    # "mismatch":   agent ran but some reference point is off/missing.
    # "run_failed": the agent run itself returned non-zero.
    # "unsupported_ref": reference format not parsed by this harness.
    # "skipped":    no solver, or case not agent-addressable.
    status: str
    detail: str


def solver_available() -> bool:
    return bool(shutil.which("cardiacFoam")) and bool(os.environ.get("WM_PROJECT_DIR"))


def _stage_tutorials_root(case: RegressionCase) -> tuple[Path, Path]:
    """Copy the case into a throwaway tutorials root; return (root, case_path)."""
    src = tutorials_root() / case.case_dir
    root = Path(tempfile.mkdtemp(prefix="regressioneq_")) / "tutorials"
    case_path = root / case.case_dir
    case_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, case_path)
    for stale in ("postProcessing", "workflow_state.json", "workflow_logs"):
        p = case_path / stale
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    for log_file in case_path.glob("log.*"):
        log_file.unlink(missing_ok=True)
    return root, case_path


def _drive_agent(case: RegressionCase, driver: str, cases_root: Path) -> subprocess.CompletedProcess:
    """``--plugin`` is explicit: with several adapters installed the child has no default."""
    if driver == "strict":
        entry_args = ["--entry", case.entry_name]
    else:
        entry_args = ["--entry", case.case_dir, "--entry-kind", "case_folder"]
    argv = [
        sys.executable, "-m", "omnidriver", "run", "--strict",
        "--plugin", "cardiacfoam",
        *entry_args, "--cases-root", str(cases_root),
    ]
    return subprocess.run(argv, capture_output=True, text=True)


def _run_regression_script(case: RegressionCase, case_path: Path) -> subprocess.CompletedProcess:
    script_path = case_path / case.regression_script
    return subprocess.run(
        ["/bin/bash", str(script_path)],
        cwd=case_path,
        capture_output=True,
        text=True,
    )


def _tail(text: str, *, limit: int = 1500) -> str:
    return text[-limit:] if len(text) > limit else text


_PROTOCOL_FILENAME = "equivalence_protocol.yaml"


def _omnidriver_checkout_root() -> Path:
    """Not ``repo_root_default()``: that can return an enclosing cardiacFoam monorepo root."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / _PROTOCOL_FILENAME).is_file() and (parent / "packages").is_dir():
            return parent
    raise FileNotFoundError(
        f"no ancestor of {here} holds {_PROTOCOL_FILENAME} beside packages/; "
        "check_protocol needs an omniD checkout"
    )


@functools.cache
def _protocol_module() -> ModuleType:
    """Core's ``tests/equivalence/protocol.py``, loaded by path: core's tests tree is
    not importable here, and adding it to the path would shadow this tree's conftest."""
    path = _omnidriver_checkout_root() / "packages" / "omnidriver" / "tests" / "equivalence" / "protocol.py"
    name = "regression_equivalence._core_equivalence_protocol"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the equivalence protocol module from {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before executing: dataclasses resolves string annotations
    # (``from __future__ import annotations``) through sys.modules.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_equivalence_protocol():
    return _protocol_module().load_protocol(_omnidriver_checkout_root() / _PROTOCOL_FILENAME)


def check_protocol(case_dir: str, case_path: Path) -> tuple[bool, str]:
    """Returns (ok, detail); raises NotImplementedError when the protocol has no rows for the case."""
    protocol = load_equivalence_protocol()

    rows = [r for r in protocol.rows if r.case_dir == case_dir]
    metric_rows = [r for r in protocol.metric_rows if r.case_dir == case_dir]
    
    if not rows and not metric_rows:
        raise NotImplementedError(f"no rules found in equivalence_protocol.yaml for {case_dir}")

    problems: list[str] = []
    checks = 0

    if rows:
        for p in rows:
            checks += 1
            f = case_path / p.data_file
            val = (
                read_series_value(f.read_text(errors="ignore"), p.time, p.variable, time_atol=TIME_MATCH_ATOL)
                if f.exists() else None
            )
            if val is None:
                problems.append(f"{p.data_file} {p.variable}@{p.time}: missing in agent output")
            elif not values_agree(val, p.expected, p.tolerance):
                problems.append(
                    f"{p.data_file} {p.variable}@{p.time}: agent={val} "
                    f"expected={p.expected} tol={p.tolerance}"
                )

    if metric_rows:
        error_file = find_manufactured_error_file(case_path)
        error_text = error_file.read_text(errors="ignore") if error_file else ""
        ecg_file = find_pseudo_ecg_file(case_path)
        ecg_text = ecg_file.read_text(errors="ignore") if ecg_file else ""
        
        for p in metric_rows:
            checks += 1
            val = None
            if p.kind == "summary":
                if error_text: val = extract_summary_value(error_text, p.key)
            elif p.kind == "error":
                if error_text: val = extract_error_metric(error_text, p.key, p.metric)
            elif p.kind == "pseudoECG":
                if ecg_text: val = extract_pseudo_ecg_value(ecg_text, p.key)
                
            if val is None:
                problems.append(f"{p.kind} {p.key} {p.metric}: missing in agent output")
            elif not values_agree(val, p.expected, p.tolerance):
                problems.append(f"{p.kind} {p.key} {p.metric}: agent={val} expected={p.expected} tol={p.tolerance}")

    if problems:
        return False, "\n".join(problems)
    return True, f"{checks} reference points reproduced against YAML protocol"


def verify_reproduction(case: RegressionCase, *, driver: str) -> ReproResult:
    if not solver_available():
        return ReproResult(
            case.case_dir, driver, "skipped",
            "cardiacFoam not built/sourced (WM_PROJECT_DIR unset or binary absent)",
        )
    if driver == "generic" and not case.generic_addressable:
        return ReproResult(
            case.case_dir, driver, "skipped",
            "case layout not addressable by agent discovery",
        )

    root, case_path = _stage_tutorials_root(case)
    try:
        regression_script = case_path / case.regression_script
        if driver == "generic" and regression_script.is_file():
            proc = _run_regression_script(case, case_path)
            output = "\n".join(
                part for part in (
                    _tail(proc.stdout.strip()),
                    _tail(proc.stderr.strip()),
                )
                if part
            )
            if proc.returncode == 77:
                return ReproResult(
                    case.case_dir,
                    driver,
                    "skipped",
                    f"committed regression script returned expected skip rc=77\n{output}",
                )
            if proc.returncode != 0:
                return ReproResult(
                    case.case_dir,
                    driver,
                    "mismatch",
                    f"committed regression script rc={proc.returncode}; output tail:\n{output}",
                )
            return ReproResult(
                case.case_dir,
                driver,
                "reproduced",
                "committed regression script passed",
            )
        else:
            proc = _drive_agent(case, driver, root)
        if proc.returncode != 0:
            output = "\n".join(
                part for part in (
                    _tail(proc.stdout.strip()),
                    _tail(proc.stderr.strip()),
                )
                if part
            )
            return ReproResult(
                case.case_dir, driver, "run_failed",
                f"agent run rc={proc.returncode}; output tail:\n{output}",
            )
        try:
            ok, detail = check_protocol(case.case_dir, case_path)
        except NotImplementedError as exc:
            return ReproResult(
                case.case_dir, driver, "unsupported_ref",
                f"agent run ok, but {exc} (YAML missing case)",
            )
        if not ok:
            print(f"FAILED {case.case_dir} via {driver}:\n{detail}")
        return ReproResult(
            case.case_dir, driver, "reproduced" if ok else "mismatch", detail
        )
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)
