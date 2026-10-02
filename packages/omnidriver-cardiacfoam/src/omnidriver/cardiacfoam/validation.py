from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from omnidriver.cardiacfoam.solver_coupling import SOLVER_COMPATIBILITY_RULES
from omnidriver.core.planning_types import diagnostic

if TYPE_CHECKING:
    from omnidriver.core.planning_types import StrictDiagnostic


def _diagnostic_from_phase(phase: str, field: str, message: str, level: str) -> "StrictDiagnostic":
    """Build the canonical :class:`StrictDiagnostic` from this module's
    ``(phase, field, message, level)`` call shape, keeping every call site
    below unchanged in argument order. ``code`` is the generic
    ``"run_validation"`` -- none of these sites carries a more specific one.
    """
    return diagnostic(level, "run_validation", message, source=phase, field=field)


def _catalogued(driver_path: str, value: Any) -> bool:
    """Whether the catalogue lists ``value`` in ``driver_path``'s menu. A rule
    that compares a name refuses only a name it knows: one the catalogue
    lacks may be a model the scan registered, and is never refused here."""
    from .record_key_validation import _ELECTRO_ENTRIES_BY_PATH

    entry = _ELECTRO_ENTRIES_BY_PATH.get(driver_path)
    return entry is not None and value in entry.enum_values


_CONDUCTION_SOLVER_SUFFIX = ".purkinjeGraphModelCoeffs.conductionSystemSolver"
_COUPLER_SUFFIX = ".electroDomainCoupler"
_NETWORK_REF_SUFFIX = ".conductionNetworkDomain"
_CONDUCTION_NET_PREFIX = "conductionNetworkDomains."
_DOMAIN_COUPLINGS_PREFIX = "domainCouplings."


def _evaluate_solver_coupling(context: dict[str, Any]) -> list["StrictDiagnostic"]:
    """Validate each explicit coupling against its referenced network.

    Network creation alone does not imply a coupling. Match the C++ system
    builder's conductionNetworkDomain lookup rather than borrowing whichever
    network selector happens to appear first in the flattened context.
    """
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
    """Names of every conductionNetworkDomains.<name> block that has at
    least one sub-key present in context."""
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

        # gradientAxes is a dynamic-name dictionary (native 3025230b9): more
        # than one named axis (e.g. apicobasal, longitudinal) can compose on
        # the same run, each validated independently.
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
            # deliberately not checked here -- the old "beta must be > 0"
            # check was never backed by a native read and is dropped, not
            # carried over, with the apexBaseBands -> gradientAxes rename.
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
    """Validate an explicitly selected eikonalECG template-generation block.

    The block is intentionally optional: eikonalECG otherwise uses compiled
    templates.  Its all-or-nothing contents and its relationship to a
    manufactured verifier are solver science, not generic dictionary rules.
    This mirrors constructor checks in ``eikonalECG.C`` before a run starts.

    A case selects its verifier only through
    ``ecgVerificationModel``/``verificationModel.type``; the native
    ``manufacturedEikonalECG.`` legacy alias key does not exist, so no
    context built from a real case can hold it.
    """
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

        required = (
            "ionicModelConfig.ionicModel", "nBeats", "duration", "dt",
            "ionicModelConfig.singleCellStimulus.stim_start",
            "ionicModelConfig.singleCellStimulus.stim_period_S1",
            "ionicModelConfig.singleCellStimulus.stim_duration",
            "ionicModelConfig.singleCellStimulus.stim_amplitude",
        )
        for suffix in required:
            key = template_prefix + suffix
            if context.get(key) in (None, ""):
                errors.append(_diagnostic_from_phase(
                    phase="physics", field=key,
                    message=f"{key} is required when personalizedTemplates is configured.",
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
    """Interpret an OpenFOAM ``Switch``-shaped value as a Python bool.

    ``value`` is either a real ``foamlib``-parsed string (``"yes"``/``"no"``/
    ``"true"``/``"false"``, possibly quoted) or, in a unit test's literal
    context dict, a plain Python ``bool``. Anything else (missing, ``None``)
    reads as ``False`` -- the native default
    (``manufacturedPseudoECGVerifier.C:420``,
    ``cfg.lookupOrDefault<Switch>("anisotropic", false)``).
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().strip('"').lower()
    return text in {"yes", "true", "on", "y", "t", "1"}


def _evaluate_ecg_anisotropic_consistency(context: dict[str, Any]) -> list["StrictDiagnostic"]:
    """``ecgDomains.<name>.verificationModel.anisotropic`` must state the same
    relation the tissue verifier already states, in both directions.

    Native ``manufacturedPseudoECGVerifier`` reads its own ``anisotropic``
    ``Switch`` (default ``false``,
    ``src/verificationModels/ecgVerification/manufacturedPseudoECGVerifier.C``,
    ``readVerificationModel``) to choose which of two reference branches --
    the isotropic FDA cosine field or the anisotropic
    ``sin^2(pi x)*sin^2(pi y)*sin^2(pi z)`` field -- its samples are checked
    against. That choice has to agree with the *tissue*-side verifier
    actually driving the solve
    (``$ELECTRO_MODEL_COEFFS.verificationModel.type``): ``anisotropic yes``
    is correct exactly when the tissue verifier is
    ``manufacturedAnisotropicMonodomainVerifier``, and wrong -- a silently
    mismatched reference -- otherwise, in either direction. This models the
    relation between the two existing keys; it adds no new key.

    Scoped to domains whose own ``ecgDomains.<name>.verificationModel.type``
    is ``manufacturedPseudoECGVerifier``: native only reads ``anisotropic``
    there (``manufacturedEikonalECGVerifier``/``manufacturedFDABathBidomain
    ECGVerifier`` do not declare the key at all -- ``grep -rl anisotropic
    src/verificationModels/ecgVerification/`` finds only the pseudo-ECG
    verifier's ``.C``/``.H`` pair), matching this catalog entry's own
    ``applicable_when``.
    """
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


def _graph_has_terminal_resistances(graph_path: Any) -> bool:
    """Whether a materialized Purkinje graph file carries a non-empty
    top-level ``pvjResistances`` list (``conductionGraph::readFromDict``
    reads it as an optional scalar list). foamlib parses without evaluating
    ``#calc``/``#codeStream``, so it is safe on a file this module did not
    write."""
    from foamlib import FoamFile

    try:
        resistances = FoamFile(graph_path).get("pvjResistances")
    except (OSError, ValueError):
        return False
    if resistances is None:
        return False
    try:
        return len(resistances) > 0
    except TypeError:
        return bool(resistances)


def _evaluate_pvj_resistance_requirement(
    case_root: Path, context: dict[str, Any], electro_path: Path,
) -> list["StrictDiagnostic"]:
    """``reactionDiffusionPvjCoupler`` reads ``rPvj`` only when its graph's
    ``terminalResistances()`` is null (``reactionDiffusionPvjCoupler.C``), so
    the catalogue cannot state it as a ``required_when``: it depends on a
    file. A graph not yet materialized defers the check; a materialized one
    with no ``pvjResistances`` and no ``rPvj`` is an error."""
    found: list["StrictDiagnostic"] = []
    for key, coupler in context.items():
        if not (key.startswith(_DOMAIN_COUPLINGS_PREFIX) and key.endswith(_COUPLER_SUFFIX)) or coupler != _RPVJ_COUPLER:
            continue
        block = key[: -len(_COUPLER_SUFFIX)]
        network = context.get(block + _NETWORK_REF_SUFFIX)
        rpvj_key = f"{block}.rPvj"
        if network is None or rpvj_key in context:
            continue
        graph_name = context.get(
            f"{_CONDUCTION_NET_PREFIX}{network}.purkinjeGraphModelCoeffs.graphFile"
        )
        if graph_name is None:
            continue
        graph_path = case_root / "constant" / str(graph_name)
        if not graph_path.exists() or _graph_has_terminal_resistances(graph_path):
            continue
        found.append(diagnostic(
            "error", "missing_rpvj",
            (
                f"conductionNetworkDomains.{network} is coupled via {_RPVJ_COUPLER} ({block}) "
                f"but neither rPvj nor a graph-provided pvjResistances list is available: the "
                f"materialized graph file {graph_name!r} has no pvjResistances, and rPvj is not "
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


def case_diagnostics(case_root: Path) -> tuple["StrictDiagnostic", ...]:
    """Every rule the resolved case at ``case_root`` violates. A case with no
    ``electroProperties`` violates none."""
    from foamlib import FoamFile

    from omnidriver.openfoam.case_rules import flatten, rule_diagnostics

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
    document = electro_path.relative_to(case_root).as_posix()
    return tuple(
        rule_diagnostics(_ELECTRO_ENTRIES_BY_PATH.values(), context, document=document)
        + cross_field_diagnostics(context)
        + _evaluate_pvj_resistance_requirement(case_root, context, electro_path)
    )
