"""cardiacFoam-owned physicsProperties and prePacingProperties catalog entries."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from omnidriver.core.contracts.catalogue_paths import slot_key
from omnidriver.core.contracts.dictionary import DictEntry

from .dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS, IONIC_MODEL_MENU


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


_PRE_PACING_SOURCE = ("src/genericWriter/prePacingIO.H",)
_PRE_PACING_SOLVERS = {"myocardiumSolver": ("monodomainSolver", "bidomainSolver")}
_PRE_PACING_TOKEN = "$PRE_PACING."
_PRE_PACING_REGION = _PRE_PACING_TOKEN + "regions.<region_name>."


def _pre_pacing_entries(scope: str) -> tuple[DictEntry, ...]:
    """The keys ``prePacingIO::readEntries`` reads, at the file's root or in one ``regions.<region_name>`` block, by ``scope``."""
    bindings = {"<region_name>": None} if scope != _PRE_PACING_TOKEN else {}
    ionic = ("src/ionicModels/ionicModel/ionicModel.C",)
    prepacing = ("src/electroModels/electroDomains/myocardiumDomain/myocardiumPrePacing.C",)

    def entry(key: str, **fields) -> DictEntry:
        return DictEntry(
            driver_path=scope + key, phases=frozenset({"solver"}), allowed_bindings=bindings,
            applicable_when=_PRE_PACING_SOLVERS, **fields,
        )

    return (
        entry(
            "enabled", value_kind="boolean",
            description=(
                "Whether pre-pacing runs. The file's presence enables it, so the key is only needed to set "
                "false, which leaves the cells (at the root: the whole case) at their initial state."
            ),
            source_refs=(*_PRE_PACING_SOURCE, *prepacing),
            notes="Absent, it is true at the root and, inside a region block, the root's value.",
            typical_value="true",
        ),
        entry(
            "tolerance", value_kind="scalar", typical_value="1e-4",
            description=(
                "Largest relative change of any ionic state variable between successive beats "
                "below which a pre-paced cell counts as converged. Pre-pacing stops after two "
                "consecutive converged beats."
            ),
            source_refs=(*_PRE_PACING_SOURCE, *ionic),
        ),
        entry(
            "minBeats", value_kind="integer", typical_value="10",
            description="Fewest beats to pace before the convergence test may stop pre-pacing.",
            source_refs=(*_PRE_PACING_SOURCE, *ionic),
        ),
        entry(
            "maxBeats", value_kind="integer", typical_value="3000",
            description=(
                "Most beats to pace; a cell that has not converged by then is a fatal error. "
                "It also sets the number of pulses of the pacing protocol (its nstim1)."
            ),
            source_refs=(*_PRE_PACING_SOURCE, *ionic, *prepacing),
        ),
        entry(
            "beatComparisonInterval", value_kind="scalar", unit="ms", typical_value="200",
            description=(
                "Time between ionic-state comparisons when the pacing protocol has no S1 period "
                "(stim_period_S1 unset or zero), for a self-beating model; with a S1 period the "
                "comparison is once per S1 cycle."
            ),
            source_refs=(*_PRE_PACING_SOURCE, *ionic, *prepacing),
            notes=(
                "Pre-pacing is refused when no pacing protocol exists: either a singleCellStimulus "
                "(in this file, else the electroProperties one) or this key must be present."
            ),
        ),
        entry(
            "singleCellIonicModel", value_kind="enum", enum_values=IONIC_MODEL_MENU,
            description=(
                "Ionic model that paces the single cell, in place of the tissue's own ionicModel; "
                "typically the batched twin of a model that is slow to pace. Left unset, the cell "
                "uses the tissue's model."
            ),
            source_refs=(*_PRE_PACING_SOURCE, *prepacing),
            constraints=(
                "Its state variables must match the tissue model's, in name and order, or "
                "pre-pacing is refused: the converged state seeds the tissue.",
            ),
        ),
        entry(
            "batchedIntegrator", value_kind="enum", enum_values=("euler", "rushLarsen"),
            description=(
                "Integration scheme of the single cell, in place of the tissue's batchedIntegrator. "
                "Left unset, the cell uses the tissue's."
            ),
            source_refs=(*_PRE_PACING_SOURCE, *prepacing, "src/ionicModels/ionicModel/batchedIonicModel.H"),
            notes="Read by the batched ionic models only; any other value is fatal there.",
        ),
        entry(
            "deltaT", value_kind="scalar", unit="s",
            description=(
                "Time step of the single-cell pre-pacing integration. Unset or 0, the cell uses the case's deltaT."
            ),
            source_refs=(*_PRE_PACING_SOURCE, *prepacing),
        ),
    )


def _pre_pacing_stimulus_entries(scope: str) -> tuple[DictEntry, ...]:
    """The pacing protocol, which ``myocardiumPrePacing`` hands to the same ``stimulusIO::loadStimulusProtocol`` as
    electroProperties' ``singleCellStimulus``: that block's entries, re-rooted under ``scope`` and applying to the solvers
    that read the file, with the four protocol keys required together once any key of the block is set."""
    presence = slot_key(f"{scope}$singleCellStimulus_present")
    bindings = {"<region_name>": None} if scope != _PRE_PACING_TOKEN else {}
    prefix = "$ELECTRO_MODEL_COEFFS.singleCellStimulus."
    return tuple(
        replace(
            entry, driver_path=f"{scope}singleCellStimulus.{entry.driver_path.removeprefix(prefix)}",
            applicable_when=_PRE_PACING_SOLVERS, allowed_bindings=bindings, typical_value="", constraints=(),
            required=False, required_when={presence: True} if entry.required_when else {},
            source_refs=(*_PRE_PACING_SOURCE, *entry.source_refs),
            notes=(
                "Set to maxBeats whatever it says, so every beat is paced."
                if entry.driver_path.endswith(".nstim1") else entry.notes
            ),
        )
        for entry in ELECTRO_PROPERTY_ENTRY_GROUPS["single_cell_stimulus"]
    )


#: The opt-in ``constant/prePacingProperties``, whose paths carry the scope
#: token ``$PRE_PACING`` because ``deltaT`` is also a ``controlDict`` key: its absence disables pre-pacing,
#: and ``regions.<region_name>`` overrides each key above for one tissue region.
#: Monodomain and bidomain build the myocardium domain that reads it;
#: singleCellSolver and the eikonal solver do not.
PRE_PACING_PROPERTY_ENTRIES: Final[tuple[DictEntry, ...]] = (
    *_pre_pacing_entries(_PRE_PACING_TOKEN), *_pre_pacing_stimulus_entries(_PRE_PACING_TOKEN),
    *_pre_pacing_entries(_PRE_PACING_REGION), *_pre_pacing_stimulus_entries(_PRE_PACING_REGION),
)
