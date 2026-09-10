"""Run an explicitly selected driver/checker pair in a disposable fixture."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from selected_cardiacfoam_fixture import (
    FixtureInputError,
    SelectedRuntime,
    load_case_input_manifest,
    materialize_case_inputs,
)


@dataclass(frozen=True)
class IntegrationCommands:
    driver: tuple[str, ...]
    solver_checker: tuple[str, ...]
    timeout_s: int


@dataclass(frozen=True)
class CommandEvidence:
    command: tuple[str, ...]
    returncode: int | None
    timed_out: bool
    log_path: str
    tail: str


@dataclass(frozen=True)
class IntegrationEvidence:
    stage_root: Path
    case_root: Path
    input_digest: str
    driver: CommandEvidence
    solver_checker: CommandEvidence
    evidence_path: Path


def load_integration_commands(runtime: SelectedRuntime) -> IntegrationCommands:
    """Read the manifest's explicit driver and solver-owned checker commands."""
    try:
        payload: dict[str, Any] = json.loads(runtime.case_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureInputError(f"Invalid case input manifest {runtime.case_manifest}: {exc}") from exc
    integration = payload.get("integration")
    if not isinstance(integration, dict):
        raise FixtureInputError("Case input manifest requires an integration object for T7")
    driver = _command(integration.get("driver_command"), "integration.driver_command")
    checker = _command(
        integration.get("solver_checker_command"),
        "integration.solver_checker_command",
    )
    timeout_s = integration.get("timeout_s")
    if type(timeout_s) is not int or timeout_s < 1 or timeout_s > 3600:
        raise FixtureInputError("integration.timeout_s must be an integer from 1 to 3600")
    return IntegrationCommands(driver=driver, solver_checker=checker, timeout_s=timeout_s)


def run_selected_integration(
    runtime: SelectedRuntime, commands: IntegrationCommands
) -> IntegrationEvidence:
    """Stage inputs, invoke driverFOAM, then invoke the solver's own checker.

    This is a test harness boundary, not a second process runner: retries,
    transaction policy, and solver timeout semantics remain in the driver
    command/RunDocument.  The outer timeout protects the test host only.
    """
    staged = materialize_case_inputs(runtime, load_case_input_manifest(runtime))
    case_root = staged.root / "case"
    if not case_root.is_dir():
        raise FixtureInputError("Selected case inputs must materialize below case/")
    driver = _run_command(
        _render(commands.driver, staged.root, runtime),
        cwd=case_root,
        log_name="driver-command.log",
        timeout_s=commands.timeout_s,
    )
    checker = _run_command(
        _render(commands.solver_checker, staged.root, runtime),
        cwd=case_root,
        log_name="solver-checker.log",
        timeout_s=commands.timeout_s,
    )
    evidence_path = staged.root / "integration-evidence.json"
    payload = {
        "schema_version": 1,
        "stage_root": str(staged.root),
        "case_root": str(case_root),
        "input_digest": staged.input_digest,
        "driver": asdict(driver),
        "solver_checker": asdict(checker),
    }
    evidence_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return IntegrationEvidence(
        stage_root=staged.root,
        case_root=case_root,
        input_digest=staged.input_digest,
        driver=driver,
        solver_checker=checker,
        evidence_path=evidence_path,
    )


def _command(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise FixtureInputError(f"{name} must be a non-empty list of command arguments")
    return tuple(value)


def _render(
    command: tuple[str, ...], stage_root: Path, runtime: SelectedRuntime
) -> tuple[str, ...]:
    values = {
        "{stage_root}": str(stage_root),
        "{python}": sys.executable,
        "{openfoam_bashrc}": str(runtime.openfoam_bashrc),
    }
    rendered = []
    for argument in command:
        for token, replacement in values.items():
            argument = argument.replace(token, replacement)
        if "{" in argument or "}" in argument:
            raise FixtureInputError(f"Unsupported command placeholder in {argument!r}")
        rendered.append(argument)
    return tuple(rendered)


def _run_command(
    command: tuple[str, ...], *, cwd: Path, log_name: str, timeout_s: int
) -> CommandEvidence:
    log_path = cwd / log_name
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            try:
                returncode = process.wait(timeout=timeout_s)
                timed_out = False
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
                returncode = process.returncode
                timed_out = True
    except OSError as exc:
        log_path.write_text(f"{type(exc).__name__}: {exc}\n")
        returncode = None
        timed_out = False
    return CommandEvidence(
        command=command,
        returncode=returncode,
        timed_out=timed_out,
        log_path=str(log_path),
        tail=_tail(log_path),
    )


def _tail(path: Path, limit: int = 16_384) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - limit))
        return handle.read().decode(errors="replace")
