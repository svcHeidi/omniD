"""The records over ``eikonal1DCableCV``, ``ionicHeterogeneity`` and ``rotorInstability``, against the native
cases committed verbatim as fixtures (their ``Allrun``, ``constant/`` and ``system/``): each record's steps run
what ``Allrun`` runs, and each plans clean. Nothing runs a solver."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.records import TUTORIAL_RECORDS
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime import record_execution
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError

TUTORIALS = Path(__file__).resolve().parent / "fixtures" / "tutorials"
PROTOCOLS = TUTORIALS / "electrophysiologyProtocols"

#: The steps of the parallel branch, which a record leaves to ``--parallel``.
_PARALLEL_COMMANDS = frozenset({"decomposePar", "reconstructPar", "redistributeRestartState"})
NEW_RECORDS = ("cable1DEikonalCV", "ionicHeterogeneity", "rotorInstability")


def _allrun_commands(case: Path) -> list[tuple[str, ...]]:
    """What ``Allrun`` runs in serial: its ``runApplication`` lines, minus the parallel branch."""
    commands = []
    for line in (case / "Allrun").read_text().splitlines():
        words = shlex.split(line.strip())
        if words[:1] != ["runApplication"]:
            continue
        command = tuple(word for word in words[1:] if word != "-o")
        if command[0] not in _PARALLEL_COMMANDS:
            commands.append(command)
    return commands


def _step_commands(record_name: str, *, among: tuple[str, ...] | None = None) -> list[tuple[str, ...]]:
    steps = TUTORIAL_RECORDS[record_name].workflow_steps
    return [step.command for step in steps if among is None or step.step_id in among]


def _plan(record: str, tmp_path, study: dict | None = None):
    return strict_plan(
        record, overrides={"cases_root": str(TUTORIALS), **(study or {})},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("cardiacfoam"),
    )


def _foam_value(case: Path, document: str, key: str) -> str:
    match = re.search(rf"^\s*{key}\s+(\S+);", (case / document).read_text(), re.MULTILINE)
    assert match is not None, f"{case / document} has no {key}"
    return match.group(1)


@pytest.mark.parametrize("record, case", [
    ("cable1DEikonalCV", PROTOCOLS / "cableProtocol" / "eikonal1DCableCV"),
    ("ionicHeterogeneity", PROTOCOLS / "ionicHeterogeneity"),
    ("rotorInstability", PROTOCOLS / "rotorInstability"),
])
def test_a_records_steps_run_what_the_native_allrun_runs(record, case):
    native = _allrun_commands(case)
    assert _step_commands(record) == native


@pytest.mark.parametrize("record", NEW_RECORDS)
def test_a_new_record_plans_clean(record, tmp_path):
    report = _plan(record, tmp_path)
    assert report.status == "ok", [d.message for d in report.plugin_diagnostics if d.level == "error"]


def test_the_eikonal_cables_dx_axis_resizes_the_cables_one_hex_block():
    case = PROTOCOLS / "cableProtocol" / "eikonal1DCableCV"
    assert re.search(r"hex \(0 1 2 3 4 5 6 7\) \(400 1 1\)", (case / "system" / "blockMeshDict").read_text())
    record = TUTORIAL_RECORDS["cable1DEikonalCV"]
    preview = record_execution.preview_record_case(
        record, cases_root=TUTORIALS, study_by_source={"base": {"dx": 0.0001}},
        driver_context=load_plugin_context("cardiacfoam"),
    )
    [patch] = preview["patches"]
    assert (patch["document"], tuple(patch["value"])) == ("system/blockMeshDict", (200, 1, 1))


def test_ionic_heterogeneity_has_nothing_to_split_across_processes():
    with pytest.raises(TutorialRecordError, match="'ionicHeterogeneity' is serial only"):
        record_execution.preview_record_case(
            TUTORIAL_RECORDS["ionicHeterogeneity"], cases_root=TUTORIALS, study_by_source={"base": {"parallel": True}},
            driver_context=load_plugin_context("cardiacfoam"),
        )


def test_ionic_heterogeneity_consumes_what_the_probe_reads():
    [step] = TUTORIAL_RECORDS["ionicHeterogeneity"].workflow_steps
    assert {"constant/electroProperties", "constant/ionicHeterogeneityProbe"} <= set(step.consumes)
    assert _foam_value(PROTOCOLS / "ionicHeterogeneity", "system/controlDict", "application") == "ionicHeterogeneityProbe"
