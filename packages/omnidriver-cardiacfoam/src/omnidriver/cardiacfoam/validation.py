from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from omnidriver.cardiacfoam.dict_entries_catalog import HETEROGENEITY_MODELS
from omnidriver.cardiacfoam.solver_coupling import SOLVER_COMPATIBILITY_RULES
from omnidriver.core.planning_types import diagnostic
from omnidriver.openfoam.literals import switch_value

if TYPE_CHECKING:
    from omnidriver.core.planning_types import StrictDiagnostic


def _diagnostic_from_phase(phase: str, field: str, message: str, level: str) -> "StrictDiagnostic":
    """A ``run_validation`` diagnostic from the ``(phase, field, message, level)`` call shape."""
    return diagnostic(level, "run_validation", message, source=phase, field=field)


def _catalogued(driver_path: str, value: Any) -> bool:
    """Whether the catalogue lists ``value``; a name it lacks may be one the scan registered, so a rule never refuses it."""
    from .record_key_validation import _ELECTRO_ENTRIES_BY_PATH

    entry = _ELECTRO_ENTRIES_BY_PATH.get(driver_path)
    return entry is not None and value in entry.enum_values


# Block-presence virtual keys: a catalogue entry gated on `$..._present` or
# `$..._configured` applies only to a context that holds a leaf under the
# block. Without one the block stays off, so plain bidomain gets no bath
# leaves.
_VIRTUAL_PRESENCE_TRIGGERS: tuple[tuple[str, str], ...] = (
    ("bathPotentialDomain.", "$bathPotentialDomain_configured"),
    ("ecgDomains.", "$ecgDomains_present"),
    ("conductionNetworkDomains.", "$conductionNetworkDomains_present"),
    # A single-cell run with no stimulus is legal: stimulusIO returns a
    # no-op protocol when the sub-dict is absent. Gating the stimulus family
    # on presence rather than on myocardiumSolver keeps the builder from
    # inventing stim_amplitude/nstim1 defaults and quietly pacing a case
    # that asked for none.
    ("singleCellStimulus.", "$singleCellStimulus_present"),
    ("externalStimulus.", "$externalStimulus_present"),
)


def infer_virtual_presence(ctx: dict[str, Any], *, empty_blocks: "frozenset[str]" = frozenset()) -> None:
    """Set, in place, the virtual keys that a leaf of `ctx` under a block
    implies, and for each ECG domain holding ``personalizedTemplates`` the
    domain's own ``$personalizedTemplates_present``. A block named in
    ``empty_blocks`` (the case holds it with no leaf) counts as present. Idempotent."""
    for prefix, virtual_key in _VIRTUAL_PRESENCE_TRIGGERS:
        if virtual_key in ctx:
            continue
        if prefix.removesuffix(".") in empty_blocks:
            ctx[virtual_key] = True
            continue
        for existing_key in ctx:
            if existing_key.startswith(prefix):
                ctx[virtual_key] = True
                break
    for existing_key in [key for key in ctx if key.startswith("regions.") and ".singleCellStimulus." in key]:
        ctx[existing_key.split(".singleCellStimulus.")[0] + ".$singleCellStimulus_present"] = True
    for existing_key in [key for key in ctx if key.startswith(_ECG_DOMAIN_PREFIX) and _PERSONALIZED_TEMPLATES_SUFFIX in key]:
        ctx[existing_key.split(_PERSONALIZED_TEMPLATES_SUFFIX)[0] + ".$personalizedTemplates_present"] = True

    if ctx.get("myocardiumSolver") == "eikonalSolver" or ctx.get("ionicModel") in HETEROGENEITY_MODELS:
        ctx["$ionicHeterogeneity_supported"] = True



_CONDUCTION_SOLVER_SUFFIX = ".purkinjeGraphModelCoeffs.conductionSystemSolver"
_COUPLER_SUFFIX = ".electroDomainCoupler"
_NETWORK_REF_SUFFIX = ".conductionNetworkDomain"
_CONDUCTION_NET_PREFIX = "conductionNetworkDomains."
_DOMAIN_COUPLINGS_PREFIX = "domainCouplings."


def _evaluate_solver_coupling(context: dict[str, Any]) -> list["StrictDiagnostic"]:
    """Check each explicit coupling against the network it names, as the C++ system builder resolves it."""
    errors: list["StrictDiagnostic"] = []
    myocardium = context.get("myocardiumSolver")
    if myocardium is None:
        return errors

    coupling_blocks = sorted({
        key.rsplit(".", 1)[0]
        for key in context
        if key.startswith(_DOMAIN_COUPLINGS_PREFIX)
        and key.endswith((_NETWORK_REF_SUFFIX, _COUPLER_SUFFIX))
    })
    declared_networks = _declared_conduction_networks(context)
    for block in coupling_blocks:
        reference_key = block + _NETWORK_REF_SUFFIX
        network = context.get(reference_key)
        if network is None or str(network) not in declared_networks:
            # Required-field and block-reference checks own these errors.
            # Never substitute another declared network for an absent target.
            continue

        solver_key = (
            _CONDUCTION_NET_PREFIX + str(network) + _CONDUCTION_SOLVER_SUFFIX
        )
        purkinje = context.get(solver_key)
        coupler_key = block + _COUPLER_SUFFIX
        actual = context.get(coupler_key)
        rule = next((
            candidate for candidate in SOLVER_COMPATIBILITY_RULES
            if candidate["myocardium_solver"] == myocardium
            and purkinje is not None
            and candidate["purkinje_solver"] in (purkinje, "*")
        ), None)

        if rule is None:
            errors.append(_diagnostic_from_phase(
                phase="physics",
                field=coupler_key,
                message=(
                    f"Solver coupling compatibility is unknown for {block}: "
                    f"myocardiumSolver={myocardium}, "
                    f"conductionNetworkDomain={network!r}, "
                    f"conductionSystemSolver={purkinje!r}. "
                    "No applicable compatibility rule is available."
                ),
                level="warning",
            ))
            continue

        if not rule["valid"]:
            errors.append(_diagnostic_from_phase(
                phase="physics",
                field=coupler_key,
                message=(
                    f"Incompatible solver pair for {block} "
                    f"(conductionNetworkDomain={network!r}): "
                    f"myocardiumSolver={myocardium} "
                    f"with conductionSystemSolver={purkinje}. "
                    f"{rule.get('reason', '')}"
                ).strip(),
                level="error",
            ))
            continue

        required = rule.get("required_coupler")
        if required is None:
            continue
        if actual is None:
            errors.append(_diagnostic_from_phase(
                phase="physics",
                field=coupler_key,
                message=(
                    f"electroDomainCoupler is required for {block} "
                    f"(conductionNetworkDomain={network!r}): myocardiumSolver="
                    f"{myocardium} + conductionSystemSolver={purkinje}; "
                    f"expected {required}."
                ),
                level="error",
            ))
        elif actual != required:
            errors.append(_diagnostic_from_phase(
                phase="physics",
                field=coupler_key,
                message=(
                    f"electroDomainCoupler={actual!r} is incompatible for "
                    f"{block} (conductionNetworkDomain={network!r}) "
                    f"with myocardiumSolver={myocardium} + "
                    f"conductionSystemSolver={purkinje}; "
                    f"expected {required}."
                ),
                level="error",
            ))

    return errors


def _declared_conduction_networks(context: dict[str, Any]) -> set[str]:
    """Names of the conductionNetworkDomains.<name> blocks with a sub-key in ``context``."""
    declared_networks: set[str] = set()
    for key in context:
        if not key.startswith(_CONDUCTION_NET_PREFIX):
            continue
        rest = key[len(_CONDUCTION_NET_PREFIX):]
        if "." not in rest:
            continue
        declared_networks.add(rest.split(".", 1)[0])
    return declared_networks


def _evaluate_block_references(
    context: dict[str, Any],
) -> list["StrictDiagnostic"]:
    errors: list["StrictDiagnostic"] = []
    declared_networks = _declared_conduction_networks(context)

    for key, val in context.items():
        if not (
            key.startswith(_DOMAIN_COUPLINGS_PREFIX)
            and key.endswith(_NETWORK_REF_SUFFIX)
        ):
            continue
        referenced = str(val)
        if referenced not in declared_networks:
            errors.append(_diagnostic_from_phase(
                phase="physics",
                field=key,
                message=(
                    f"conductionNetworkDomain references {referenced!r} but "
                    f"no matching block is declared under "
                    f"conductionNetworkDomains.{referenced}.*"
                ),
                level="error",
            ))

    return errors


_HETEROGENEITY_PREFIX = "ionicHeterogeneity."
# 'gradientAxes' is a dynamic-name dictionary of named axes (e.g.
# 'apicobasal'), so the check below groups by axis name instead of assuming
# a single block. endoMInterface/mEpiInterface and the transmuralBands mode
# are not accepted, so there is no ordering check between them.
_GRADIENT_AXES_PREFIX = "ionicHeterogeneity.gradientAxes."


def _evaluate_heterogeneity(context: dict[str, Any]) -> list["StrictDiagnostic"]:
    errors: list["StrictDiagnostic"] = []
    het_keys = [k for k in context if k.startswith(_HETEROGENEITY_PREFIX)]
    if not het_keys:
        return errors

    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG

    transmural_keys = [k for k in het_keys if not k.startswith(_GRADIENT_AXES_PREFIX)]
    ga_keys = [k for k in het_keys if k.startswith(_GRADIENT_AXES_PREFIX)]

    model = context.get("ionicModel")
    entry = IONIC_MODEL_CATALOG.get(model) if model is not None else None

    if transmural_keys and entry is not None and not getattr(entry, "supports_heterogeneity", False):
        capable_models = sorted(
            n for n, e in IONIC_MODEL_CATALOG.items()
            if getattr(e, "supports_heterogeneity", False)
            and not n.endswith("compactBatched")
        )
        errors.append(_diagnostic_from_phase(
            phase="physics",
            field="$ELECTRO_MODEL_COEFFS.ionicHeterogeneity",
            message=(
                f"ionicHeterogeneity is configured but ionicModel "
                f"{model!r} does not support transmural heterogeneity. "
                f"Supported models: {', '.join(capable_models)} "
                f"(and their compactBatched variants where available)."
            ),
            level="error",
        ))

    mode = context.get("ionicHeterogeneity.mode")
    if mode == "namedRegions":
        ranges = []
        for k, v in context.items():
            if k.startswith("ionicHeterogeneity.regions.") and k.endswith(".range"):
                region_name = k.split(".")[2]
                try:
                    if isinstance(v, str):
                        clean_v = v.strip("()[] ")
                        parts = clean_v.split()
                        min_v, max_v = float(parts[0]), float(parts[1])
                    else:
                        min_v, max_v = float(v[0]), float(v[1])
                    ranges.append((min_v, max_v, region_name, k))
                except (ValueError, TypeError, IndexError):
                    pass

        ranges.sort(key=lambda x: x[0])

        for i in range(len(ranges)):
            min_v, max_v, name, k = ranges[i]
            if min_v >= max_v:
                errors.append(_diagnostic_from_phase(
                    phase="physics",
                    field=f"$ELECTRO_MODEL_COEFFS.{k}",
                    message=f"Region '{name}' range [{min_v}, {max_v}] must be strictly increasing.",
                    level="error",
                ))
            if min_v < 0.0 or max_v > 1.0:
                errors.append(_diagnostic_from_phase(
                    phase="physics",
                    field=f"$ELECTRO_MODEL_COEFFS.{k}",
                    message=f"Region '{name}' range [{min_v}, {max_v}] must be within [0, 1].",
                    level="error",
                ))
            if i > 0:
                prev_min, prev_max, prev_name, prev_k = ranges[i - 1]
                if min_v < prev_max:
                    errors.append(_diagnostic_from_phase(
                        phase="physics",
                        field=f"$ELECTRO_MODEL_COEFFS.{k}",
                        message=f"Region '{name}' range [{min_v}, {max_v}] overlaps with region '{prev_name}' [{prev_min}, {prev_max}].",
                        level="error",
                    ))

    if ga_keys:
        if entry is not None and not getattr(entry, "supports_gradient_axis_heterogeneity", False):
            capable_models = sorted(
                n for n, e in IONIC_MODEL_CATALOG.items()
                if getattr(e, "supports_gradient_axis_heterogeneity", False)
                and not n.endswith("compactBatched")
            )
            errors.append(_diagnostic_from_phase(
                phase="physics",
                field="$ELECTRO_MODEL_COEFFS.ionicHeterogeneity.gradientAxes",
                message=(
                    f"ionicHeterogeneity.gradientAxes is configured but ionicModel "
                    f"{model!r} does not support gradient-axis heterogeneity. "
                    f"Supported models: {', '.join(capable_models)} "
                    f"(and their compactBatched variants where available)."
                ),
                level="error",
            ))

        # gradientAxes is a dynamic-name dictionary: more than one named axis
        # (e.g. apicobasal, longitudinal) can compose on the same run, each
        # validated independently.
        axis_names = sorted({
            k[len(_GRADIENT_AXES_PREFIX):].split(".", 1)[0]
            for k in ga_keys
            if "." in k[len(_GRADIENT_AXES_PREFIX):]
        })
        for axis in axis_names:
            prefix = f"{_GRADIENT_AXES_PREFIX}{axis}."

            # Mirrors ionicHeterogeneity::validateGradientAxisConfig exactly:
            # 0 < scalingMin <= scalingMax. beta carries no native constraint
            # (apexBaseScale accepts any value, positive or negative) and is
            # deliberately not checked here.
            scaling_min = context.get(prefix + "scalingMin")
            scaling_max = context.get(prefix + "scalingMax")
            if scaling_min is not None:
                try:
                    if float(scaling_min) <= 0:
                        errors.append(_diagnostic_from_phase(
                            phase="physics",
                            field=f"$ELECTRO_MODEL_COEFFS.{prefix}scalingMin",
                            message=f"gradientAxes.{axis}.scalingMin ({scaling_min}) must be > 0.",
                            level="error",
                        ))
                except (TypeError, ValueError):
                    pass
            if scaling_max is not None:
                try:
                    if float(scaling_max) <= 0:
                        errors.append(_diagnostic_from_phase(
                            phase="physics",
                            field=f"$ELECTRO_MODEL_COEFFS.{prefix}scalingMax",
                            message=f"gradientAxes.{axis}.scalingMax ({scaling_max}) must be > 0.",
                            level="error",
                        ))
                except (TypeError, ValueError):
                    pass
            if scaling_min is not None and scaling_max is not None:
                try:
                    if float(scaling_max) < float(scaling_min):
                        errors.append(_diagnostic_from_phase(
                            phase="physics",
                            field=f"$ELECTRO_MODEL_COEFFS.{prefix}scalingMin",
                            message=(
                                f"gradientAxes.{axis}.scalingMax ({scaling_max}) must be >= "
                                f"scalingMin ({scaling_min})."
                            ),
                            level="error",
                        ))
                except (TypeError, ValueError):
                    pass

            # validateGradientAxisConfig also fatals on an empty 'variables'
            # list (ionicHeterogeneity.C).
            variables = context.get(prefix + "variables")
            if variables is not None:
                if isinstance(variables, str):
                    is_empty = not variables.strip("()[] ").strip()
                elif isinstance(variables, (list, tuple)):
                    is_empty = len(variables) == 0
                else:
                    is_empty = False
                if is_empty:
                    errors.append(_diagnostic_from_phase(
                        phase="physics",
                        field=f"$ELECTRO_MODEL_COEFFS.{prefix}variables",
                        message=f"gradientAxes.{axis}.variables must not be empty.",
                        level="error",
                    ))

    return errors


def _evaluate_tissue_compatibility(context: dict[str, Any]) -> list["StrictDiagnostic"]:
    errors: list["StrictDiagnostic"] = []
    model = context.get("ionicModel")
    tissue = context.get("tissue")
    if model is None or tissue is None:
        return errors

    from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG

    entry = IONIC_MODEL_CATALOG.get(model)
    if entry is None or not entry.compatible_tissues:
        return errors
    if not any(tissue in known.compatible_tissues for known in IONIC_MODEL_CATALOG.values()):
        return errors
    if "manufactured" in entry.compatible_tissues:
        return errors
    if tissue not in entry.compatible_tissues:
        errors.append(_diagnostic_from_phase(
            phase="physics",
            field="$ELECTRO_MODEL_COEFFS.tissue",
            message=(
                f"tissue {tissue!r} is not in the compatible tissues for "
                f"ionicModel {model!r}: {list(entry.compatible_tissues)}."
            ),
            level="error",
        ))

    return errors


_ECG_DOMAIN_PREFIX = "ecgDomains."
_PERSONALIZED_TEMPLATES_SUFFIX = ".personalizedTemplates."


def _evaluate_personalized_templates(context: dict[str, Any]) -> list["StrictDiagnostic"]:
    """Value checks of the optional eikonalECG template-generation block; its required keys are the catalogue's ``required_when``."""
    errors: list["StrictDiagnostic"] = []
    domains = {
        key[len(_ECG_DOMAIN_PREFIX):].split(".", 1)[0]
        for key in context
        if key.startswith(_ECG_DOMAIN_PREFIX)
        and _PERSONALIZED_TEMPLATES_SUFFIX in key
    }
    for domain in sorted(domains):
        prefix = f"{_ECG_DOMAIN_PREFIX}{domain}."
        template_prefix = prefix + "personalizedTemplates."
        field = prefix + "personalizedTemplates"
        ecg_solver = context.get(prefix + "ecgSolver")
        if ecg_solver != "eikonalECG":
            if not _catalogued("$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.ecgSolver", ecg_solver):
                continue
            errors.append(_diagnostic_from_phase(
                phase="physics", field=field,
                message="personalizedTemplates is supported only by ecgSolver=eikonalECG.",
                level="error",
            ))
            continue

        manufactured = (
            context.get(prefix + "ecgVerificationModel") == "manufacturedEikonalECGVerifier"
            or context.get(prefix + "verificationModel.type") == "manufacturedEikonalECGVerifier"
        )
        if manufactured:
            errors.append(_diagnostic_from_phase(
                phase="physics", field=field,
                message=("personalizedTemplates cannot be combined with a manufactured "
                         "eikonal ECG verification configuration."),
                level="error",
            ))

        def number(suffix: str) -> float | None:
            try:
                return float(context[template_prefix + suffix])
            except (KeyError, TypeError, ValueError):
                return None

        n_beats = number("nBeats")
        duration = number("duration")
        dt = number("dt")
        period = number("ionicModelConfig.singleCellStimulus.stim_period_S1")
        nstim2 = number("ionicModelConfig.singleCellStimulus.nstim2")
        if n_beats is not None and n_beats < 1:
            errors.append(_diagnostic_from_phase("physics", template_prefix + "nBeats", "personalizedTemplates.nBeats must be at least 1.", "error"))
        if duration is not None and duration <= 0:
            errors.append(_diagnostic_from_phase("physics", template_prefix + "duration", "personalizedTemplates.duration must be positive.", "error"))
        if dt is not None and dt <= 0:
            errors.append(_diagnostic_from_phase("physics", template_prefix + "dt", "personalizedTemplates.dt must be positive.", "error"))
        if duration is not None and period is not None and duration > 1e-3 * period:
            errors.append(_diagnostic_from_phase("physics", template_prefix + "duration", "personalizedTemplates.duration must not exceed one S1 period.", "error"))
        if nstim2 is not None and nstim2 != 0:
            errors.append(_diagnostic_from_phase("physics", template_prefix + "ionicModelConfig.singleCellStimulus.nstim2", "personalizedTemplates does not support non-zero nstim2.", "error"))
        if not any(key.startswith("ionicHeterogeneity.") for key in context):
            errors.append(_diagnostic_from_phase("physics", "ionicHeterogeneity", "personalizedTemplates requires an ionicHeterogeneity block.", "error"))

    return errors


_TISSUE_ANISOTROPIC_VERIFIER = "manufacturedAnisotropicMonodomainVerifier"
_ECG_PSEUDO_VERIFIER = "manufacturedPseudoECGVerifier"


def _as_switch_bool(value: Any) -> bool:
    """An OpenFOAM ``Switch``-shaped value as a bool; a missing one reads as the native default, false."""
    return bool(switch_value(value))


def _evaluate_ecg_anisotropic_consistency(context: dict[str, Any]) -> list["StrictDiagnostic"]:
    """``ecgDomains.<name>.verificationModel.anisotropic`` is yes exactly when the tissue verifier is the anisotropic one."""
    # A mismatch silently checks the pseudo-ECG samples against the wrong reference field.
    errors: list["StrictDiagnostic"] = []
    tissue_verifier = context.get("verificationModel.type")
    if tissue_verifier is not None and not _catalogued(
        "$ELECTRO_MODEL_COEFFS.verificationModel.type", tissue_verifier,
    ):
        return errors
    tissue_is_anisotropic = tissue_verifier == _TISSUE_ANISOTROPIC_VERIFIER

    domains = {
        key[len(_ECG_DOMAIN_PREFIX):].split(".", 1)[0]
        for key in context
        if key.startswith(_ECG_DOMAIN_PREFIX)
    }
    for domain in sorted(domains):
        prefix = f"{_ECG_DOMAIN_PREFIX}{domain}."
        # Only manufacturedPseudoECGVerifier reads `anisotropic`.
        if context.get(prefix + "verificationModel.type") != _ECG_PSEUDO_VERIFIER:
            continue

        field = prefix + "verificationModel.anisotropic"
        anisotropic = _as_switch_bool(context.get(field))
        if anisotropic == tissue_is_anisotropic:
            continue

        tissue_type = context.get("verificationModel.type")
        if anisotropic:
            message = (
                f"{field} is yes, but $ELECTRO_MODEL_COEFFS.verificationModel.type "
                f"is {tissue_type!r}, not {_TISSUE_ANISOTROPIC_VERIFIER!r}. "
                "anisotropic must match the tissue verifier actually driving the solve."
            )
        else:
            message = (
                f"{field} is no (or unset), but "
                f"$ELECTRO_MODEL_COEFFS.verificationModel.type is "
                f"{_TISSUE_ANISOTROPIC_VERIFIER!r}. anisotropic must be yes "
                f"when the tissue verifier is {_TISSUE_ANISOTROPIC_VERIFIER!r}."
            )
        errors.append(_diagnostic_from_phase(
            phase="physics", field=field, message=message, level="error",
        ))
    return errors


_RPVJ_COUPLER = "reactionDiffusionPvjCoupler"
_GRAPH_FILE_SUFFIX = ".purkinjeGraphModelCoeffs.graphFile"


@lru_cache(maxsize=8)
def _read_graph(path: str, stamp: tuple[int, int]) -> tuple[dict[str, str], tuple[tuple[str, str], ...]]:
    """A graph file's catalogued keys and its breaks, once per file version: a plan judges the case twice."""
    from omnidriver.openfoam.mutators import read_foam_entries

    from .common_dict_entries import PURKINJE_GRAPH_ENTRIES

    raw = read_foam_entries(Path(path), [entry.driver_path for entry in PURKINJE_GRAPH_ENTRIES])
    return raw, tuple(_graph_breaks(raw))


def _materialized_graphs(case_root: Path, context: dict[str, Any]) -> dict[str, tuple[str, dict[str, str], tuple]]:
    """Each network's graph file the case holds: its case-relative path, catalogued keys and breaks."""
    graphs: dict[str, tuple[str, dict[str, str], tuple]] = {}
    for key, name in context.items():
        if not (key.startswith(_CONDUCTION_NET_PREFIX) and key.endswith(_GRAPH_FILE_SUFFIX)):
            continue
        relpath = f"constant/{name}"
        path = case_root / relpath
        if not path.is_file():
            continue
        status = path.stat()
        graphs[key[len(_CONDUCTION_NET_PREFIX):-len(_GRAPH_FILE_SUFFIX)]] = (
            relpath, *_read_graph(str(path.resolve()), (status.st_mtime_ns, status.st_size)),
        )
    return graphs


def _graph_breaks(raw: dict[str, str]) -> list[tuple[str, str]]:
    """``(key, reason)`` for each way a graph's text breaks what ``conductionGraph::readFromDict`` and
    ``conductionSystemDomain::readGraphFile`` require; a key the file lacks is the catalogue's to report."""
    from omnidriver.openfoam.literals import list_elements, parse_scalar_list_literal

    breaks: list[tuple[str, str]] = []

    def elements(key: str) -> list[str] | None:
        try:
            return list_elements(raw[key]) if key in raw else None
        except ValueError as exc:
            breaks.append((key, f"{key} is not an OpenFOAM list: {exc}"))
            return None

    def labels(key: str, values: list[str]) -> list[int] | None:
        try:
            return [int(value) for value in values]
        except ValueError:
            breaks.append((key, f"{key} holds a value that is not a node index"))
            return None

    nodes = None
    edges = elements("conductionEdges")
    if edges is not None:
        pairs = []
        for index, text in enumerate(edges):
            try:
                values = parse_scalar_list_literal(text)
            except ValueError as exc:
                breaks.append(("conductionEdges", f"conductionEdges entry {index} is not a list of numbers: {exc}"))
                break
            if len(values) != 4:
                breaks.append((
                    "conductionEdges",
                    f"conductionEdges entry {index} has {len(values)} values, not (nodeA nodeB length conductance)",
                ))
                break
            pairs.append((int(values[0]), int(values[1])))
        else:
            if any(node < 0 for pair in pairs for node in pair):
                breaks.append(("conductionEdges", "conductionEdges names a negative node index; nodes count from 0"))
            else:
                nodes = max([0, *(node for pair in pairs for node in pair)]) + 1
                if len(pairs) != nodes - 1:
                    breaks.append((
                        "conductionEdges",
                        f"conductionEdges has {len(pairs)} edges over {nodes} nodes; the tree "
                        f"conductionGraph::buildTreeTopology requires has {nodes - 1}",
                    ))
                else:
                    neighbours: dict[int, list[int]] = {}
                    for a, b in pairs:
                        neighbours.setdefault(a, []).append(b)
                        neighbours.setdefault(b, []).append(a)
                    reached, frontier = {0}, [0]
                    while frontier:
                        for neighbour in neighbours.get(frontier.pop(), ()):
                            if neighbour not in reached:
                                reached.add(neighbour)
                                frontier.append(neighbour)
                    if len(reached) != nodes:
                        breaks.append((
                            "conductionEdges",
                            f"conductionEdges is not connected: node 0 reaches {len(reached)} of {nodes} nodes",
                        ))
    pvj = elements("pvjNodes")
    pvj_nodes = labels("pvjNodes", pvj) if pvj is not None else None
    if nodes is not None:
        root = labels("rootNode", [raw["rootNode"]]) if "rootNode" in raw else None
        if root is not None and not 0 <= root[0] < nodes:
            breaks.append(("rootNode", f"rootNode {root[0]} is outside the graph's nodes 0 to {nodes - 1}"))
        outside = [node for node in pvj_nodes or () if not 0 <= node < nodes]
        if outside:
            breaks.append(("pvjNodes", f"pvjNodes {outside[:5]} are outside the graph's nodes 0 to {nodes - 1}"))
        points = elements("points")
        if points is not None and len(points) != nodes:
            breaks.append(("points", f"points holds {len(points)} positions for {nodes} nodes"))
    if pvj_nodes is not None:
        # An empty pvjResistances is no list at all to the couplers (terminalResistances).
        for key, listed in (("pvjLocations", elements("pvjLocations")), ("pvjResistances", elements("pvjResistances") or None)):
            if listed is not None and len(listed) != len(pvj_nodes):
                breaks.append((key, f"{key} holds {len(listed)} values for {len(pvj_nodes)} pvjNodes"))
    return breaks


def _evaluate_conduction_graphs(graphs: dict[str, tuple[str, dict[str, str], tuple]]) -> list["StrictDiagnostic"]:
    """The catalogue's rules and the tree the C++ requires, over each network's graph file."""
    from omnidriver.openfoam.case_rules import rule_diagnostics

    from .common_dict_entries import PURKINJE_GRAPH_ENTRIES

    found: list["StrictDiagnostic"] = []
    for relpath, raw, breaks in graphs.values():
        found += rule_diagnostics(PURKINJE_GRAPH_ENTRIES, raw, document=relpath)
        found += [
            diagnostic("error", "conduction_graph_invalid", f"{relpath}: {reason}.", source=relpath, field=key)
            for key, reason in breaks
        ]
    return found


def _evaluate_pvj_resistance_requirement(
    context: dict[str, Any], graphs: dict[str, tuple[str, dict[str, str], tuple]], electro_path: Path,
) -> list["StrictDiagnostic"]:
    """``rPvj`` is required only when the materialized graph has no ``pvjResistances``, which a ``required_when`` cannot see; an absent graph defers."""
    from omnidriver.openfoam.literals import list_elements

    found: list["StrictDiagnostic"] = []
    for key, coupler in context.items():
        if not (key.startswith(_DOMAIN_COUPLINGS_PREFIX) and key.endswith(_COUPLER_SUFFIX)) or coupler != _RPVJ_COUPLER:
            continue
        block = key[: -len(_COUPLER_SUFFIX)]
        network = context.get(block + _NETWORK_REF_SUFFIX)
        rpvj_key = f"{block}.rPvj"
        if network is None or rpvj_key in context or network not in graphs:
            continue
        relpath, raw, _breaks = graphs[network]
        try:
            if "pvjResistances" in raw and list_elements(raw["pvjResistances"]):
                continue
        except ValueError:
            continue
        found.append(diagnostic(
            "error", "missing_rpvj",
            (
                f"conductionNetworkDomains.{network} is coupled via {_RPVJ_COUPLER} ({block}) "
                f"but neither rPvj nor a graph-provided pvjResistances list is available: the "
                f"materialized graph file {relpath!r} has no pvjResistances, and rPvj is not "
                f"set. reactionDiffusionPvjCoupler.C will FatalError on dict.get<scalar>(\"rPvj\")."
            ),
            source=str(electro_path), field=rpvj_key,
        ))
    return found


def cross_field_diagnostics(context: dict[str, Any]) -> list["StrictDiagnostic"]:
    """The rules between values that no single catalogue entry states.
    ``context`` is the active ``<solver>Coeffs`` block's leaves, keyed by
    dotted path, plus ``myocardiumSolver``."""
    return (
        _evaluate_solver_coupling(context)
        + _evaluate_block_references(context)
        + _evaluate_heterogeneity(context)
        + _evaluate_personalized_templates(context)
        + _evaluate_tissue_compatibility(context)
        + _evaluate_ecg_anisotropic_consistency(context)
    )


def case_diagnostics(case_root: Path, *, mapping: Any = None) -> tuple["StrictDiagnostic", ...]:
    """Every rule the resolved case at ``case_root`` violates: the catalogue's
    relations over its ``electroProperties``, ``prePacingProperties``,
    ``controlDict`` and the Purkinje graph each conduction network names, the
    keys the supplied C++ (``mapping``) requires, and cardiacFOAM's cross-field rules. A case with no ``electroProperties``
    violates none. ``physicsProperties``' one key is judged by ``physics_layout``."""
    from foamlib import FoamFile

    from omnidriver.openfoam.case_rules import flatten, read_leaves, rule_diagnostics
    from omnidriver.openfoam.control_dict import control_dict_diagnostics

    from .cardiacfoam_plugin import CardiacFoamPlugin
    from .record_key_validation import _ELECTRO_ENTRIES_BY_PATH
    from .physics_layout import region_document

    case_root = Path(case_root)
    electro_path = region_document(case_root, "electro", "electroProperties")
    if electro_path is None:
        return ()
    try:
        parsed = FoamFile(electro_path)
        solver = parsed.get("myocardiumSolver")
        context = {"myocardiumSolver": str(solver), **flatten(parsed[f"{solver}Coeffs"])}
    except (OSError, ValueError, KeyError) as exc:
        return (diagnostic(
            "error", "missing_solver",
            f"{electro_path} names no myocardiumSolver whose <solver>Coeffs block it holds: {exc!r}",
            source=str(electro_path), field="myocardiumSolver",
        ),)
    catalogue = CardiacFoamPlugin.get_dictionary_catalog()
    document = electro_path.relative_to(case_root).as_posix()
    entries = tuple(_ELECTRO_ENTRIES_BY_PATH.values())
    rule_context = dict(context)
    # The C++ takes the stimulus boxes from externalStimulus whenever it is found, empty or not.
    held = frozenset(name for name in ("externalStimulus",) if hasattr(parsed[f"{solver}Coeffs"].get(name), "keys"))
    infer_virtual_presence(rule_context, empty_blocks=held)
    found = rule_diagnostics(entries, rule_context, document=document, mapping=mapping, catalogue=catalogue)
    found += control_dict_diagnostics(case_root)
    pre_pacing = region_document(case_root, "electro", "prePacingProperties")
    if pre_pacing is not None:
        relative = pre_pacing.relative_to(case_root).as_posix()
        try:
            leaves = read_leaves(pre_pacing)
        except (OSError, ValueError, KeyError) as exc:
            found.append(diagnostic("error", "case_unreadable", f"{pre_pacing} cannot be read: {exc}", source=relative))
        else:
            pacing = {"myocardiumSolver": str(solver), **leaves}
            infer_virtual_presence(pacing)
            found += rule_diagnostics(
                catalogue.entries_for("prePacingProperties"), pacing,
                document=relative, mapping=mapping, catalogue=catalogue,
            )
    graphs = _materialized_graphs(case_root, context)
    return tuple(
        found
        + cross_field_diagnostics(context)
        + _evaluate_conduction_graphs(graphs)
        + _evaluate_pvj_resistance_requirement(context, graphs, electro_path)
    )
