"""``purkinjeRestitution2DAntegrade``, ``...Retrograde`` and ``...Monodomain``: one record per ``Allrun`` word.
Native case: ``electrophysiologyProtocols/purkinjeRestitution2D``. ``Allrun`` links one ``electroProperties.<word>`` and
one ``controlDict.<word>`` to the names the solver reads; each record's input overlays that pair onto them.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import RecordInput, TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .routes import block_mesh_step, redistribute_restart_state_step, solve_step

_NATIVE_CASE = "electrophysiologyProtocols/purkinjeRestitution2D"
_CONTROL_DICT = "system/controlDict"
_PURKINJE_GRAPH = "constant/purkinjeGraph"

#: Written by the network solver of every variant, and by `runPurkinjeGraph`.
_NETWORK_OUTPUTS = ("postProcessing/purkinjeNetwork.dat", "postProcessing/purkinjeNetworkVTK/*")

VARIANT_INPUT_NAME = "variant"

SOLVER_SELECTOR_NAME = "solver"
COUPLED_VARIANT = "coupled"
GRAPH_ONLY_VARIANT = "graphOnly"
_SOLVE_STEP_ID = "solve"
_GRAPH_ONLY_STEP_ID = "solveGraphOnly"


def _variant_input(word: str) -> RecordInput:
    return RecordInput(
        name=VARIANT_INPUT_NAME, native_relpath=_NATIVE_CASE,
        files=((f"{ELECTRO_PROPERTIES}.{word}", ELECTRO_PROPERTIES), (f"{_CONTROL_DICT}.{word}", _CONTROL_DICT)),
    )


def _mesh_and_solve() -> tuple[WorkflowStep, ...]:
    return (
        block_mesh_step(("system/blockMeshDict", _CONTROL_DICT)),
        solve_step((WITH_DEFAULT_VALUES, *_NETWORK_OUTPUTS), consumes=(_PURKINJE_GRAPH,)),
        redistribute_restart_state_step(),
    )


def _variant_record(word: str, name: str) -> TutorialRecord:
    return TutorialRecord(
        name=name, native_case_relpath=_NATIVE_CASE, inputs=(_variant_input(word),),
        workflow_steps=_mesh_and_solve(),
    )


ANTEGRADE_RECORD = _variant_record("antegrade", "purkinjeRestitution2DAntegrade")
RETROGRADE_RECORD = _variant_record("retrograde", "purkinjeRestitution2DRetrograde")

#: The case's README and regression also advance the network alone on the same
#: mesh, with `runPurkinjeGraph` on the one domain the variant declares.
MONODOMAIN_RECORD = TutorialRecord(
    name="purkinjeRestitution2DMonodomain",
    native_case_relpath=_NATIVE_CASE,
    inputs=(_variant_input("monodomain"),),
    workflow_steps=(
        *_mesh_and_solve(),
        WorkflowStep(
            step_id=_GRAPH_ONLY_STEP_ID,
            command=("runPurkinjeGraph", "-conductionDomain", "purkinjeNetwork"),
            consumes=(_CONTROL_DICT, ELECTRO_PROPERTIES, _PURKINJE_GRAPH),
            produces=_NETWORK_OUTPUTS,
        ),
    ),
    workflow_variants={
        COUPLED_VARIANT: ("mesh", _SOLVE_STEP_ID, "redistributeRestartState"),
        GRAPH_ONLY_VARIANT: ("mesh", _GRAPH_ONLY_STEP_ID),
    },
    variant_selector=SOLVER_SELECTOR_NAME,
    default_variant=COUPLED_VARIANT,
)

RECORDS = (ANTEGRADE_RECORD, RETROGRADE_RECORD, MONODOMAIN_RECORD)
