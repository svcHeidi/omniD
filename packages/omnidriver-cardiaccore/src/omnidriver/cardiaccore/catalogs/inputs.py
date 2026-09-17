"""Evidence-labelled input catalog for cardiacCore preprocessing utilities.

Every ``DictEntry`` below is backed by a native ``.get``/``.getOrDefault``/
``.found`` read discovered with ``omnidriver.openfoam.dict_keys_scanner`` over
``cardiacCoreStandalone/src`` (see ``docs/BUILDER_AGENT_EVIDENCE_CONTRACT.md``
for the exact invocation). Conditionality that the native source expresses as
an ``if``/``found`` branch is expressed here as ``applicable_when`` /
``required_when`` / ``forbidden_when`` / ``mutually_exclusive_with`` rather
than prose, following the vocabulary
``omnidriver-cardiacfoam/dict_entries_catalog.py`` already uses -- see
``omnidriver.core.specs.validation.entry_is_applicable`` /
``is_required_in_context`` / ``_predicate_matches`` for how these fields are
evaluated.

Declaring a key here gives an agent KNOWLEDGE of it. It does not make the key
mutable: a key only becomes an overridable "x value" once it is also routed
through ``workflows/overrides.py``'s ``_TARGETS`` map AND named in a
workflow's ``active_input_paths``. Several documents below (setCardiacScar,
setPurkinjeScar, generatePurkinjeTree, coordinatesConvention) are declared but
have no ``_TARGETS`` entry -- see the module docstring in ``workflows/overrides.py``
for why, and ``workflows/preprocessing.py``'s ``PURKINJE_TREE_INPUT_PATHS``
for the tree-parameter freeze this must not disturb.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog


_CONDUCTIVITY_SOURCE = "src/setCardiacConductivity/setCardiacConductivity.C"
_ANATOMY_SOURCE = "src/setCardiacAnatomy/setCardiacAnatomy.C"
_SLAB_SOURCE = "src/setPurkinjeSlab/setPurkinjeSlab.C"
_MORPHOMETRY_SOURCE = "src/setPurkinjeMorphometry/setPurkinjeMorphometry.C"
_SCAR_SOURCE = "src/setCardiacScar/setCardiacScar.C"
_SCAR_SEVERITY_SOURCE = "src/setCardiacScar/scarSeverityFn.H"
_SCAR_README = "src/setCardiacScar/README.md"
_PURKINJE_SCAR_SOURCE = "src/setPurkinjeScar/setPurkinjeScar.C"
_PURKINJE_SCAR_README = "src/setPurkinjeScar/README.md"
_COORDINATES_CONVENTION_SOURCE = "src/coordinatesConvention/coordinatesConvention.H"
_TREE_SOURCE = "src/generatePurkinjeTree/generatePurkinjeTree.C"
_TREE_README = "src/generatePurkinjeTree/README.md"


CONDUCTIVITY_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.df",
        description="Longitudinal conductivity coefficient used to construct Conductivity.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        notes=(
            "The utility constructs a dimensional conductivity field, but this adapter "
            "has not independently verified the physical unit for this input."
        ),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.ds",
        description="Sheet-direction conductivity coefficient used to construct Conductivity.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        notes=(
            "The utility constructs a dimensional conductivity field, but this adapter "
            "has not independently verified the physical unit for this input."
        ),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.dn",
        description="Normal-direction conductivity coefficient used to construct Conductivity.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        notes=(
            "The utility constructs a dimensional conductivity field, but this adapter "
            "has not independently verified the physical unit for this input."
        ),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.fiberField",
        description="Name of the vector field defining the fibre direction.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        value_kind="word",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.sheetField",
        description="Name of the vector field defining the sheet direction.",
        source_refs=("cases/bivCase/system/setCardiacConductivityDict", _CONDUCTIVITY_SOURCE),
        value_kind="word",
        required=True,
    ),
    # --- Bidomain pair, folded in from the old CONDITIONAL_INPUTS prose. ---
    # setCardiacConductivity.C: `hasIntracellular` and
    # `hasExtracellular` are each a bare `diffDict.found(...)` check, and a
    # FatalIOError fires when exactly one is present ("Bidomain output
    # requires both ... subdictionaries."). When present, each subDict is
    # passed to the same `writeConductivity` helper that reads the top-level
    # df/ds/dn (lines 22-34), so the subDict shares that shape.
    #
    # This is a genuine co-requirement ("both or neither"): setCardiacConductivity
    # raises a FatalIOError when exactly one subdictionary is present. It is NOT
    # `mutually_exclusive_with`, which fires when BOTH siblings are set; here
    # both-set is the required case. It is declared with `co_required_with` on
    # every member of the group, so the relation is symmetric and the validator
    # reports a half-set pair before a case is staged rather than leaving it to
    # the native FatalIOError at run time.
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.conductivityIntracellular.df",
        description="Longitudinal conductivity coefficient for the intracellular bidomain tensor.",
        source_refs=(_CONDUCTIVITY_SOURCE,),
        value_kind="scalar",
        co_required_with=(
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.dn",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.dn",
        ),
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.conductivityIntracellular.ds",
        description="Sheet-direction conductivity coefficient for the intracellular bidomain tensor.",
        source_refs=(_CONDUCTIVITY_SOURCE,),
        value_kind="scalar",
        co_required_with=(
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.dn",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.dn",
        ),
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.conductivityIntracellular.dn",
        description="Normal-direction conductivity coefficient for the intracellular bidomain tensor.",
        source_refs=(_CONDUCTIVITY_SOURCE,),
        value_kind="scalar",
        co_required_with=(
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.dn",
        ),
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.conductivityExtracellular.df",
        description="Longitudinal conductivity coefficient for the extracellular bidomain tensor.",
        source_refs=(_CONDUCTIVITY_SOURCE,),
        value_kind="scalar",
        co_required_with=(
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.dn",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.dn",
        ),
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.conductivityExtracellular.ds",
        description="Sheet-direction conductivity coefficient for the extracellular bidomain tensor.",
        source_refs=(_CONDUCTIVITY_SOURCE,),
        value_kind="scalar",
        co_required_with=(
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.dn",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.dn",
        ),
    ),
    DictEntry(
        driver_path="$CARDIAC_CONDUCTIVITY.conductivityExtracellular.dn",
        description="Normal-direction conductivity coefficient for the extracellular bidomain tensor.",
        source_refs=(_CONDUCTIVITY_SOURCE,),
        value_kind="scalar",
        co_required_with=(
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.ds",
            "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.dn",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.df",
            "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.ds",
        ),
    ),
)

ANATOMY_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$CARDIAC_ANATOMY.zApicalMid",
        description="Longitudinal-coordinate threshold separating apical and mid AHA regions.",
        source_refs=("cases/bivCase/system/setCardiacAnatomyDict", _ANATOMY_SOURCE),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_ANATOMY.zMidBasal",
        description="Longitudinal-coordinate threshold separating mid and basal AHA regions.",
        source_refs=("cases/bivCase/system/setCardiacAnatomyDict", _ANATOMY_SOURCE),
        value_kind="scalar",
        required=True,
    ),
    DictEntry(
        driver_path="$CARDIAC_ANATOMY.zApexCap",
        description="Longitudinal-coordinate extent assigned to the apical cap.",
        source_refs=("cases/bivCase/system/setCardiacAnatomyDict", _ANATOMY_SOURCE),
        value_kind="scalar",
        required=True,
    ),
)

SLAB_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$PURKINJE_SLAB.thickness",
        description="Sub-endocardial slab thickness in the case's transmural-coordinate units.",
        source_refs=("cases/bivCase/system/setPurkinjeSlabDict", _SLAB_SOURCE),
        value_kind="scalar",
        constraints=("Must lie between zero and the configured transmural-coordinate range.",),
        # This utility is optional at the adapter level: a selected workflow
        # must read this dictionary before it becomes a required case input.
        required=False,
    ),
    DictEntry(
        driver_path="$PURKINJE_SLAB.multiplier",
        description="Conductivity multiplier applied within the Purkinje slab.",
        source_refs=("cases/bivCase/system/setPurkinjeSlabDict", _SLAB_SOURCE),
        value_kind="scalar",
        required=False,
    ),
)

# setPurkinjeMorphometryDict currently has no reviewed x-values other than
# subendocardialWeight: groove detection is unconditional native behaviour
# (never a dictionary input). subendocardialWeight was previously kept out of
# CATALOG entirely (in CONDITIONAL_INPUTS) because bivCase does not set it and
# relies on the compiled default; it is folded in below as a real, optional
# DictEntry, matching the SLAB_ENTRIES precedent immediately above: declared,
# not required, and not routed through `_TARGETS` (see workflows/overrides.py).
MORPHOMETRY_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$PURKINJE_MORPHOMETRY.subendocardialWeight",
        description=(
            "Weight blending the subendocardial and intramural terminal-sampling "
            "fields written by setPurkinjeMorphometry."
        ),
        source_refs=("cases/bivCase/system/setPurkinjeMorphometryDict", _MORPHOMETRY_SOURCE),
        value_kind="scalar",
        typical_value="0.56",
        required=False,
    ),
)

# --- setCardiacScarDict -----------------------------------------------------
#
# Not present in the selected auto-mode bivCase (no workflow currently
# schedules setCardiacScar; see cardiacCoreStandalone/tutorials/template
# instead), so no `cases/bivCase/...` path is cited and no `_TARGETS` row
# exists for this document -- declared knowledge only, matching the
# utilities.py precedent (11 declared utilities, 5 scheduled).
SCAR_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$CARDIAC_SCAR.selection",
        description=(
            "Scar-region selector: a name ending in '.vtu' is read as a VTU CellData "
            "selection keyed by idArray; any other name is read as an OpenFOAM cellSet."
        ),
        source_refs=(_SCAR_SOURCE, _SCAR_README),
        value_kind="word",
        notes="Unconditionally required by the native utility (the scarDict.get<word> read of 'selection'); required=False here only because no cardiacCore workflow currently schedules setCardiacScar (see SLAB_ENTRIES precedent above).",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.idArray",
        description="VTU CellData array name providing global cell IDs for the .vtu selection form. Also reused, unchanged, for the optional channels.selection -- there is no separate channels.idArray key.",
        source_refs=(_SCAR_SOURCE, _SCAR_README),
        value_kind="word",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.distanceMode",
        description="Scar-depth distance metric.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="enum",
        enum_values=("topological", "euclidean"),
        notes="setCardiacScar.C's distanceMode branch raises a FatalError for any other value.",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.function",
        description="Severity-vs-normalized-depth response function.",
        source_refs=(_SCAR_SEVERITY_SOURCE,),
        value_kind="enum",
        enum_values=("linear", "power", "exponential", "logistic", "binary"),
        notes="scarSeverityFn.H raises a FatalError for any other value.",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.scarField",
        description="Output field name for the binary scar mask. Always written.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="word",
        typical_value="Scar",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.depthField",
        description="Output field name for topological/euclidean scar depth. Written only when writeDebugFields is true.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="word",
        typical_value="ScarDepth",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.normalizedDepthField",
        description="Output field name for the per-component normalized scar depth. Written only when writeDebugFields is true.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="word",
        typical_value="ScarNormalizedDepth",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.severityField",
        description="Output field name for the scar severity value in [0,1]. Always written; consumed by setPurkinjeScar.",
        source_refs=(_SCAR_SOURCE, _PURKINJE_SCAR_SOURCE),
        value_kind="word",
        typical_value="ScarSeverity",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.channelField",
        description="Output field name for the binary channel mask. Written only when writeDebugFields is true.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="word",
        typical_value="ScarChannel",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.scarRegionField",
        description="Output field name for the per-component scar region ID. Written only when writeDebugFields is true; setPurkinjeScar requires this field on disk (writeDebugFields true is mandatory for that hand-off).",
        source_refs=(_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="word",
        typical_value="ScarRegionID",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.channelRegionField",
        description="Output field name for the per-component channel region ID. Written only when writeDebugFields is true.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="word",
        typical_value="ScarChannelRegionID",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.power",
        description="Exponent for the 'power' severity function.",
        source_refs=(_SCAR_SEVERITY_SOURCE,),
        value_kind="scalar",
        typical_value="1.0",
        applicable_when={"function": ("power",)},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.exponentialBeta",
        description="Beta shape parameter for the 'exponential' severity function.",
        source_refs=(_SCAR_SEVERITY_SOURCE,),
        value_kind="scalar",
        typical_value="3.0",
        applicable_when={"function": ("exponential",)},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.logisticK",
        description="Steepness parameter for the 'logistic' severity function.",
        source_refs=(_SCAR_SEVERITY_SOURCE,),
        value_kind="scalar",
        typical_value="10.0",
        applicable_when={"function": ("logistic",)},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.logisticMidpoint",
        description="Midpoint parameter for the 'logistic' severity function.",
        source_refs=(_SCAR_SEVERITY_SOURCE,),
        value_kind="scalar",
        typical_value="0.5",
        applicable_when={"function": ("logistic",)},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.coreThreshold",
        description="Normalized-depth threshold at/above which the 'binary' severity function reports full severity.",
        source_refs=(_SCAR_SEVERITY_SOURCE,),
        value_kind="scalar",
        typical_value="0.7",
        applicable_when={"function": ("binary",)},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.maxConductivityScale",
        description="Conductivity scale applied at zero severity (the scar boundary).",
        source_refs=(_SCAR_SOURCE,),
        value_kind="scalar",
        typical_value="1.0",
        applicable_when={"scaleConductivity": "true"},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.coreMultiplier",
        description="Per-fiber-axis (fiber, sheet, normal) conductivity multiplier applied at full severity (the scar core).",
        source_refs=(_SCAR_SOURCE,),
        value_kind="vector3",
        typical_value="(0.30 0.05 0.05)",
        applicable_when={"scaleConductivity": "true"},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.fiberField",
        description="Name of the vector field defining the fibre direction, used only when scaling conductivity.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="word",
        typical_value="fiber",
        applicable_when={"scaleConductivity": "true"},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.sheetField",
        description="Name of the vector field defining the sheet direction, used only when scaling conductivity.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="word",
        typical_value="sheet",
        applicable_when={"scaleConductivity": "true"},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.scaleConductivity",
        description="Whether to scale Conductivity (and ConductivityIntracellular/ConductivityExtracellular, when present) inside the scar.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="boolean",
        typical_value="true",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.normalizeByComponent",
        description="Normalize scar depth independently per disconnected scar component (0-to-1 within each) rather than globally.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="boolean",
        typical_value="true",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.writeDebugFields",
        description="Write depthField/normalizedDepthField/channelField/scarRegionField/channelRegionField in addition to scarField/severityField.",
        source_refs=(_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="boolean",
        typical_value="false",
        notes="Must be true for the setPurkinjeScar hand-off, which requires scarRegionField on disk (README 'Required hand-off').",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.channels.enabled",
        description="Enable a conduction-channel sub-selection inside the scar.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="boolean",
        typical_value="false",
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.channels.channelScale",
        description="Uniform conductivity scale applied to channel cells when channelMultiplier is not given.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="scalar",
        typical_value="0.4",
        applicable_when={"channels.enabled": "true"},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.channels.selection",
        description="Channel-region selector, in the same idArray/.vtu-or-cellSet form as the top-level selection. Must resolve to a subset of the scar selection or the utility raises a FatalError.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="word",
        applicable_when={"channels.enabled": "true"},
        required_when={"channels.enabled": "true"},
    ),
    DictEntry(
        driver_path="$CARDIAC_SCAR.channels.channelMultiplier",
        description="Per-fiber-axis conductivity multiplier applied to channel cells, overriding the uniform channelScale.",
        source_refs=(_SCAR_SOURCE,),
        value_kind="vector3",
        notes="Defaults to three copies of channelScale when omitted (the channels subDict channelMultiplier getOrDefault); not a fixed literal default, so no typical_value is given.",
        applicable_when={"channels.enabled": "true"},
    ),
)

# --- setPurkinjeScarDict -----------------------------------------------------
#
# Same status as setCardiacScarDict: not present in bivCase, no `_TARGETS`
# row, declared knowledge only.
PURKINJE_SCAR_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$PURKINJE_SCAR.severityField",
        description="Name of the current-time volScalarField read as edge/PVJ severity, normalized to [0,1].",
        source_refs=(_PURKINJE_SCAR_SOURCE,),
        value_kind="word",
        notes="Unconditionally required by the native utility; required=False here for the same reason as $CARDIAC_SCAR.selection (no scheduling workflow yet).",
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.regionField",
        description="Name of the current-time volScalarField read as the scar region ID (-1 for healthy cells, from setCardiacScar's scarRegionField).",
        source_refs=(_PURKINJE_SCAR_SOURCE,),
        value_kind="word",
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.inputGraph",
        description="Name of the constant/<inputGraph> dictionary object to read (produced by 1DgraphToFoam).",
        source_refs=(_PURKINJE_SCAR_SOURCE,),
        value_kind="word",
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.outputGraph",
        description="Name of the constant/<outputGraph> dictionary object to write.",
        source_refs=(_PURKINJE_SCAR_SOURCE,),
        value_kind="word",
        notes="Defaults to inputGraph + 'Scar' when omitted (setPurkinjeScar.C, outGraphFileName); not a fixed literal, so no typical_value is given.",
        required=False,
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.purkinjeScarPolicy.conductanceReduction",
        description="Fractional edge-conductance reduction per unit endpoint severity, below conductanceBlockThreshold.",
        source_refs=(_PURKINJE_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="scalar",
        constraints=("Must lie in [0, 1] (setPurkinjeScar.C validatePolicy).",),
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.purkinjeScarPolicy.conductanceBlockThreshold",
        description="Severity at/above which an edge's conductance is set to zero.",
        source_refs=(_PURKINJE_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="scalar",
        constraints=("Must lie in [0, 1] (setPurkinjeScar.C validatePolicy).",),
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.purkinjeScarPolicy.basePvjResistance",
        description="Baseline (zero-severity) PVJ resistance.",
        source_refs=(_PURKINJE_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="scalar",
        constraints=("Must be positive (setPurkinjeScar.C validatePolicy).",),
        notes="README: 'a provisional 100 kOhm model value... the graph solver must define the physical unit ... before these values are treated as calibrated solver parameters.' No unit is given here for the same reason.",
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.purkinjeScarPolicy.resistanceMultiplier",
        description="PVJ resistance multiplier at full severity: pvjResistance = basePvjResistance * (1 + severity * resistanceMultiplier).",
        source_refs=(_PURKINJE_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="scalar",
        constraints=("Must be non-negative (setPurkinjeScar.C validatePolicy).",),
    ),
    # An optional `regions/<id>` subdictionary overrides any subset of the
    # four purkinjeScarPolicy values for edges/PVJs whose region ID matches
    # `<id>` (setPurkinjeScar.C, policyForRegion/readRegionPolicy).
    # `<id>` is an open-ended region ID, so this is a genuine dynamic_path
    # block, modelled the same way as generatePurkinjeTree's <ventKey> below.
    DictEntry(
        driver_path="$PURKINJE_SCAR.regions.<region_id>.conductanceReduction",
        description="Region-specific override of conductanceReduction for edges/PVJs whose region ID matches <region_id>.",
        source_refs=(_PURKINJE_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="scalar",
        dynamic_path=True,
        constraints=("Falls back to purkinjeScarPolicy.conductanceReduction when omitted; validated with the same [0,1] range.",),
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.regions.<region_id>.conductanceBlockThreshold",
        description="Region-specific override of conductanceBlockThreshold.",
        source_refs=(_PURKINJE_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="scalar",
        dynamic_path=True,
        constraints=("Falls back to purkinjeScarPolicy.conductanceBlockThreshold when omitted; validated with the same [0,1] range.",),
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.regions.<region_id>.basePvjResistance",
        description="Region-specific override of basePvjResistance.",
        source_refs=(_PURKINJE_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="scalar",
        dynamic_path=True,
        constraints=("Falls back to purkinjeScarPolicy.basePvjResistance when omitted; validated as positive.",),
    ),
    DictEntry(
        driver_path="$PURKINJE_SCAR.regions.<region_id>.resistanceMultiplier",
        description="Region-specific override of resistanceMultiplier.",
        source_refs=(_PURKINJE_SCAR_SOURCE, _PURKINJE_SCAR_README),
        value_kind="scalar",
        dynamic_path=True,
        constraints=("Falls back to purkinjeScarPolicy.resistanceMultiplier when omitted; validated as non-negative.",),
    ),
)

# --- coordinatesConventionDict -----------------------------------------------
#
# NOTE (dated 2026-09-17): cardiacCoreStandalone/src/coordinatesConvention was
# refactored (concurrently with this catalog rewrite, in the native repo, not
# this one) from a fixed `uvc` convention to a `coordinateSystem`-selected
# one (`uvc` or `cobiveco`). The dict file itself was renamed
# `uvcConventionDict` -> `coordinatesConventionDict`, the `uvc` sub-block ->
# `coordinates` (now getOrDefault with real field-name defaults instead of a
# hard `found` requirement), `rotationalField` was dropped, and
# `transmural.{min,max}` -> `transmural.{endocardium,epicardium}` (named by
# anatomical meaning, since CObiveco's `tm` has endocardium > epicardium).
# The entries below describe the CURRENT (post-refactor) shape, confirmed
# against cases/bivCase/system/coordinatesConventionDict, which already uses
# it. Superseded COORDINATES_CONVENTION_ENTRIES claims are corrected, not silently
# overwritten, per house style.
#
# Shared across setCardiacAnatomy, setPurkinjeSlab, setPurkinjeMorphometry
# and generatePurkinjeTree: each utility's coordinatesConvention.H reader only
# pulls the sub-block(s)/leaves it needs, but the file exists once per case
# and conventionally carries all blocks together.
COORDINATES_CONVENTION_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$COORDINATES_CONVENTION.coordinateSystem",
        description="Selects which ventricular coordinate system the case's fields follow.",
        source_refs=("cases/bivCase/system/coordinatesConventionDict", _COORDINATES_CONVENTION_SOURCE),
        value_kind="enum",
        enum_values=("uvc", "cobiveco"),
        notes=(
            "'uvc': Bayer et al. biventricular convention -- transmural and "
            "intraventricular membership are solved together against the LV "
            "boundary, so the RV-facing septal wall reads near-epicardial "
            "and needs the septal-flip/RV-septal-recovery correction "
            "generatePurkinjeTree applies (useSeptalFlip = coordinateSystem "
            "== uvc, generatePurkinjeTree.C). 'cobiveco': tm/tv/apicobasal "
            "fields solved independently per chamber, so no correction is "
            "needed or performed. Unconditionally required (readCoordinateSystem "
            "raises a FatalError for any other value)."
        ),
    ),
    DictEntry(
        driver_path="$COORDINATES_CONVENTION.coordinates.transmuralField",
        description="Name of the volScalarField carrying the transmural coordinate.",
        source_refs=("cases/bivCase/system/coordinatesConventionDict", _COORDINATES_CONVENTION_SOURCE),
        value_kind="word",
        typical_value="transmural",
        notes="Read from a subOrEmptyDict, so the whole 'coordinates' block is optional: a case whose fields already carry the canonical names (transmural/intraventricular/apicobasal) needs no 'coordinates' block at all.",
    ),
    DictEntry(
        driver_path="$COORDINATES_CONVENTION.coordinates.intraventricularField",
        description="Name of the volScalarField carrying the LV/RV intraventricular coordinate.",
        source_refs=("cases/bivCase/system/coordinatesConventionDict", _COORDINATES_CONVENTION_SOURCE),
        value_kind="word",
        typical_value="intraventricular",
    ),
    DictEntry(
        driver_path="$COORDINATES_CONVENTION.coordinates.longitudinalField",
        description="Name of the volScalarField carrying the apex-to-base longitudinal coordinate.",
        source_refs=("cases/bivCase/system/coordinatesConventionDict", _COORDINATES_CONVENTION_SOURCE),
        value_kind="word",
        typical_value="apicobasal",
    ),
    DictEntry(
        driver_path="$COORDINATES_CONVENTION.intraventricularChambers.LV",
        description="Intraventricular coordinate value identifying the LV chamber.",
        source_refs=("cases/bivCase/system/coordinatesConventionDict", _COORDINATES_CONVENTION_SOURCE),
        value_kind="scalar",
    ),
    DictEntry(
        driver_path="$COORDINATES_CONVENTION.intraventricularChambers.RV",
        description="Intraventricular coordinate value identifying the RV chamber.",
        source_refs=("cases/bivCase/system/coordinatesConventionDict", _COORDINATES_CONVENTION_SOURCE),
        value_kind="scalar",
        notes="isLeftVentricle()/isRightVentricle() classify a cell by proximity to LV vs RV; the LV/RV seam is their midpoint.",
    ),
    DictEntry(
        driver_path="$COORDINATES_CONVENTION.transmural.endocardium",
        description="Transmural-coordinate value at the endocardium. Not necessarily numerically smaller than epicardium (e.g. CObiveco's tm reads 1=endocardium, 0=epicardium).",
        source_refs=("cases/bivCase/system/coordinatesConventionDict", _COORDINATES_CONVENTION_SOURCE),
        value_kind="scalar",
    ),
    DictEntry(
        driver_path="$COORDINATES_CONVENTION.transmural.epicardium",
        description="Transmural-coordinate value at the epicardium.",
        source_refs=("cases/bivCase/system/coordinatesConventionDict", _COORDINATES_CONVENTION_SOURCE),
        value_kind="scalar",
    ),
)

# --- generatePurkinjeTreeDict -------------------------------------------------
#
# CRITICAL: these tree parameters are the ones workflows/preprocessing.py
# deliberately keeps frozen (`PURKINJE_TREE_INPUT_PATHS` covers only the
# conductivity/anatomy paths above). Declaring them here documents the native
# contract; it must NOT be paired with a `_TARGETS` row or an
# `active_input_paths` change (see workflows/overrides.py and
# workflows/preprocessing.py's `_apply_human_tree_case` / `_apply_pig_purkinje_case`,
# both of which reject any override outside `PURKINJE_TREE_INPUT_PATHS`
# regardless of what this catalog declares).
TREE_ENTRIES: Final[tuple[DictEntry, ...]] = (
    DictEntry(
        driver_path="$PURKINJE_TREE.hisBundleSeed",
        description="Common His/root point shared by the LV and RV trees in the glued output.",
        source_refs=("cases/bivCase/system/generatePurkinjeTreeDict", _TREE_SOURCE),
        value_kind="vector3",
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.growthModel",
        description="Cable-growth marching algorithm.",
        source_refs=("cases/bivCase/system/generatePurkinjeTreeDict", _TREE_SOURCE, _TREE_README),
        value_kind="enum",
        enum_values=("legacy", "surfaceFollow"),
        typical_value="legacy",
        notes="'legacy': nearest-vertex one-ring projection, fixed straight march direction. 'surfaceFollow': nearest-point-on-surface projection plus march-direction re-projection every step (generatePurkinjeTree.C's growthModel legacy/surfaceFollow guard, README).",
    ),
    # Per-ventricle block: the scanner reports scope <ventKey> (README: "the
    # same block structure is used for lv and rv"). Modelled the way
    # cardiacFoam models ionicHeterogeneity.regions.<region_name>.* --
    # dynamic_path=True with a <ventKey> placeholder segment.
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.seed",
        description="Initial point of the ventricular tree.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="vector3",
        dynamic_path=True,
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.lineEnd",
        description="Point defining the initial trunk direction together with seed (direction = lineEnd - seed).",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="vector3",
        dynamic_path=True,
        mutually_exclusive_with=("$PURKINJE_TREE.<ventKey>.initDir",),
        constraints=(
            "Alternative to initDir; a ventricular block must provide exactly one "
            "(generatePurkinjeTree.C's lineEnd/initDir branch raises a FatalError if neither is "
            "present). If both are present the native code silently prefers "
            "lineEnd and never reads initDir (readVentParams' if/else-if), so "
            "`mutually_exclusive_with` is a stricter check than the native code "
            "enforces -- flagged here as a call-out in the report.",
        ),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.initDir",
        description="Initial trunk direction vector, used directly instead of deriving it from lineEnd.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="vector3",
        dynamic_path=True,
        mutually_exclusive_with=("$PURKINJE_TREE.<ventKey>.lineEnd",),
        constraints=("Alternative to lineEnd; see lineEnd sibling entry.",),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.initLength",
        description="Initial trunk length.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.N_it",
        description="Number of branching generations grown after the trunk.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="integer",
        dynamic_path=True,
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.length",
        description="Mean length of each new branch.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.l_segment",
        description="Discretization step length used while growing each branch.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
        constraints=("Must suit local mesh resolution (README): too coarse relative to surface triangle size/curvature can walk the march out of its local projection neighbourhood.",),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.branchAngle",
        description="Half-angle between the two daughter branches at a bifurcation.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        unit="rad",
        dynamic_path=True,
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.repulsivity",
        description="Local branch-separation correction weight.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.transmuralMin",
        description="Minimum accepted transmural coordinate for a surface growth point.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
        notes="Defaults to transmuralLowerValue($COORDINATES_CONVENTION.transmural) = min(endocardium, epicardium) when omitted (generatePurkinjeTree.C's transmuralMin getOrDefault and its range guard); not a fixed literal, so no typical_value is given.",
        constraints=("Must satisfy transmuralLowerValue <= transmuralMin <= transmuralMax <= transmuralUpperValue (the numeric bounds of $COORDINATES_CONVENTION.transmural, not necessarily endocardium <= epicardium -- see that document's notes on CObiveco).",),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.transmuralMax",
        description="Maximum accepted transmural coordinate for a surface growth point.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
        notes="Defaults to transmuralUpperValue($COORDINATES_CONVENTION.transmural) = max(endocardium, epicardium) when omitted (generatePurkinjeTree.C's transmuralMax getOrDefault and its range guard); not a fixed literal, so no typical_value is given.",
        constraints=("Must satisfy transmuralLowerValue <= transmuralMin <= transmuralMax <= transmuralUpperValue; see transmuralMin sibling entry.",),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.longitudinalMin",
        description="Minimum accepted longitudinal coordinate for a surface growth point.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
        typical_value="-GREAT (unbounded)",
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.longitudinalMax",
        description="Maximum accepted longitudinal coordinate for a surface growth point.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
        typical_value="GREAT (unbounded)",
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.terminalModel",
        description="Terminal (PMJ) placement model.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="enum",
        enum_values=("endocardial", "transmural"),
        typical_value="endocardial",
        dynamic_path=True,
        notes="'endocardial': terminals stay on the grown tree. 'transmural': each terminal marches inward toward a depth sampled from [extension.depthMin, extension.depthMax]; requires the extension sub-block.",
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.extension.type",
        description="Transmural terminal-extension march style.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="enum",
        enum_values=("straightSegment", "gradientFollow"),
        dynamic_path=True,
        applicable_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        required_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        notes="'straightSegment' samples one inward direction; 'gradientFollow' re-evaluates it every step and produces fewer marches that exit the mesh (README). Both march in wall-thickness depth, so neither assumes a transmural orientation (cardiacCore 1ea6d23).",
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.extension.depthMin",
        description="Minimum depth into the wall, as a fraction of thickness from the endocardium, sampled as a terminal-extension target.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
        applicable_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        required_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        constraints=("Must satisfy 0 <= depthMin <= depthMax <= 1 (generatePurkinjeTree.C's extension depth guard). 0 is the endocardial surface and 1 the epicardial one, whichever numeric transmural value each carries, so one value means the same place under uvc and cobiveco.",),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.extension.depthMax",
        description="Maximum depth into the wall sampled as a terminal-extension target; the effective ceiling since the march stops as soon as it crosses the sampled depth.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
        applicable_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        required_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        constraints=("Must satisfy 0 <= depthMin <= depthMax <= 1; see the depthMin sibling entry.",),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.extension.stepLen",
        description="Terminal-extension marching step length.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="scalar",
        dynamic_path=True,
        applicable_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        required_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        constraints=("Must be positive (generatePurkinjeTree.C's extension.stepLen/maxSteps guard).",),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.extension.maxSteps",
        description="Safety limit on the number of marching steps for one terminal extension.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="integer",
        dynamic_path=True,
        applicable_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        required_when={"$PURKINJE_TREE.<ventKey>.terminalModel": ("transmural",)},
        constraints=("Must be positive (generatePurkinjeTree.C's extension.stepLen/maxSteps guard).",),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.terminalSelectionModel",
        description="Terminal-sampling model: which grown leaves become terminals.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="enum",
        enum_values=("allLeaves", "weightedField"),
        typical_value="allLeaves",
        dynamic_path=True,
        constraints=(
            "weightedField is supported for the lv block only in v1 "
            "(generatePurkinjeTree.C's weightedField ventKey guard raises a FatalError for "
            "ventKey != 'lv'). This restricts one *instance* of the "
            "<ventKey> dynamic block relative to another (lv vs rv), which "
            "the applicable_when/forbidden_when predicate model cannot "
            "express -- applicability is evaluated once per catalog entry, "
            "not once per resolved instance name (see "
            "omnidriver.core.specs.validation._predicate_matches docstring). "
            "Left as a cited constraint; see the report.",
        ),
    ),
    DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.terminalCount",
        description="Number of distinct LV source leaves sampled by terminalSelectionModel=weightedField.",
        source_refs=(_TREE_SOURCE, _TREE_README),
        value_kind="integer",
        dynamic_path=True,
        applicable_when={"$PURKINJE_TREE.<ventKey>.terminalSelectionModel": ("weightedField",)},
        required_when={"$PURKINJE_TREE.<ventKey>.terminalSelectionModel": ("weightedField",)},
        constraints=("Must be positive (generatePurkinjeTree.C's terminalCount positivity guard).",),
    ),
)

_RAW_DOCUMENTS: Final[dict[str, tuple[DictEntry, ...]]] = {
    "setCardiacConductivityDict": CONDUCTIVITY_ENTRIES,
    "setCardiacAnatomyDict": ANATOMY_ENTRIES,
    "setPurkinjeSlabDict": SLAB_ENTRIES,
    "setPurkinjeMorphometryDict": MORPHOMETRY_ENTRIES,
    "setCardiacScarDict": SCAR_ENTRIES,
    "setPurkinjeScarDict": PURKINJE_SCAR_ENTRIES,
    "coordinatesConventionDict": COORDINATES_CONVENTION_ENTRIES,
    "generatePurkinjeTreeDict": TREE_ENTRIES,
}

# These values are all consumed before a cardiac solver exists in this
# workflow. Giving them one adapter-owned phase makes strict validation honest
# without borrowing cardiacFoam's anatomy/physics/stimulus/solver vocabulary.
DOCUMENTS: Final[dict[str, tuple[DictEntry, ...]]] = {
    name: tuple(replace(entry, phases=frozenset({"preprocessing"})) for entry in entries)
    for name, entries in _RAW_DOCUMENTS.items()
}

CATALOG: Final[DictionaryCatalog] = DictionaryCatalog(DOCUMENTS)

# All source reads that were CONDITIONAL_INPUTS prose (the setCardiacConductivity
# bidomain pair and setPurkinjeMorphometry's subendocardialWeight) are now real
# DictEntry objects above, using applicable_when/required_when/constraints
# instead of free-text "when"/"reason"/"status" dicts. CONDITIONAL_INPUTS is
# therefore empty. The name stays bound (rather than removed) because
# plugin.py's `cardiaccore_conditional_inputs` named catalog publishes it
# unconditionally.
CONDITIONAL_INPUTS: Final[dict[str, tuple[dict[str, object], ...]]] = {}

# --- Triage of the remaining native reads that are NOT settings a user places
# in a system/*Dict configuration file. Keeping these visible (rather than
# silently dropping them) is the point: a reader can see they were
# classified, not missed. ---

# Graph-file format keys: the on-disk shape of a `constant/<graphName>`
# 1D-graph object (written by 1DgraphToFoam / generatePurkinjeTree's VTK
# output, read by foamTo1Dgraph and setPurkinjeScar). Not a system/*Dict
# user setting, so never a DictEntry.
GRAPH_FILE_KEYS: Final[tuple[dict[str, object], ...]] = (
    {
        "name": "points",
        "reason": "Graph node coordinates (pointField).",
        "source_refs": ("src/foamTo1Dgraph/foamTo1Dgraph.C", "src/setPurkinjeScar/setPurkinjeScar.C"),
    },
    {
        "name": "conductionEdges",
        "reason": "Scalar-list edge records: endpoint node indices at positions 0/1, conductance at position 3.",
        "source_refs": ("src/foamTo1Dgraph/foamTo1Dgraph.C", "src/setPurkinjeScar/setPurkinjeScar.C"),
    },
    {
        "name": "pvjNodes",
        "reason": "Optional node indices receiving PVJ resistances.",
        "source_refs": ("src/foamTo1Dgraph/foamTo1Dgraph.C", "src/setPurkinjeScar/setPurkinjeScar.C"),
    },
    {
        "name": "pvjResistances",
        "reason": "Optional per-PVJ-node resistance values, written by setPurkinjeScar.",
        "source_refs": ("src/foamTo1Dgraph/foamTo1Dgraph.C",),
    },
)

# CLI options, not dictionary keys: the scanner matches any
# `.getOrDefault<T>("key", default)` call syntactically, and cannot
# distinguish an `argList` option accessor (`args.getOrDefault(...)`) from a
# `dictionary` accessor. All three of these are read from argList, not from
# any system/*Dict.
UTILITY_CLI_OPTIONS: Final[tuple[dict[str, object], ...]] = (
    {
        "name": "name",
        "utility": "1DgraphToFoam",
        "reason": "-name command-line option naming the constant/ graph object to write (default: purkinjeGraph).",
        "source_refs": ("src/1DgraphToFoam/1DgraphToFoam.C",),
    },
    {
        "name": "maxEdgeLength",
        "utility": "refine1Dgraph",
        "reason": "-maxEdgeLength command-line option (default: 3e-4 m).",
        "source_refs": ("src/refine1Dgraph/refine1Dgraph.C",),
    },
    {
        "name": "internalRole",
        "utility": "refine1Dgraph",
        "reason": "-internalRole command-line option for the inserted-node role value (default: -1).",
        "source_refs": ("src/refine1Dgraph/refine1Dgraph.C",),
    },
)
