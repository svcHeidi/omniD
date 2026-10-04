"""cardiacFoam-owned physicsProperties, controlDict and prePacingProperties catalog entries."""

from __future__ import annotations

from typing import Final

from omnidriver.core.contracts.dictionary import DictEntry

from .dict_entries_catalog import IONIC_MODEL_MENU


PHYSICS_PROPERTY_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="type",
        phases=frozenset({"physics"}),
        description=(
            "Top-level physics model selector. Cardiac tutorial values in this repository "
            "include electroModel and electroMechanicalModel."
        ),
        source_refs=(
            "modules/physicsModel/src/solids4FoamModels/physicsModel/physicsModel.C",
            "applications/utilities/listCellModelsVariables/listCellModelsVariables.C",
            "src/electroModels/core/electroModel.H",
        ),
        value_kind="enum",
        enum_values=("electroModel", "electroMechanicalModel"),
        required=True,
    ),
)


CONTROL_DICT_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="deltaT",
        phases=frozenset({"solver"}),
        description=(
            "Simulation time step. Critical for ODE solver stability and "
            "manufactured-solution convergence tests — sweep alongside mesh "
            "refinement (number_cells) to measure temporal order. Use a large "
            "value for smoke-test runs that verify setup before committing to a "
            "fine-resolution sweep."
        ),
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        value_kind="scalar",
        unit="s",
        required=True,
        typical_value="",
    ),
    DictEntry(
        driver_path="endTime",
        phases=frozenset({"solver"}),
        description=(
            "Simulation end time. Set to a small value (e.g. 1e-3) for a "
            "smoke-test run that verifies the case launches and runs at least "
            "one step without crashing, before committing to a full-length "
            "production run."
        ),
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        value_kind="scalar",
        unit="s",
        required=True,
        typical_value="",
    ),
    DictEntry(
        driver_path="startTime",
        phases=frozenset({"solver"}),
        description="Simulation start time. Almost always 0 for new runs.",
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        value_kind="scalar",
        unit="s",
        required=True,
        typical_value="0",
    ),
    DictEntry(
        driver_path="startFrom",
        phases=frozenset({"solver"}),
        description=(
            "Which time directory to start from. "
            "startTime uses the value of startTime; "
            "latestTime restarts from the last written time directory."
        ),
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        value_kind="enum",
        enum_values=("startTime", "firstTime", "latestTime"),
        required=True,
        typical_value="startTime",
    ),
    DictEntry(
        driver_path="stopAt",
        phases=frozenset({"solver"}),
        description="Condition that halts the run.",
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        value_kind="enum",
        enum_values=("endTime", "writeNow", "noWriteNow", "nextWrite"),
        required=True,
        typical_value="endTime",
    ),
    DictEntry(
        driver_path="writeControl",
        phases=frozenset({"solver"}),
        description=(
            "Trigger for writing output to disk. "
            "runTime writes every writeInterval seconds of simulation time; "
            "timeStep writes every writeInterval time steps."
        ),
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        notes=(
            "enum_values matches Foam::Time::writeControlNames (OpenFOAM "
            "v2412 src/OpenFOAM/db/Time/Time.C): all seven names, including "
            "adjustableRunTime, which the native bathBidomain case uses."
        ),
        value_kind="enum",
        enum_values=(
            "none", "timeStep", "runTime", "adjustable", "adjustableRunTime",
            "clockTime", "cpuTime",
        ),
        required=True,
        typical_value="runTime",
    ),
    DictEntry(
        driver_path="writeInterval",
        phases=frozenset({"solver"}),
        description=(
            "Output writing frequency in units of writeControl. "
            "When writeControl=runTime this is seconds of simulation time. "
            "Typical cardiac simulations write every 5 ms."
        ),
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        value_kind="scalar",
        unit="s (when writeControl=runTime)",
        required=True,
        typical_value="5e-3",
    ),
    DictEntry(
        driver_path="writeFormat",
        phases=frozenset({"solver"}),
        description="Binary or ASCII output format. ASCII is human-readable; binary is faster and smaller.",
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        value_kind="enum",
        enum_values=("ascii", "binary"),
        required=True,
        typical_value="ascii",
    ),
    DictEntry(
        driver_path="purgeWrite",
        phases=frozenset({"solver"}),
        description=(
            "Number of output time directories to keep on disk (0 = keep all). "
            "Use 2-3 when disk space is limited on long convergence sweeps."
        ),
        source_refs=("applications/solvers/cardiacFoam/cardiacFoam.C",),
        value_kind="integer",
        required=True,
        typical_value="0",
    ),
)


_PRE_PACING_SOURCE = ("src/genericWriter/prePacingIO.H",)
_PRE_PACING_SOLVERS = {"myocardiumSolver": ("monodomainSolver", "bidomainSolver", "singleCellSolver")}

#: The opt-in ``constant/prePacingProperties``: its absence disables pre-pacing,
#: and ``regions.<name>`` overrides each key below for one tissue region. Every
#: solver but the eikonal builds the myocardium domain that reads it.
PRE_PACING_PROPERTY_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="tolerance",
        phases=frozenset({"solver"}),
        description=(
            "Largest relative change of any ionic state variable between successive beats "
            "below which a pre-paced cell counts as converged. Pre-pacing stops after two "
            "consecutive converged beats."
        ),
        source_refs=(*_PRE_PACING_SOURCE, "src/ionicModels/ionicModel/ionicModel.C"),
        value_kind="scalar",
        typical_value="1e-4",
        applicable_when=_PRE_PACING_SOLVERS,
    ),
    DictEntry(
        driver_path="minBeats",
        phases=frozenset({"solver"}),
        description="Fewest beats to pace before the convergence test may stop pre-pacing.",
        source_refs=(*_PRE_PACING_SOURCE, "src/ionicModels/ionicModel/ionicModel.C"),
        value_kind="integer",
        typical_value="10",
        applicable_when=_PRE_PACING_SOLVERS,
    ),
    DictEntry(
        driver_path="maxBeats",
        phases=frozenset({"solver"}),
        description=(
            "Most beats to pace; a cell that has not converged by then is a fatal error. "
            "It also sets the number of pulses of the pacing protocol (its nstim1)."
        ),
        source_refs=(*_PRE_PACING_SOURCE, "src/ionicModels/ionicModel/ionicModel.C", "src/electroModels/electroDomains/myocardiumDomain/myocardiumPrePacing.C"),
        value_kind="integer",
        typical_value="3000",
        applicable_when=_PRE_PACING_SOLVERS,
    ),
    DictEntry(
        driver_path="beatComparisonInterval",
        phases=frozenset({"solver"}),
        description=(
            "Time between ionic-state comparisons when the pacing protocol has no S1 period "
            "(stim_period_S1 unset or zero), for a self-beating model; with a S1 period the "
            "comparison is once per S1 cycle."
        ),
        source_refs=(*_PRE_PACING_SOURCE, "src/ionicModels/ionicModel/ionicModel.C", "src/electroModels/electroDomains/myocardiumDomain/myocardiumPrePacing.C"),
        notes=(
            "Pre-pacing is refused when no pacing protocol exists: either a singleCellStimulus "
            "(in this file, else the electroProperties one) or this key must be present."
        ),
        value_kind="scalar",
        unit="ms",
        typical_value="200",
        applicable_when=_PRE_PACING_SOLVERS,
    ),
    DictEntry(
        driver_path="singleCellIonicModel",
        phases=frozenset({"physics"}),
        description=(
            "Ionic model that paces the single cell, in place of the tissue's own ionicModel; "
            "typically the batched twin of a model that is slow to pace. Left unset, the cell "
            "uses the tissue's model."
        ),
        source_refs=(*_PRE_PACING_SOURCE, "src/electroModels/electroDomains/myocardiumDomain/myocardiumPrePacing.C"),
        constraints=(
            "Its state variables must match the tissue model's, in name and order, or "
            "pre-pacing is refused: the converged state seeds the tissue.",
        ),
        value_kind="enum",
        enum_values=IONIC_MODEL_MENU,
        applicable_when=_PRE_PACING_SOLVERS,
    ),
)
