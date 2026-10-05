"""Build a runnable cardiacFoam case from the dict-entry catalogue, for when there is no native case to run.

``build_case`` writes and rule-checks the whole case; ``build`` is the ``omnidriver build`` entry point.
"""
from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from omnidriver.core.contracts.catalogue_paths import PLACEHOLDER, slot_key
from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.planning_types import diagnostic
from omnidriver.openfoam.case_builder import (
    default_block_mesh_dict_text,
    populate_values,
    serialize_block,
    set_nested,
    single_cell_block_mesh_dict_text,
    value_token,
    write_documents,
)
from omnidriver.openfoam.case_rules import applicable_entries, forbidden_in, match_dynamic_entry, rule_diagnostics
from omnidriver.openfoam.control_dict import CONTROL_DICT_DOCUMENT, CONTROL_DICT_ENTRIES
from omnidriver.openfoam.literals import BOOLEAN_WORDS, parse_vector3_literal
from omnidriver.openfoam.plan_diagnostics import cxx_source_not_supplied
from omnidriver.openfoam.record_key_validation import scanned_key

from .common_dict_entries import PHYSICS_PROPERTY_ENTRIES
from .dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from .record_key_validation import cardiacfoam_mapping
from .validation import cross_field_diagnostics, infer_virtual_presence

PLUGIN_ID = "org.cardiacfoam"

_ELECTRO_DOCUMENT = "constant/electroProperties"
_PHYSICS_DOCUMENT = "constant/physicsProperties"

#: No spatial geometry to size a mesh from: these get a fixed one-cell
#: ``blockMeshDict`` and refuse ``dx``.
SINGLE_CELL_SOLVERS = frozenset({"singleCellSolver"})


def _all_electro_entries() -> list[DictEntry]:
    ordered_keys = [
        "top_level",
        "common_model_coeffs",
        "monodomain",
        "bidomain",
        "bath_potential_domain",
        "eikonal_diffusion",
        "ionic_heterogeneity",
        "ionic_constant_overrides",
        "batched_integrator",
        "active_tension",
        "ode_solver_passthrough",
        "single_cell_stimulus",
        "conduction_system",
        "domain_couplings",
        "ecg"
    ]
    out: list[DictEntry] = []
    groups = ELECTRO_PROPERTY_ENTRY_GROUPS
    for k in ordered_keys:
        if k in groups:
            out.extend(groups[k])
    for k, group in groups.items():
        if k not in ordered_keys:
            out.extend(group)
    return out


def resolve_context(
    selectors: dict[str, str],
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Collapse selectors + overrides into a single `{slot_key: value}` dict.

    Selectors enter at their raw key (`myocardiumSolver`, `ionicModel`, ...);
    overrides go through `slot_key`, which strips the `$ELECTRO_MODEL_COEFFS.`
    prefix. Virtual presence keys are inferred, so a block's `applicable_when`
    fires only when overrides under that block were declared.
    """
    ctx: dict[str, Any] = dict(selectors)
    if overrides:
        for driver_path, value in overrides.items():
            ctx[slot_key(driver_path)] = value
    if ctx.get("myocardiumSolver") in {
        "monodomainSolver", "eikonalSolver", "bidomainSolver"
    }:
        ctx.setdefault("conductivitySource", "uniform")
    infer_virtual_presence(ctx)
    return ctx


def select_applicable_entries(
    context: dict[str, Any],
    *,
    entries: list[DictEntry] | None = None,
) -> list[DictEntry]:
    """The entries whose ``applicable_when`` holds in ``context`` and whose
    ``forbidden_when`` does not, from ``entries`` or every electroProperties
    entry."""
    return applicable_entries(entries if entries is not None else _all_electro_entries(), context)


_FOAM_BANNER = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v1912                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "{location}";
    object      {object_name};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""


def _foam_header(location: str, object_name: str) -> str:
    return _FOAM_BANNER.format(location=location, object_name=object_name)


def _with_virtual_presence(values: dict[str, str]) -> dict[str, Any]:
    context: dict[str, Any] = dict(values)
    infer_virtual_presence(context)
    return context


def _check_no_forbidden_selectors(context: dict[str, Any]) -> None:
    """Raise ValueError for a key the caller set that the context forbids."""
    for entry, predicate in forbidden_in(_all_electro_entries(), context):
        raise ValueError(
            f"build_electro_properties: '{slot_key(entry.driver_path)}' is forbidden when "
            + ", ".join(f"{key}={context.get(slot_key(key))!r}" for key in predicate) + "."
        )


def _typed(text: str) -> Any:
    """The value an override's text reads as: a Switch word, JSON, an OpenFOAM vector, else the word."""
    if text in BOOLEAN_WORDS:
        return BOOLEAN_WORDS[text]
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        return list(parse_vector3_literal(text))
    except ValueError:
        return text


def uncatalogued_entries(overrides: Mapping[str, str] | None) -> tuple[DictEntry, ...]:
    """An entry for each override the catalogue lacks that the supplied C++
    reads at exactly that path, of the kind the C++ reads.

    Raises:
        ValueError: an override neither the catalogue nor the C++ places, a
            value the C++ would not read, or no C++ source supplied."""
    catalogued = _all_electro_entries()
    by_path = {entry.driver_path for entry in catalogued}
    entries = []
    for path, value in (overrides or {}).items():
        if path in by_path or match_dynamic_entry(path, catalogued) is not None:
            continue
        try:
            kind, _ = scanned_key(
                _ELECTRO_DOCUMENT, tuple(path.split(".")), _typed(value), mapping=cardiacfoam_mapping(), entries=catalogued,
            )
        except KeyError as exc:
            raise ValueError(f"build_electro_properties: {path!r} is not in the catalogue, and {exc.args[0]}") from None
        entries.append(DictEntry(
            driver_path=path, value_kind=kind, description="read by the supplied C++; the catalogue lacks it",
        ))
    return tuple(entries)


def build_electro_properties(
    selectors: dict[str, str],
    *,
    overrides: dict[str, str] | None = None,
    typical_value_fallback: bool = True,
    uncatalogued: tuple[DictEntry, ...] = (),
) -> str:
    """Synthesise a complete `electroProperties` dict from intent.

    Args:
        selectors: top-level discriminators (myocardiumSolver, ionicModel,
            tissue, ...). Required keys depend on the chosen solver.
        overrides: full driver_path → value mappings for entries whose
            `typical_value` is not appropriate.
        typical_value_fallback: when True (default), applicable entries
            with no override fall back to `DictEntry.typical_value` if
            declared. When False, only explicit overrides count.
        uncatalogued: the entries :func:`uncatalogued_entries` made for
            overrides the catalogue lacks; they are written like any other.

    Returns:
        OpenFOAM-format text including the standard `FoamFile` preamble.

    Raises:
        ValueError: required+applicable entry has no value, mutex violation,
            an override no applicable catalogue entry places, or any catalogue
            relation `case_rules` finds violated.
    """
    context = resolve_context(selectors, overrides=overrides)

    # Pre-check: if the caller explicitly provides a key that is forbidden
    # in this context, reject immediately rather than silently ignoring it.
    _check_no_forbidden_selectors(context)

    entries = [*select_applicable_entries(context), *uncatalogued]
    populated = populate_values(
        entries, context, typical_value_fallback=typical_value_fallback,
    )

    unplaced = [path for path in overrides or () if slot_key(path) not in populated]
    if unplaced:
        raise ValueError(
            f"build_electro_properties: {unplaced} match no applicable catalogue entry, so the "
            f"builder cannot place them; `omnidriver catalog --uncatalogued` lists what the C++ "
            f"reads and the catalogue lacks"
        )

    populated_values = {key: value for key, value in populated.items() if value not in (None, "")}
    errors = [
        e for e in (
            *rule_diagnostics(entries, _with_virtual_presence(populated_values), document=_ELECTRO_DOCUMENT),
            *cross_field_diagnostics(populated_values),
        ) if e.level == "error"
    ]
    if errors:
        raise ValueError(
            "build_electro_properties: validator rejected synthesised dict:\n  - "
            + "\n  - ".join(e.message for e in errors)
        )

    body = _serialize(populated, entries, selectors["myocardiumSolver"])
    return _foam_header("constant", "electroProperties") + "\n" + body


_COEFFS_PREFIX = "$ELECTRO_MODEL_COEFFS."


def _serialize(
    populated: dict[str, str],
    entries: list[DictEntry],
    myocardium_solver: str,
) -> str:
    """The dict body: top-level keys at the root, `$ELECTRO_MODEL_COEFFS.` keys under `<solver>Coeffs`."""
    top_level: dict[str, str] = {}
    coeffs: dict = {}

    dynamic_patterns = []
    for entry in entries:
        if getattr(entry, "dynamic_path", False):
            template = slot_key(entry.driver_path)
            # Same generic placeholder rule as the population pass: an entry
            # that fails to match its own catalogue entry routes to top_level
            # and emits a $ELECTRO_MODEL_COEFFS.* key at the electroProperties
            # root, where the solver never reads it.
            pattern = PLACEHOLDER.sub(r"([^.]+)", re.escape(template))
            dynamic_patterns.append((entry, re.compile(f"^{pattern}$")))

    for concrete_key, value in populated.items():
        matched_entry = None
        for entry in entries:
            if not getattr(entry, "dynamic_path", False):
                if slot_key(entry.driver_path) == concrete_key:
                    matched_entry = entry
                    break

        if not matched_entry:
            for entry, regex in dynamic_patterns:
                if regex.match(concrete_key):
                    matched_entry = entry
                    break

        if matched_entry and matched_entry.driver_path.startswith(_COEFFS_PREFIX):
            segments = concrete_key.split(".")
            set_nested(coeffs, segments, value)
        else:
            top_level[concrete_key] = value

    parts: list[str] = []
    for key, value in top_level.items():
        parts.append(f"{key} {value_token(value)};")
    if coeffs:
        coeffs_scope = f"{myocardium_solver}Coeffs"
        parts.append("")
        parts.append(coeffs_scope)
        parts.append("{")
        parts.append(serialize_block(coeffs, indent=4))
        parts.append("}")
    parts.append("")
    return "\n".join(parts)


def build_physics_properties(
    selectors: dict[str, str],
    *,
    overrides: dict[str, str] | None = None,
    typical_value_fallback: bool = True,
) -> str:
    """Synthesise a complete `physicsProperties` dict from intent.

    Mirrors :func:`build_electro_properties` against
    :data:`PHYSICS_PROPERTY_ENTRIES`; every physics key lives at the dict
    root, with no ``<solver>Coeffs`` wrapper.

    Args:
        selectors: top-level physics keys (e.g. ``{"type": "electroModel"}``).
        overrides: full driver_path → value mappings for future expansion.
        typical_value_fallback: when True, applicable entries with no
            override fall back to ``DictEntry.typical_value`` if declared.

    Returns:
        OpenFOAM-format text with a ``physicsProperties``-typed FoamFile
        preamble.

    Raises:
        ValueError: required entry has no value, or any structured
            relation `case_rules` finds violated.
    """
    context = resolve_context(selectors, overrides=overrides)
    entries = applicable_entries(PHYSICS_PROPERTY_ENTRIES, context)
    populated = populate_values(
        entries, context, typical_value_fallback=typical_value_fallback,
    )

    errors = [
        e for e in rule_diagnostics(entries, populated, document=_PHYSICS_DOCUMENT)
        if e.level == "error"
    ]
    if errors:
        raise ValueError(
            "build_physics_properties: validator rejected synthesised dict:\n  - "
            + "\n  - ".join(e.message for e in errors)
        )

    # Physics keys are root-level — no <solver>Coeffs wrapper.
    body_lines: list[str] = []
    for entry in entries:
        key = slot_key(entry.driver_path)
        if key in populated:
            body_lines.append(f"{key} {populated[key]};")
    body = "\n".join(body_lines) + "\n"
    return _foam_header("constant", "physicsProperties") + "\n" + body


# --------------------------------------------------------------------------
# System dictionaries
# --------------------------------------------------------------------------

_END_RULE = "// ************************************************************************* //\n"


def _block(name: str, lines: list[str]) -> str:
    return f"{name}\n{{\n" + "".join(f"    {line}\n" for line in lines) + "}\n\n"


def _fv_schemes(solver: str) -> str:
    """The discretisation for each field family a ``myocardiumSolver`` solves (``Vm``, with ``psi`` or ``phiE``)."""
    if "singleCell" in solver:
        ddt = ["default         backward; // 2nd order"]
        grad = "leastSquares"
        div = ["default         none;", "div(phiU,psi)   Gauss linear;"]
    else:
        ddt = ["default         none;", "ddt(Vm)         backward;"]
        grad = "Gauss linear"
        div = ["default         none;"]
        if "bidomain" in solver.lower():
            div += [
                "div((conductivityIntracellular&grad(Vm))) Gauss linear;",
                "div((conductivityIntracellular&grad(phiE))) Gauss linear;",
            ]
    return (
        _foam_header("system", "fvSchemes") + "\n"
        + _block("ddtSchemes", ddt)
        + _block("gradSchemes", [f"default         {grad};"])
        + _block("divSchemes", div)
        + _block("laplacianSchemes", ["default         Gauss linear corrected;"])
        + _block("interpolationSchemes", ["default         linear;"])
        + _block("snGradSchemes", ["default         corrected;"])
        + _END_RULE
    )


def _solver_group(fields: str, tolerance: str, rel_tol: str) -> str:
    return (
        f'    "{fields}"\n    {{\n        solver          PCG;\n        preconditioner  DIC;\n'
        f"        tolerance       {tolerance};\n        relTol          {rel_tol};\n    }}\n"
    )


def _fv_solution(solver: str) -> str:
    if "singleCell" in solver:
        solvers = (
            _solver_group("Vm|VmFinal|u|uFinal", "1e-11", "0.0") + "\n"
            + _solver_group("psi|psiFinal", "1e-11", "0.1")
        )
        rest = (
            "PIMPLE\n{\n    nOuterCorrectors    1000;\n\n    residualControl\n    {\n"
            '        "Vm|psi"\n        {\n            relTol          0.0;\n'
            "            tolerance       1e-6;\n        }\n    }\n}\n\n"
            + _block("relaxationFactors", ["equations\n    {\n        psi    0.9;\n    }"])
        )
    else:
        solvers = _solver_group("Vm|VmFinal|u|uFinal", "1e-15", "0.0")
        if "bidomain" in solver.lower():
            solvers += "\n" + _solver_group("phiE|phiEFinal|phiI|phiIFinal", "1e-15", "0.0")
        rest = "PIMPLE\n{\n    nOuterCorrectors     2;\n}\n\n"
    return _foam_header("system", "fvSolution") + "\nsolvers\n{\n" + solvers + "}\n\n" + rest + _END_RULE


def _control_dict(delta_t: float, end_time: float) -> str:
    """The ``controlDict`` text, held to ``Foam::Time``'s catalogue rules before it is written."""
    leaves = {
        "startFrom": "startTime", "startTime": 0, "stopAt": "endTime", "endTime": end_time, "deltaT": delta_t,
        "writeControl": "runTime", "writeInterval": min(0.1, end_time), "purgeWrite": 0, "writeFormat": "ascii",
    }
    broken = [item.message for item in rule_diagnostics(CONTROL_DICT_ENTRIES, leaves, document=CONTROL_DICT_DOCUMENT)]
    if end_time <= leaves["startTime"]:
        broken.append(f"endTime is {end_time!r}, not after the startTime {leaves['startTime']} the built case starts from.")
    if broken:
        raise ValueError("build_case: the controlDict breaks:\n  - " + "\n  - ".join(broken))
    return (
        _foam_header("system", "controlDict")
        + f"""
application     cardiacFoam;

startFrom       {leaves['startFrom']};
startTime       {leaves['startTime']};
stopAt          {leaves['stopAt']};
endTime         {end_time};
deltaT          {delta_t};

writeControl    {leaves['writeControl']};
writeInterval   {leaves['writeInterval']};
purgeWrite      {leaves['purgeWrite']};
writeFormat     {leaves['writeFormat']};
writePrecision  6;
writeCompression off;

timeFormat      general;
timePrecision   6;
runTimeModifiable false;

"""
        + _END_RULE
    )


# --------------------------------------------------------------------------
# The build
# --------------------------------------------------------------------------

#: What a case that already holds `system/` keeps, unless the caller asked to overwrite.
_KEPT_UNLESS_OVERWRITTEN = frozenset({"system/blockMeshDict", "system/fvSchemes", "system/fvSolution", "system/controlDict"})

_OPTIONS = {"dx": "isotropic cell size of the default mesh, metres", "deltaT": "time step, s", "endTime": "end time, s"}


def build_case(
    electro_selectors: dict[str, str],
    *,
    physics_selectors: dict[str, str] | None = None,
    case_dir: Path,
    electro_overrides: dict[str, str] | None = None,
    overwrite: bool = False,
    delta_t: float = 1e-4,
    end_time: float = 1.0,
    dx: float | None = None,
    driver_context: Any,
) -> dict[str, Any]:
    """Write a runnable case into ``case_dir`` and judge it by the pre-run
    rules a record's case passes.

    Writes ``constant/electroProperties`` and ``physicsProperties``,
    ``system/fvSchemes``, ``fvSolution``, ``controlDict``, ``blockMeshDict``
    and an ``Allrun`` (``blockMesh`` then ``cardiacFoam``); a ``system/``
    file the directory already holds is kept unless ``overwrite``. The mesh is
    a generic slab, sized by ``dx`` (metres); a single-cell solver gets one
    cell and refuses ``dx``.

    Raises:
        FileExistsError: ``case_dir`` holds an ``electroProperties`` and
            ``overwrite`` is false.
        ValueError: a selector or override the catalogue's rules reject, or
            ``dx`` for a single-cell solver.

    Returns ``status`` (``ok``, or ``failed`` when the written case breaks a
    rule), the written ``files`` and the rule ``diagnostics``.
    """
    case_dir = Path(case_dir).resolve()
    if (case_dir / _ELECTRO_DOCUMENT).exists() and not overwrite:
        raise FileExistsError(f"{case_dir / _ELECTRO_DOCUMENT} already exists; pass --overwrite to replace it")
    solver = electro_selectors.get("myocardiumSolver", "monodomainSolver")
    single_cell = solver in SINGLE_CELL_SOLVERS
    if single_cell and dx is not None:
        raise ValueError(f"dx has no effect for myocardiumSolver={solver!r}: it has no geometry for dx to resolve")
    uncatalogued = uncatalogued_entries(electro_overrides)
    electro_text = build_electro_properties(electro_selectors, overrides=electro_overrides, uncatalogued=uncatalogued)
    record = write_documents(
        case_dir,
        {
            _ELECTRO_DOCUMENT: electro_text,
            _PHYSICS_DOCUMENT: build_physics_properties(physics_selectors or {"type": "electroModel"}),
            "system/fvSchemes": _fv_schemes(solver),
            "system/fvSolution": _fv_solution(solver),
            "system/controlDict": _control_dict(delta_t, end_time),
            "system/blockMeshDict": (
                single_cell_block_mesh_dict_text() if single_cell else default_block_mesh_dict_text(dx_m=dx)
            ),
            "Allrun": "#!/bin/sh\nblockMesh\ncardiacFoam\n",
        },
        owner_id=PLUGIN_ID,
        source_artifacts=(f"cardiacfoam.dict_entries:electro:{solver}", "cardiacfoam.dict_entries:physics"),
        driver_context=driver_context,
        executable=frozenset({"Allrun"}),
        keep_existing=_KEPT_UNLESS_OVERWRITTEN if not overwrite else frozenset({"system/blockMeshDict"}),
    )
    found = list(driver_context.stack.call("validate_run_semantics", case_dir))
    found += [diagnostic(
        "info", "plugin_catalog_uncatalogued",
        f"{entry.driver_path} is not in the catalogue; the supplied C++ reads it as {entry.value_kind}, "
        "so it is written as asked (omnidriver catalog --uncatalogued lists every read the catalogue lacks)",
        field=entry.driver_path,
    ) for entry in uncatalogued]
    mapping = cardiacfoam_mapping()
    if mapping.source_root(os.environ) is None:
        found.append(cxx_source_not_supplied(mapping, source=driver_context.identity.resolutions["get_profile"]))
    return {
        "status": "failed" if any(item.level == "error" for item in found) else "ok",
        "case_dir": str(case_dir),
        "files": list(record.committed),
        "diagnostics": [
            {"level": item.level, "code": item.code, "field": item.field, "message": item.message} for item in found
        ],
    }


def build(
    driver_context: Any,
    out: Path,
    *,
    select: Mapping[str, str],
    set_values: Mapping[str, str],
    options: Mapping[str, str],
    overwrite: bool,
) -> dict[str, Any]:
    """``omnidriver build`` for cardiacFoam. ``select`` holds the discriminators
    (``myocardiumSolver``, ``ionicModel``, ``tissue``, ``conductivitySource``)
    and ``type`` for physicsProperties (default ``electroModel``);
    ``set_values`` maps catalogue driver paths to values; ``options`` may carry
    ``dx``, ``deltaT`` and ``endTime``."""
    unknown = sorted(set(options) - set(_OPTIONS))
    if unknown:
        raise ValueError(f"unknown build option(s) {unknown}; cardiacFoam takes {_OPTIONS}")
    electro = dict(select)
    physics = {"type": electro.pop("type", "electroModel")}
    return build_case(
        electro, physics_selectors=physics, case_dir=out, electro_overrides=dict(set_values) or None,
        overwrite=overwrite, driver_context=driver_context,
        **{name: float(options[key]) for name, key in (("dx", "dx"), ("delta_t", "deltaT"), ("end_time", "endTime")) if key in options},
    )
