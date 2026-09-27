"""``cable1DRestitution``, a tutorial record (tutorials-are-pointers plan
§5e, step 5.2). Native case:
``electrophysiologyProtocols/cableProtocol/monodomain1DCableCV``.

Replaces ``cardiacfoam.tutorials.cable_1d_restitution``/``tutorials.defaults
.cable_1d_restitution`` (deleted alongside this record).

**Every write the old ``_plan_case`` made, accounted for:**

| old write | now |
|---|---|
| ``system/blockMeshDict`` hex block rewrite | ``dx`` axis (:mod:`.cable_axes`) |
| ``system/controlDict:deltaT`` | direct study key, in seconds (no unit-converting axis: topic A/B's own convention) |
| ``monodomainSolverCoeffs.conductivity`` | direct study key |
| ``monodomainSolverCoeffs.tissue`` | direct study key (design: "do not derive it") |
| ``monodomainSolverCoeffs.ionicModel`` | direct study key -- unlike ``restitutionCurves``, this tutorial's stimulus amplitude is a fixed geometry constant, not a catalog lookup, so no ``ionicModel`` axis is needed here |
| ``monodomainSolverCoeffs.solutionAlgorithm`` | direct study key; every committed study names ``"implicit"`` (the native default) so it need not be named at all |
| the S1/S2 spatial ``externalStimulus.*`` lists, ``system/controlDict:endTime`` | ``s1s2SpatialProtocol`` axis, below |
| ``conductivity_id``, ``case_dir_name``, ``setup_dir_name``, ``postprocess_strict_artifacts`` | dropped: sweep-engine/staging bookkeeping the old factory needed and the new engine already provides |
| ``electro_property_overrides``/``physics_property_overrides`` | dropped: always ``None`` in every real committed study, so no write ever happened |
| ``parallel`` (old default ``True``) | dropped: owner Q6, serial is the record's default; a study opts into parallel through core's reserved ``parallel`` study name, not a record concern |
| ``.driverfoam_case_id`` sentinel, ``.cardiacfoam_protocol.json`` sidecar | deleted (owner decision (b)): the ``postprocess`` step below runs the native ``Allrun.post`` (which execs ``setup/postProcessing_cableRestitution.py``, rewritten alongside this record). It reads the stimulus SCHEDULE from the case's own ``constant/electroProperties`` (``externalStimulus.stimulusStartTimeList``, already committed there by this axis), and the S1/S2 SPLIT point (``n_s1``/``n_s2``/the DI90 reference, when this run has one) from ``--n-s1``/``--n-s2``/``--reference-repolarization90-s`` -- literal arguments this SAME axis contributes to the step, the same mechanism ``dimension``/``tetNumberCells`` already use for ``-dict``/``-setnumber``. Neither is a Python-side restatement: the times live only in the dictionary, and the split is the study's own resolved value, never re-derived or cached in a second file. ``--case-id`` (naming this run's own output files) is no longer read from a sentinel: the script now defaults it to its own case directory's name |

**The ``s1s2SpatialProtocol`` axis** reproduces the old module's own
arithmetic (module docstring has the full derivation) via the existing
:func:`omnidriver.cardiacfoam.spatial_pacing.generate_spatial_stimulus_lists`,
never a new formula. ``s1_interval_ms`` (1000 ms) is a fixed constant: no
committed study varies it. Two modes, both real (native
``sweep_stewart_di90_boundaries_dt1e-6.json``/``sweep_stewart_true_di90_dt1e-6
.json`` use ``requested_di90_ms``; ``sweep.json`` uses ``s2_interval_ms``):

- ``n_s2 == 0`` (automaticity): no S2 stimulus; ``endTime`` is one S1
  interval past the last S1 stimulus, plus the study's own buffer.
- ``requested_di90_ms`` present: S2 fires at
  ``reference_repolarization90_s + requested_di90_ms/1000``; ``endTime`` is
  that time plus the buffer.
- ``s2_interval_ms`` present: S2 fires ``n_s2`` beats after the last S1, one
  interval apart; ``endTime`` is the last S2 time plus ONE MORE S1 interval
  (propagation margin a 1D cable needs that a 0-D single cell does not) plus
  the buffer.

**Workflow steps, from the native ``Allrun``**::

    runApplication blockMesh
    runApplication cardiacFoam

(the ``parallel`` branch is owner Q6: the OpenFOAM layer's job, not a
record concern). ``postProcess`` is declared as a third step because owner
decision (b) makes post-processing part of this record, unlike
``restitutionCurves``'s conditional, off-by-default ``plotVoltage``.

Produces/consumes observed in a real run:
``docs/solver-learning/cardiacfoam.md``, section "cable".
"""

from __future__ import annotations

from typing import Any

from omnidriver.cardiacfoam.spatial_pacing import (
    generate_spatial_s1_s2_stimulus_lists, generate_spatial_stimulus_lists,
)
from omnidriver.core.tutorial_records import (
    AxisContract, AxisPatch, AxisResult, DefaultArgument, TutorialRecord, WorkflowStep,
)

from .cable_axes import cable_dx_axis
from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES

#: This tutorial always addresses `myocardiumSolver monodomainSolver`'s own
#: `monodomainSolverCoeffs` scope -- never varied (the native case already
#: holds it).
_MONODOMAIN_SOLVER_COEFFS = ("monodomainSolverCoeffs",)

DX_AXIS_NAME = "dx"
S1_S2_PROTOCOL_AXIS_NAME = "s1s2SpatialProtocol"

#: The old module's own literals (stimulus geometry, never varied by any
#: real study): the first 0.5 mm of the cable, a 4 ms/50000 A m^-3 pulse.
_STIMULUS_BOUNDS_MIN = (0.0, 0.0, 0.0)
_STIMULUS_BOUNDS_MAX = (2e-3, 2e-4, 2e-4)
_STIMULUS_DURATION_S = 4e-3
_STIMULUS_INTENSITY = 50000.0

#: Fixed: no committed study varies the S1 pacing interval itself.
_S1_INTERVAL_MS = 1000.0

_CONTROL_DICT_DOCUMENT = "system/controlDict"

#: Each externalStimulus list's own catalogued shape (dict_entries_catalog.py):
#: the record-key validator overrides this before it reaches
#: patches_to_parameters, but a shape this wrong (a string where a sequence
#: belongs) is refused before that ever runs.
_STIMULUS_LIST_VALUE_KINDS = {
    "stimulusStartTimeList": "scalar_list",
    "stimulusDurationList": "scalar_list",
    "stimulusIntensityList": "scalar_list",
    "stimulusLocationMinList": "vector3_list",
    "stimulusLocationMaxList": "vector3_list",
}

#: The postprocess step's command-line contract with the native
#: ``setup/postProcessing_cableRestitution.py`` (owner decision (b)): this
#: axis is the ONLY thing that knows where the S1/S2 split falls in the
#: case's own concatenated ``stimulusStartTimeList``, so it passes that
#: split (plus the DI90 reference, when this case run has one) as literal
#: arguments, the same mechanism ``dimension``/``tetNumberCells`` already
#: use to pass ``-dict``/``-setnumber`` -- not a second Python-side record
#: of the schedule, since the times themselves stay in the case's own
#: dictionary (the script reads them from there).
POSTPROCESS_STEP_ID = "postprocess"
_N_S1_ARG = ("--n-s1",)
_N_S2_ARG = ("--n-s2",)
_REFERENCE_REPOLARIZATION90_ARG = ("--reference-repolarization90-s",)


def _s1_s2_protocol_axis(name: str, *, electro_document: str, scope: tuple[str, ...]) -> AxisContract:
    def resolve(value: Any, staged_case_root) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        protocol = value
        n_s1 = int(protocol["n_s1"])
        n_s2 = int(protocol["n_s2"])
        end_time_buffer_s = float(protocol["end_time_buffer_s"])
        last_s1_time_s = (n_s1 - 1) * (_S1_INTERVAL_MS / 1000.0) if n_s1 else 0.0

        if "requested_di90_ms" in protocol:
            if n_s2 != 1:
                raise ValueError(
                    f"{name!r}: requested_di90_ms scheduling requires n_s2 == 1, got {n_s2!r}"
                )
            reference_repolarization90_s = float(protocol["reference_repolarization90_s"])
            requested_di90_ms = float(protocol["requested_di90_ms"])
            s2_time_s = reference_repolarization90_s + requested_di90_ms / 1000.0
            s1_times_s = [i * (_S1_INTERVAL_MS / 1000.0) for i in range(n_s1)]
            stimulus_lists = generate_spatial_stimulus_lists(
                times_s=s1_times_s + [s2_time_s],
                bounds_min=_STIMULUS_BOUNDS_MIN, bounds_max=_STIMULUS_BOUNDS_MAX,
                duration_s=_STIMULUS_DURATION_S, intensity=_STIMULUS_INTENSITY,
            )
            # No extra S1-interval propagation margin in this mode (unlike
            # coupling_interval, below): the old module's own arithmetic.
            end_time_s = s2_time_s + end_time_buffer_s
        else:
            if n_s2 and "s2_interval_ms" not in protocol:
                raise ValueError(
                    f"{name!r}: n_s2 > 0 requires either 's2_interval_ms' or "
                    "'requested_di90_ms' + 'reference_repolarization90_s'"
                )
            # n_s2 == 0 (automaticity, no premature beat) is simply this
            # emitter's own n_s2=0 case: the S2 loop then contributes nothing.
            s2_interval_ms = float(protocol.get("s2_interval_ms", 0.0))
            stimulus_lists = generate_spatial_s1_s2_stimulus_lists(
                s1_interval_ms=_S1_INTERVAL_MS, n_s1=n_s1,
                s2_interval_ms=s2_interval_ms, n_s2=n_s2,
                bounds_min=_STIMULUS_BOUNDS_MIN, bounds_max=_STIMULUS_BOUNDS_MAX,
                duration_s=_STIMULUS_DURATION_S, intensity=_STIMULUS_INTENSITY,
            )
            # One extra S1 interval past the last stimulus: a 1D cable needs
            # propagation time a 0-D single cell does not (module docstring).
            end_time_s = (
                last_s1_time_s + (_S1_INTERVAL_MS / 1000.0)
                + n_s2 * (s2_interval_ms / 1000.0) + end_time_buffer_s
            )

        stimulus_scope = scope + ("externalStimulus",)
        patches = tuple(
            AxisPatch(
                document=electro_document, key_path=stimulus_scope + (key,),
                value=rendered, value_kind=_STIMULUS_LIST_VALUE_KINDS[key],
            )
            for key, rendered in stimulus_lists.items()
        ) + (
            AxisPatch(document=_CONTROL_DICT_DOCUMENT, key_path=("endTime",), value=end_time_s, value_kind="scalar"),
        )
        postprocess_args = _N_S1_ARG + (str(n_s1),) + _N_S2_ARG + (str(n_s2),)
        if "reference_repolarization90_s" in protocol:
            postprocess_args += _REFERENCE_REPOLARIZATION90_ARG + (
                str(float(protocol["reference_repolarization90_s"])),
            )
        return AxisResult(
            patches=patches,
            command_arguments={POSTPROCESS_STEP_ID: postprocess_args},
        )

    return AxisContract(name=name, value_kind="mapping", resolve=resolve)


AXES = (
    cable_dx_axis(DX_AXIS_NAME),
    _s1_s2_protocol_axis(
        S1_S2_PROTOCOL_AXIS_NAME, electro_document=ELECTRO_PROPERTIES, scope=_MONODOMAIN_SOLVER_COEFFS,
    ),
)

RECORD = TutorialRecord(
    name="cable1DRestitution",
    native_case_relpath="electrophysiologyProtocols/cableProtocol/monodomain1DCableCV",
    axes=AXES,
    workflow_steps=(
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            consumes=("system/blockMeshDict", _CONTROL_DICT_DOCUMENT),
            produces=POLY_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                _CONTROL_DICT_DOCUMENT, "system/fvSchemes", "system/fvSolution",
                "constant/physicsProperties", ELECTRO_PROPERTIES, "system/cableProbes",
            ),
            produces=(WITH_DEFAULT_VALUES, "postProcessing/cableProbes/*/Vm"),
        ),
        WorkflowStep(
            step_id=POSTPROCESS_STEP_ID,
            command=("Allrun.post",),
            default_arguments=(
                DefaultArgument(key=("--output-dir",), values=("postProcessing",)),
            ),
            # Not `postProcessing/cableProbes/*/Vm`: that is the `solve`
            # step's own `produces`, not an authored file this step fails
            # without -- C8 fingerprints only pre-existing inputs (P4's own
            # rule, `restitution_curves.py`'s docstring).
            consumes=(ELECTRO_PROPERTIES,),
            produces=("postProcessing/*_event_summary.json", "postProcessing/*_events.csv", "postProcessing/*_restitution.csv"),
        ),
    ),
)
