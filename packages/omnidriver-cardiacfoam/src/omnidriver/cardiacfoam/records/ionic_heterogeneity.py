"""``ionicHeterogeneity``, the transmural-heterogeneity probe record.
Native case: ``electrophysiologyProtocols/ionicHeterogeneity``; one meshless utility, no ``cardiacFoam`` solve.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES

_PROBE_DICT = "constant/ionicHeterogeneityProbe"
_OUTPUT_DIR = "postProcessing/ionicHeterogeneityProbe"

RECORD = TutorialRecord(
    name="ionicHeterogeneity",
    native_case_relpath="electrophysiologyProtocols/ionicHeterogeneity",
    workflow_steps=(
        WorkflowStep(
            step_id="probe",
            command=("ionicHeterogeneityProbe",),
            consumes=("system/controlDict", ELECTRO_PROPERTIES, _PROBE_DICT),
            produces=tuple(
                f"{_OUTPUT_DIR}/{name}.csv"
                for name in ("Vm_traces", "AP_metrics", "smoothness_report", "APD_envelope_report")
            ),
        ),
    ),
    serial_only=True,
)
