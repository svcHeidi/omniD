"""The records over ``purkinjeRestitution2D``, one per ``Allrun`` word, against the native case committed
verbatim as a fixture (its ``Allrun``, ``constant/`` and ``system/``): each record's steps run what ``Allrun``
runs, plans clean and stages its variant's dictionaries under the names the solver reads. Nothing runs a solver."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.records import TUTORIAL_RECORDS
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan

TUTORIALS = Path(__file__).resolve().parent / "fixtures" / "tutorials"
PURKINJE_2D = TUTORIALS / "electrophysiologyProtocols" / "purkinjeRestitution2D"

#: The steps of the parallel branch, which a record leaves to ``--parallel``.
_PARALLEL_COMMANDS = frozenset({"decomposePar", "reconstructPar", "redistributeRestartState"})
PURKINJE_RECORDS = {
    "antegrade": "purkinjeRestitution2DAntegrade",
    "retrograde": "purkinjeRestitution2DRetrograde",
    "monodomain": "purkinjeRestitution2DMonodomain",
}


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


def _plan(record: str, tmp_path, study: dict | None = None):
    return strict_plan(
        record, overrides={"cases_root": str(TUTORIALS), **(study or {})},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("cardiacfoam"),
    )


def _step_commands(record_name: str, *, among: tuple[str, ...]) -> list[tuple[str, ...]]:
    steps = TUTORIAL_RECORDS[record_name].workflow_steps
    return [step.command for step in steps if step.step_id in among]


@pytest.mark.parametrize("variant, record", sorted(PURKINJE_RECORDS.items()))
def test_a_purkinje_variant_runs_the_mesh_and_solve_allrun_runs(variant, record):
    assert _allrun_commands(PURKINJE_2D) == [("blockMesh",), ("cardiacFoam",)]
    assert _step_commands(record, among=("mesh", "solve")) == [("blockMesh",), ("cardiacFoam",)]


def test_the_purkinje_records_are_the_words_allrun_accepts():
    allrun = (PURKINJE_2D / "Allrun").read_text()
    [words] = re.findall(r"^\s*([a-z]+(?:\|[a-z]+)+)\)\s+variant=", allrun, re.MULTILINE)
    assert set(words.split("|")) == set(PURKINJE_RECORDS)


@pytest.mark.parametrize("variant, record", sorted(PURKINJE_RECORDS.items()))
def test_a_purkinje_record_stages_its_variants_dictionaries_under_the_names_the_solver_reads(variant, record, tmp_path):
    case_root = Path(_plan(record, tmp_path).launch["case_root"])
    for document in ("constant/electroProperties", "system/controlDict"):
        assert (case_root / document).read_text() == (PURKINJE_2D / f"{document}.{variant}").read_text()


def test_the_monodomain_variant_alone_can_advance_the_network_without_the_tissue():
    record = TUTORIAL_RECORDS[PURKINJE_RECORDS["monodomain"]]
    assert record.workflow_variants == {"coupled": ("mesh", "solve"), "graphOnly": ("mesh", "solveGraphOnly")}
    assert record.default_variant == "coupled"
    [graph_only] = [step for step in record.workflow_steps if step.step_id == "solveGraphOnly"]
    assert graph_only.command == ("runPurkinjeGraph", "-conductionDomain", "purkinjeNetwork")
    for other in ("antegrade", "retrograde"):
        assert not TUTORIAL_RECORDS[PURKINJE_RECORDS[other]].workflow_variants


def test_the_graph_only_command_names_the_conduction_domain_the_monodomain_dictionary_declares():
    declared = re.findall(
        r"conductionNetworkDomains\s*\{\s*(\w+)", (PURKINJE_2D / "constant" / "electroProperties.monodomain").read_text(),
    )
    assert declared == ["purkinjeNetwork"]


@pytest.mark.parametrize("record", sorted(PURKINJE_RECORDS.values()))
def test_a_purkinje_record_plans_clean(record, tmp_path):
    report = _plan(record, tmp_path)
    assert report.status == "ok", [d.message for d in report.plugin_diagnostics if d.level == "error"]
