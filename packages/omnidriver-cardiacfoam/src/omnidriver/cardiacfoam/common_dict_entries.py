"""cardiacFoam-owned physicsProperties, prePacingProperties and Purkinje graph catalog entries."""

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


_DOMAIN = "src/electroModels/electroDomains/conductionSystemDomain/"
_GRAPH_READER = _DOMAIN + "conductionSystemDomain.C"
_GRAPH_TOPOLOGY = _DOMAIN + "conductionGraph.H"
_SOLVERS = "src/electroModels/conductionSystemModels/"
_COUPLERS = "src/electroModels/electroCouplers/pvjCoupler/"
_GRAPH_WRITER = "applications/utilities/1DgraphToFoam/1DgraphToFoam.C"

#: The graph dictionary ``conductionSystemDomain::readGraphFile`` opens as ``constant/<graphFile>``, named by
#: ``conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.graphFile`` (1DgraphToFoam writes ``purkinjeGraph``).
#: A graph tool's output, not a study's dictionary: a study selects a graph through graphFile and never edits
#: one, so the record-key validator does not address it; ``validation.case_diagnostics`` judges a case's
#: graph against these entries and the tree the C++ requires. The other keys 1DgraphToFoam writes
#: (``edges``, ``edgeLength``, ``pointFields`` and the rest) are its provenance, read by no solver.
PURKINJE_GRAPH_DOCUMENT = "purkinjeGraph"

PURKINJE_GRAPH_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="conductionEdges", phases=frozenset({"anatomy"}), value_kind="scalar_list", required=True,
        description=(
            "The edges of the conduction tree, one (nodeA nodeB length conductance) entry each. Node indices "
            "count from 0, and the graph has one node more than the largest index. length is the edge length "
            "in metres: monodomain1DSolver couples the two nodes by sigma/length and gives each node half of "
            "every incident length as its control length, and the eikonal solvers take length over the "
            "conduction velocity as the edge's travel time. conductance times purkinjeConductivity is the "
            "edge conductivity sigma of the cable equation, in S/m; restitutionEikonalSolver1D scales the "
            "edge's velocity by the square root of it over referenceConductance, and eikonalSolver1D ignores it."
        ),
        source_refs=(
            _GRAPH_TOPOLOGY, _GRAPH_READER, _SOLVERS + "monodomain1DSolver/monodomain1DSolver.C",
            _SOLVERS + "eikonalSolver1D/eikonalSolver1D.C",
            _SOLVERS + "restitutionEikonalSolver1D/restitutionEikonalSolver1D.C", _GRAPH_WRITER,
        ),
        constraints=(
            "Each entry is itself a list of four numbers; the catalogue has no value kind for a list of lists.",
            "A tree: one edge fewer than nodes, and every node reached from node 0.",
            "A conductance of 0 blocks the edge in monodomain1DSolver and restitutionEikonalSolver1D.",
        ),
    ),
    DictEntry(
        driver_path="points", phases=frozenset({"anatomy"}), value_kind="vector3_list", unit="m", required=True,
        description=(
            "Position [m] of every graph node, in node order. It goes to the network's VTK output and to the "
            "graph verifier; the solvers take edge lengths from conductionEdges, not from these positions."
        ),
        source_refs=(_GRAPH_READER, _GRAPH_WRITER),
        constraints=("One position per graph node.",),
    ),
    DictEntry(
        driver_path="rootNode", phases=frozenset({"anatomy"}), value_kind="integer", minimum=0, required=True,
        description=(
            "The network's root: the node rootStimulus drives, and where the eikonal solvers start the "
            "activation at the earliest rootStimulus start time. rootStimulus.node, when given, replaces it. "
            "monodomain1DSolver orders the tree from node 0 whatever the root."
        ),
        source_refs=(_GRAPH_READER, _GRAPH_TOPOLOGY, _SOLVERS + "eikonalSolver1D/eikonalSolver1D.C", _GRAPH_WRITER),
        constraints=("A node index of conductionEdges.",),
    ),
    DictEntry(
        driver_path="pvjNodes", phases=frozenset({"anatomy"}), value_kind="integer_list", required=True,
        description=(
            "The graph nodes coupled to the myocardium, one per Purkinje-ventricular junction (PVJ). A coupler "
            "reads the network's Vm or activation time at these nodes and, in bidirectional coupling, returns "
            "the junction current or the tissue's activation time to them. Any node may be one; 1DgraphToFoam "
            "takes the nodes marked terminal, else the endpoints other than the root."
        ),
        source_refs=(_GRAPH_READER, _COUPLERS + "reactionDiffusion/reactionDiffusionPvjCoupler.C", _GRAPH_WRITER),
        constraints=("Node indices of conductionEdges.", "One per pvjLocations entry, in the same order."),
    ),
    DictEntry(
        driver_path="pvjLocations", phases=frozenset({"anatomy"}), value_kind="vector3_list", unit="m",
        required=True,
        description=(
            "Position [m] of each PVJ in the myocardium mesh's coordinates, in pvjNodes order: pvjMapper "
            "couples the junction to the myocardium cells within pvjRadius of it. The C++ does not compare it "
            "with the points entry of the same node; 1DgraphToFoam writes that position."
        ),
        source_refs=(_GRAPH_READER, _COUPLERS + "pvjMapper.C", _GRAPH_WRITER),
    ),
    DictEntry(
        driver_path="pvjResistances", phases=frozenset({"physics"}), value_kind="scalar_list",
        description=(
            "Resistance of each PVJ, in pvjNodes order, in place of the coupling's single rPvj: the junction "
            "current is (Vm of the network node - Vm of the junction tissue) / resistance. With it, "
            "reactionDiffusionPvjCoupler never reads rPvj; eikonalMonodomainPvjCoupler still requires rPvj and "
            "then uses these. It has rPvj's unit, which is not settled (see rPvj). An empty list counts as absent."
        ),
        source_refs=(
            _GRAPH_TOPOLOGY, _DOMAIN + "conductionSystemDomain.H",
            _COUPLERS + "reactionDiffusion/reactionDiffusionPvjCoupler.C",
            _COUPLERS + "eikonalMonodomain/eikonalMonodomainPvjCoupler.C",
        ),
        constraints=("One per pvjNodes entry.",),
    ),
)
