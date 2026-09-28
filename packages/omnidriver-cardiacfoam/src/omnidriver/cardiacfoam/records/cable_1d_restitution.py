"""``cable1DRestitution``: a tutorial record for
``electrophysiologyProtocols/cableProtocol/monodomain1DCableCV``.

The native ``Allrun``'s commands, ``blockMesh`` then ``cardiacFoam``. The
``dx`` axis is shared with ``cable1DCVConvergence`` (:mod:`.cable_axes`).
``s1s2SpatialProtocol`` reproduces the old module's S1-S2 arithmetic for
both its pacing modes (coupling-interval and requested-DI90), reading the
stimulus geometry/duration/intensity and the S1 interval from the case's
own native defaults at resolve time rather than restating them. A third
``postprocess`` step runs the native ``Allrun.post``: the axis passes the case's own resolved S1/S2 split to it as
``--n-s1``/``--n-s2``/``--reference-repolarization90-s``, since
``case_record.json`` never carries resolved axis values for a single,
non-swept run. What each step reads/writes, the native defaults this axis
reads, and the two-mode arithmetic: ``docs/solver-learning/cardiacfoam.md``,
section CABLE.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.cardiacfoam.spatial_pacing import (
    generate_spatial_s1_s2_stimulus_lists, generate_spatial_stimulus_lists,
)
from omnidriver.core.tutorial_records import (
    AxisContract, AxisPatch, AxisResult, DefaultArgument, TutorialRecord, WorkflowStep,
)
from omnidriver.openfoam.case_planning import read_nested_entry
from omnidriver.openfoam.literals import parse_scalar_list_literal, parse_vector3_list_literal

from .cable_axes import cable_dx_axis
from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES

#: This tutorial always addresses `myocardiumSolver monodomainSolver`'s own
#: `monodomainSolverCoeffs` scope -- never varied (the native case already
#: holds it).
_MONODOMAIN_SOLVER_COEFFS = ("monodomainSolverCoeffs",)

DX_AXIS_NAME = "dx"
S1_S2_PROTOCOL_AXIS_NAME = "s1s2SpatialProtocol"

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

POSTPROCESS_STEP_ID = "postprocess"
_N_S1_ARG = ("--n-s1",)
_N_S2_ARG = ("--n-s2",)
_REFERENCE_REPOLARIZATION90_ARG = ("--reference-repolarization90-s",)


def _read_uniform_entry(
    file_path: Path, key: str, *, scope: list[str], parse,
) -> Any:
    """The one value ``key``'s list holds, read from the staged case --
    refused by name unless every entry agrees (docs/solver-learning/
    cardiacfoam.md, CABLE8: every native list this axis reads is uniform
    across all six of its entries today)."""
    raw = read_nested_entry(file_path, key, scope=scope)
    if raw is None:
        raise ValueError(
            f"{file_path}: no {'.'.join(scope)}.{key} entry to read the native default from"
        )
    values = parse(raw)
    if not values:
        raise ValueError(f"{file_path}:{'.'.join(scope)}.{key} is empty")
    if any(item != values[0] for item in values):
        raise ValueError(
            f"{file_path}:{'.'.join(scope)}.{key} is not uniform ({values!r}); "
            "this axis cannot pick one representative entry"
        )
    return values[0]


def _read_native_stimulus_defaults(
    staged_case_root: Path, electro_document: str, scope: tuple[str, ...],
) -> tuple[tuple[float, float, float], tuple[float, float, float], float, float, float]:
    """``(bounds_min, bounds_max, duration_s, intensity, s1_interval_ms)``,
    read from the staged case's own ``externalStimulus`` -- never a Python
    constant restating it (one source of truth). The S1 interval is
    ``t[1] - t[0]`` of the native ``stimulusStartTimeList``."""
    file_path = Path(staged_case_root) / electro_document
    stimulus_scope = list(scope) + ["externalStimulus"]
    bounds_min = _read_uniform_entry(
        file_path, "stimulusLocationMinList", scope=stimulus_scope, parse=parse_vector3_list_literal,
    )
    bounds_max = _read_uniform_entry(
        file_path, "stimulusLocationMaxList", scope=stimulus_scope, parse=parse_vector3_list_literal,
    )
    duration_s = _read_uniform_entry(
        file_path, "stimulusDurationList", scope=stimulus_scope, parse=parse_scalar_list_literal,
    )
    intensity = _read_uniform_entry(
        file_path, "stimulusIntensityList", scope=stimulus_scope, parse=parse_scalar_list_literal,
    )
    start_raw = read_nested_entry(file_path, "stimulusStartTimeList", scope=stimulus_scope)
    if start_raw is None:
        raise ValueError(f"{file_path}: no {'.'.join(stimulus_scope)}.stimulusStartTimeList entry")
    start_times = parse_scalar_list_literal(start_raw)
    if len(start_times) < 2:
        raise ValueError(
            f"{file_path}:{'.'.join(stimulus_scope)}.stimulusStartTimeList has fewer than 2 "
            f"entries ({start_times!r}); cannot read the S1 interval as t[1] - t[0]"
        )
    s1_interval_ms = (start_times[1] - start_times[0]) * 1000.0
    return bounds_min, bounds_max, duration_s, intensity, s1_interval_ms


def _s1_s2_protocol_axis(name: str, *, electro_document: str, scope: tuple[str, ...]) -> AxisContract:
    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        bounds_min, bounds_max, duration_s, intensity, s1_interval_ms = _read_native_stimulus_defaults(
            staged_case_root, electro_document, scope,
        )
        protocol = value
        n_s1 = int(protocol["n_s1"])
        n_s2 = int(protocol["n_s2"])
        end_time_buffer_s = float(protocol["end_time_buffer_s"])
        last_s1_time_s = (n_s1 - 1) * (s1_interval_ms / 1000.0) if n_s1 else 0.0

        if "requested_di90_ms" in protocol:
            if n_s2 != 1:
                raise ValueError(
                    f"{name!r}: requested_di90_ms scheduling requires n_s2 == 1, got {n_s2!r}"
                )
            reference_repolarization90_s = float(protocol["reference_repolarization90_s"])
            requested_di90_ms = float(protocol["requested_di90_ms"])
            s2_time_s = reference_repolarization90_s + requested_di90_ms / 1000.0
            s1_times_s = [i * (s1_interval_ms / 1000.0) for i in range(n_s1)]
            stimulus_lists = generate_spatial_stimulus_lists(
                times_s=s1_times_s + [s2_time_s],
                bounds_min=bounds_min, bounds_max=bounds_max,
                duration_s=duration_s, intensity=intensity,
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
                s1_interval_ms=s1_interval_ms, n_s1=n_s1,
                s2_interval_ms=s2_interval_ms, n_s2=n_s2,
                bounds_min=bounds_min, bounds_max=bounds_max,
                duration_s=duration_s, intensity=intensity,
            )
            # One extra S1 interval past the last stimulus: a 1D cable needs
            # propagation time a 0-D single cell does not (module docstring).
            end_time_s = (
                last_s1_time_s + (s1_interval_ms / 1000.0)
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
            # without -- C8 fingerprints only pre-existing inputs.
            consumes=(ELECTRO_PROPERTIES,),
            produces=("postProcessing/*_event_summary.json", "postProcessing/*_events.csv", "postProcessing/*_restitution.csv"),
        ),
    ),
)
