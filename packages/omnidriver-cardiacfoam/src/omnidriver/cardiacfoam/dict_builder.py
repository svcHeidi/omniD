#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     plugins.cardiacfoam.dict_builder
#
# Description
#     cardiacFoam-specific dictionary synthesis: `constant/electroProperties`
#     and `constant/physicsProperties`. Composites solver-neutral
#     dict-building primitives (entry selection, value population, OpenFOAM
#     block emission, value quoting) from `specs/dict_builder.py`.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Scratch-construct cardiacFoam dictionary files from agent intent.

`build_electro_properties` synthesises a complete `constant/electroProperties`
text from selectors + overrides. The pipeline reuses the existing dict-entry
catalog (`dict_entries.py`), the structured-constraint validator
(`validation.py`), and the path conventions encoded in `slot_key`.

The builder composes existing primitives. Every output passes through `validate_run`
before being returned; an agent that gets a string back is guaranteed it
is validator-clean.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Integral, Real
from typing import Any

from omnidriver.dict_entries import DictEntry
from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups
from omnidriver.openfoam.dict_builder import (
    _PLACEHOLDER_RE,
    _openfoam_value_token,
    _populated_to_run,
    _serialize_block,
    _set_nested,
    populate_values,
)
from omnidriver.openfoam.dict_builder import (
    select_applicable_entries as _select_applicable_entries,
)
from omnidriver.cardiacfoam.own_context import own_driver_context
from omnidriver.core.case_write import CaseMutationRequest, ParameterAssignment, ResolvedMutation
from omnidriver.core.specs.validation import (
    _predicate_matches,
    slot_key,
    validate_run,
)

from .common_dict_entries import PHYSICS_PROPERTY_ENTRIES

#: This adapter's identity on every synthesis request and resolution it
#: produces (Phase 2 Task 9).
PLUGIN_ID = "org.cardiacfoam"

#: The one format `resolve_synthesis_mutation`'s targets declare. Rendered by
#: `OpenFOAMEnvironmentPlugin` -- see `openfoam/case_rendering.py`.
_SYNTHESIS_FORMAT = "openfoam_dictionary"

_ELECTRO_DOCUMENT = "constant/electroProperties"
_PHYSICS_DOCUMENT = "constant/physicsProperties"
_FV_SCHEMES_DOCUMENT = "system/fvSchemes"
_FV_SOLUTION_DOCUMENT = "system/fvSolution"
_CONTROL_DOCUMENT = "system/controlDict"
_BLOCK_MESH_DOCUMENT = "system/blockMeshDict"

#: Not a real case document -- carries `build_and_launch`'s `overwrite` flag
#: as a reconstructable parameter so `resolve_synthesis_mutation` stays pure
#: (everything it needs comes from `request.parameters`, nothing from a
#: side channel), without inventing a file for a flag that has none. Never
#: becomes a target/`RenderedFile`; `ParameterAssignment.document` only
#: requires a case-relative string, which this satisfies without being read
#: or written by anything.
_SYNTHESIS_META_DOCUMENT = "_meta/synthesis"

#: `qualified_id` prefixes distinguishing a selector parameter (a top-level
#: discriminator such as `myocardiumSolver`) from an override parameter (an
#: arbitrary catalog `driver_path`, whose value replaces a specific entry's
#: `typical_value`) landing on the same document -- see
#: `_selector_parameters`/`_override_parameters` and their inverse,
#: `resolve_synthesis_mutation`.
_ELECTRO_SELECTOR_PREFIX = "$CARDIACFOAM.electro_selector."
_PHYSICS_SELECTOR_PREFIX = "$CARDIACFOAM.physics_selector."


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
    groups = get_electro_property_entry_groups(own_driver_context())
    for k in ordered_keys:
        if k in groups:
            out.extend(groups[k])
    for k, group in groups.items():
        if k not in ordered_keys:
            out.extend(group)
    return out


# Block-presence virtual keys auto-inferred from override prefixes.
# When an agent declares any override under `bathPotentialDomain.*`,
# `ecgDomains.*`, or `conductionNetworkDomains.*`, the dict_builder sets
# the corresponding `$..._present`/`$..._configured` virtual key on the
# resolved context. Entries gated by `applicable_when={"$..._...": True}`
# then become visible and their typical_value fallbacks fire. Without an
# override under one of these prefixes the block stays off — plain
# bidomain does not get bath leaves leaking in.
_VIRTUAL_PRESENCE_TRIGGERS: tuple[tuple[str, str], ...] = (
    ("bathPotentialDomain.", "$bathPotentialDomain_configured"),
    ("ecgDomains.", "$ecgDomains_present"),
    ("conductionNetworkDomains.", "$conductionNetworkDomains_present"),
    # A single-cell run with no stimulus is legal: stimulusIO.C:149-155
    # returns a no-op protocol when the sub-dict is absent. Gating the
    # stimulus family on presence rather than on myocardimSolver keeps the
    # builder from inventing stim_amplitude/nstim1 defaults and quietly
    # pacing a case that asked for none.
    ("singleCellStimulus.", "$singleCellStimulus_present"),
)


def _infer_virtual_presence(ctx: dict[str, Any]) -> None:
    """Set block-presence virtual keys in-place on `ctx` whenever any
    real slot_key starts with one of the documented block prefixes.
    Idempotent and safe to call after the override merge."""
    for prefix, virtual_key in _VIRTUAL_PRESENCE_TRIGGERS:
        if virtual_key in ctx:
            continue
        for existing_key in ctx:
            if existing_key.startswith(prefix):
                ctx[virtual_key] = True
                break

    # Support OR logic for ionicHeterogeneity applicability
    from omnidriver.cardiacfoam.dict_entries import get_heterogeneity_models
    if (
        ctx.get("myocardiumSolver") == "eikonalSolver"
        or ctx.get("ionicModel") in get_heterogeneity_models(own_driver_context())
    ):
        ctx["$ionicHeterogeneity_supported"] = True


def resolve_context(
    selectors: dict[str, str],
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Collapse selectors + overrides into a single `{slot_key: value}` dict.

    Selectors enter at their raw key (`myocardiumSolver`, `ionicModel`, ...);
    overrides go through `slot_key` so the `$ELECTRO_MODEL_COEFFS.` prefix
    is stripped. This is the same context shape `validation._flatten_context`
    produces from a Run document — so the validator can be reused unchanged.

    Also infers virtual presence keys (`$bathPotentialDomain_configured`,
    `$ecgDomains_present`, `$conductionNetworkDomains_present`) so the
    matching `applicable_when` predicates fire only when the agent has
    actually declared overrides under the corresponding block.
    """
    ctx: dict[str, Any] = dict(selectors)
    if overrides:
        for driver_path, value in overrides.items():
            ctx[slot_key(driver_path)] = value
    if ctx.get("myocardiumSolver") in {
        "monodomainSolver", "eikonalSolver", "bidomainSolver"
    }:
        ctx.setdefault("conductivitySource", "uniform")
    _infer_virtual_presence(ctx)
    return ctx


def select_applicable_entries(
    context: dict[str, Any],
    *,
    entries: list[DictEntry] | None = None,
) -> list[DictEntry]:
    """Cardiac-catalog default for `specs.dict_builder.select_applicable_entries`.

    Identical filtering semantics; the only difference is that omitting
    `entries` selects from every electroProperties entry rather than
    requiring the caller to name a pool. The core predicate helper is
    solver-neutral and takes its pool explicitly."""
    pool = entries if entries is not None else _all_electro_entries()
    return _select_applicable_entries(context, entries=pool)


def _foamfile_preamble(object_name: str) -> str:
    """Standard FoamFile preamble for a given `object` value.

    The object name distinguishes the two dict files this module writes —
    `electroProperties` vs `physicsProperties`. Future dict targets follow
    the same pattern.
    """
    return (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "| =========                 |                                                 |\n"
        "| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n"
        "|  \\\\    /   O peration     | cardiacFoam dict_builder synthesis              |\n"
        "|   \\\\  /    A nd           |                                                 |\n"
        "|    \\\\/     M anipulation  |                                                 |\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n"
        "{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        "    class       dictionary;\n"
        "    location    \"constant\";\n"
        f"    object      {object_name};\n"
        "}\n"
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n"
    )


# Backwards-compat alias — some callers and tests reference this name.
_FOAMFILE_PREAMBLE = _foamfile_preamble("electroProperties")


def _check_no_forbidden_selectors(context: dict[str, Any]) -> None:
    """Raise ValueError if the caller explicitly set a key that is forbidden
    in the current context.  'Explicitly set' means the slot key appears in
    *context* — i.e., the caller passed it as a selector or override."""
    for entry in _all_electro_entries():
        if not entry.forbidden_when:
            continue
        key = slot_key(entry.driver_path)
        if key not in context:
            continue
        for pred_key, expected in entry.forbidden_when.items():
            if _predicate_matches(context, pred_key, expected):
                raise ValueError(
                    f"build_electro_properties: '{key}' is forbidden when "
                    f"{pred_key}={context.get(pred_key)!r}."
                )


def build_electro_properties(
    selectors: dict[str, str],
    *,
    overrides: dict[str, str] | None = None,
    typical_value_fallback: bool = True,
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

    Returns:
        OpenFOAM-format text including the standard `FoamFile` preamble.

    Raises:
        ValueError: required+applicable entry has no value, mutex violation,
            or any structured-constraint violation from `validate_run`.
    """
    context = resolve_context(selectors, overrides=overrides)

    # Pre-check: if the caller explicitly provides a key that is forbidden
    # in this context, reject immediately rather than silently ignoring it.
    _check_no_forbidden_selectors(context)

    entries = select_applicable_entries(context)
    populated = populate_values(
        entries, context, typical_value_fallback=typical_value_fallback,
    )

    # Safety net: run the full validator scoped to electro entries only.
    # The validator now subsumes required-field checks (its section 1
    # honours `required_when` + `dynamic_path` the same way `check_required`
    # does), so we don't pre-call `check_required` from the public builder
    # entry-point. `check_required` stays exported for callers that want
    # just the required-field subset.
    context_ = own_driver_context()
    run = _populated_to_run(
        populated, entries, context_.capabilities.dictionaries.phases(),
    )
    errors = [e for e in validate_run(run, entries=entries, driver_context=context_) if e.level == "error"]
    if errors:
        raise ValueError(
            "build_electro_properties: validator rejected synthesised dict:\n  - "
            + "\n  - ".join(e.message for e in errors)
        )

    body = _serialize(populated, entries, selectors["myocardiumSolver"])
    return _FOAMFILE_PREAMBLE + "\n" + body


# Slot keys that map to selectors (top-level discriminators), not overrides.
_SELECTOR_KEYS: frozenset[str] = frozenset(
    {"myocardiumSolver", "ionicModel", "tissue", "conductivitySource"}
)
SELECTOR_KEYS: frozenset[str] = _SELECTOR_KEYS  # public alias for external consumers (e.g. sweep_routing.py)

_COEFFS_PREFIX = "$ELECTRO_MODEL_COEFFS."


def _serialize(
    populated: dict[str, str],
    entries: list[DictEntry],
    myocardium_solver: str,
) -> str:
    """Group populated values by scope and emit the OpenFOAM dict body.

    Top-level keys (entries whose `driver_path` does not start with the
    `$ELECTRO_MODEL_COEFFS.` prefix) are emitted at the root. Everything
    else nests under the resolved `<solver>Coeffs` block.
    """
    import re
    top_level: dict[str, str] = {}
    coeffs: dict = {}

    dynamic_patterns = []
    for entry in entries:
        if getattr(entry, "dynamic_path", False):
            template = slot_key(entry.driver_path)
            # Same generic placeholder rule as the population pass. Hardcoding
            # <name>/<electrode> here meant an entry with any other placeholder
            # failed to match its own catalog entry, so the ROUTING fell
            # through to top_level -- emitting a $ELECTRO_MODEL_COEFFS.* key at
            # the electroProperties root, where the solver never reads it.
            pattern = _PLACEHOLDER_RE.sub(r"([^.]+)", re.escape(template))
            dynamic_patterns.append((entry, re.compile(f"^{pattern}$")))

    for concrete_key, value in populated.items():
        comment = ""
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
            _set_nested(coeffs, segments, value)
        else:
            top_level[concrete_key] = value

    parts: list[str] = []
    for key, value in top_level.items():
        parts.append(f"{key} {_openfoam_value_token(value)};")
    if coeffs:
        coeffs_scope = f"{myocardium_solver}Coeffs"
        parts.append("")
        parts.append(coeffs_scope)
        parts.append("{")
        parts.append(_serialize_block(coeffs, indent=4))
        parts.append("}")
    parts.append("")
    return "\n".join(parts)


def _entry_scope_and_key(
    driver_path: str,
    coeffs_scope: str,
) -> tuple[list[str] | None, str]:
    """Resolve a driver_path to (scope_path, key) suitable for read_foam_entry.

    Examples:
        "myocardiumSolver"                          → (None, "myocardiumSolver")
        "$ELECTRO_MODEL_COEFFS.solutionAlgorithm"   → (["monodomainSolverCoeffs"], "solutionAlgorithm")
        "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude"
            → (["singleCellSolverCoeffs", "singleCellStimulus"], "stim_amplitude")
    """
    if driver_path.startswith(_COEFFS_PREFIX):
        segments = driver_path[len(_COEFFS_PREFIX):].split(".")
        if len(segments) == 1:
            return [coeffs_scope], segments[0]
        return [coeffs_scope] + segments[:-1], segments[-1]
    return None, driver_path


def _foamlib_child_names(
    electro_properties_path: "Any",
    coeffs_scope: str,
    prefix_segments: list[str],
) -> tuple[str, ...]:
    """Structural-only, read-only enumeration of the concrete block names
    nested at ``coeffs_scope/prefix_segments/*`` in an existing OpenFOAM
    dict file.

    Uses ``foamlib.FoamFile`` instead of the line-based scanner in
    ``core/runtime/mutators.py`` because that scanner has no notion of
    "list the children of this block" -- it locates one named block (or
    one named key) at a time. foamlib already parses the full nested
    structure in-process without evaluating ``#calc``/``#codeStream``
    (see ``core/runtime/foam_backend.py``'s header comment for why that
    property is what makes foamlib safe to use on a read path at all).

    Deliberately used for STRUCTURE ONLY, never for values: foamlib
    returns typed, reserialised values (``5.5e-3`` -> ``0.0055``), which
    would break this module's verbatim round-tripping contract (see
    :func:`read_foam_entry`'s docstring). Every value in the returned
    ``overrides`` still comes from the existing line-based
    ``read_foam_entry``, keyed by the concrete names this function finds.

    Returns an empty tuple if the file, the scope, or the block is
    absent, or if the located node has no enumerable children (e.g. it is
    an OpenFOAM list rather than a sub-dictionary) -- callers treat that
    identically to "could not structurally expand this entry" and fall
    back to recording it in ``ignored_keys``, so this never regresses
    behaviour for a container shape this function does not understand.
    """
    from foamlib import FoamFile

    try:
        node: Any = FoamFile(electro_properties_path)
        for segment in (coeffs_scope, *prefix_segments):
            node = node[segment]
    except (KeyError, TypeError):
        return ()
    if not hasattr(node, "keys"):
        return ()
    return tuple(str(k) for k in node.keys() if k is not None)


def parse_electro_properties(
    electro_properties_path: "Any",
) -> dict[str, dict[str, str]]:
    """Parse an existing ``electroProperties`` file into selectors + overrides.

    Reads the file using the same ``get_electro_property_entry_groups()`` catalog
    that :func:`build_electro_properties` writes from. Returns a dict that
    round-trips through :func:`build_electro_properties`.

    - ``selectors``: ``myocardiumSolver``, ``ionicModel``, ``tissue`` (when
      present and applicable).
    - ``overrides``: full ``driver_path → value`` for every non-default entry
      found in the file. Values equal to ``entry.typical_value`` are omitted
      (the builder fills them automatically). For ``dynamic_path=True``
      entries whose catalog template names a placeholder segment (e.g.
      ``conductionNetworkDomains.<name>.*``), :func:`_foamlib_child_names`
      structurally discovers which concrete instances (``networkA``,
      ``networkB``, ...) actually exist in the file, and each instance's
      leaves are read back and included here with the placeholder resolved
      to that concrete name -- the same round-trip static entries get.
    - ``ignored_keys``: the ``driver_path`` of every catalog entry this parser
      still does not round-trip: either its template has no placeholder
      segment to resolve, or no concrete instance could be found in the
      file (including when the block is simply absent). If the source dict
      sets any of these, they will NOT reappear on a rebuild — inspect the
      source dict manually. (Keys entirely outside the catalog remain
      un-enumerated — the parser only reads catalogued paths.)

    Returns:
        ``{"selectors": {...}, "overrides": {...}, "ignored_keys": [...]}``
    """
    from pathlib import Path as _Path
    from omnidriver.cardiacfoam.detection import detect_myocardium_solver_name
    from omnidriver.openfoam.mutators import read_foam_entry

    electro_properties_path = _Path(electro_properties_path)
    solver = detect_myocardium_solver_name(electro_properties_path)
    coeffs_scope = f"{solver}Coeffs"

    selectors: dict[str, str] = {"myocardiumSolver": solver}
    overrides: dict[str, str] = {}
    ignored_keys: list[str] = []

    for entry in _all_electro_entries():
        if entry.dynamic_path:
            sk = slot_key(entry.driver_path)
            parts = sk.split(".")
            placeholder_idx = next(
                (i for i, p in enumerate(parts) if _PLACEHOLDER_RE.fullmatch(p)),
                None,
            )
            if placeholder_idx is None:
                ignored_keys.append(entry.driver_path)
                continue

            instances = _foamlib_child_names(
                electro_properties_path, coeffs_scope, parts[:placeholder_idx],
            )
            if not instances:
                ignored_keys.append(entry.driver_path)
                continue

            expanded_any = False
            for instance in instances:
                concrete_driver_path = _PLACEHOLDER_RE.sub(
                    instance, entry.driver_path, count=1,
                )
                scope_path, key = _entry_scope_and_key(concrete_driver_path, coeffs_scope)
                value = read_foam_entry(electro_properties_path, key, scope=scope_path)
                if value is None:
                    continue
                expanded_any = True
                if value != entry.typical_value:
                    overrides[concrete_driver_path] = value
            if not expanded_any:
                ignored_keys.append(entry.driver_path)
            continue

        scope_path, key = _entry_scope_and_key(entry.driver_path, coeffs_scope)
        value = read_foam_entry(electro_properties_path, key, scope=scope_path)
        if value is None:
            continue
        sk = slot_key(entry.driver_path)
        if sk in _SELECTOR_KEYS:
            selectors[sk] = value
        elif value != entry.typical_value:
            overrides[entry.driver_path] = value

    return {
        "selectors": selectors,
        "overrides": overrides,
        "ignored_keys": sorted(set(ignored_keys)),
    }


def _dynamic_container_names() -> tuple[str, ...]:
    """The first dotted segment of every ``dynamic_path=True`` catalog
    entry's slot key, e.g. ``"conductionNetworkDomains"`` for
    ``$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>...`` -- the
    top-level block names carried forward verbatim across a solver switch
    (see :func:`_capture_dynamic_containers`) rather than resynthesised,
    even though :func:`parse_electro_properties` can now structurally
    round-trip most of them into ``overrides``: a verbatim byte carry
    remains the more robust fallback for content whose exact on-disk
    formatting a structural round-trip cannot guarantee reproducing, and
    for any concrete leaf that failed to parse."""
    names: set[str] = set()
    for entry in _all_electro_entries():
        if not entry.dynamic_path:
            continue
        sk = slot_key(entry.driver_path)
        names.add(sk.split(".", 1)[0])
    return tuple(sorted(names))


def _strip_dynamic_overrides(overrides: dict[str, str]) -> dict[str, str]:
    """Remove every override whose slot key falls under a dynamic-path
    container (``conductionNetworkDomains``, ``domainCouplings``, ...).

    Used by :func:`regenerate_electro_properties`'s intermediate rebuild:
    those values describe the OLD solver's configuration and are about to
    be discarded there in favour of a verbatim carry-forward under the NEW
    solver's coeffs scope, not resynthesised. Letting them leak into that
    intermediate ``build_electro_properties`` call would validate a stale
    pairing that does not reflect what the function actually ships.
    """
    containers = _dynamic_container_names()
    prefixes = tuple(f"{_COEFFS_PREFIX}{c}." for c in containers)
    return {k: v for k, v in overrides.items() if not k.startswith(prefixes)}


def _capture_dynamic_containers(path: "Any", solver: str) -> dict[str, str]:
    """Snapshot the raw text of every dynamic-path container
    (``conductionNetworkDomains``, ``domainCouplings``, ``ecgDomains``,
    ``bathPotentialDomain``, ``ionicHeterogeneity``,
    ``ionicConstantOverrides``, ``constants``, ``initialStates``) present
    under ``<solver>Coeffs`` in the file at ``path``. Must be called
    *before* ``path`` is overwritten -- these are exactly the block
    families :func:`parse_electro_properties` cannot itself round-trip
    (it can only enumerate them into ``ignored_keys``, having no way to
    invent the concrete ``<name>`` instances), so a rebuild that does not
    carry them forward would silently drop them."""
    from omnidriver.openfoam.mutators import read_foam_dict_block

    coeffs_scope = f"{solver}Coeffs"
    captured: dict[str, str] = {}
    for name in _dynamic_container_names():
        block_text = read_foam_dict_block(path, name, scope=[coeffs_scope])
        if block_text is not None:
            captured[name] = block_text
    return captured


def _carry_forward_dynamic_containers(
    path: "Any", new_solver: str, captured: dict[str, str],
) -> None:
    """Reinsert, verbatim, the dynamic containers ``captured`` by
    :func:`_capture_dynamic_containers` (from the OLD file, before it was
    overwritten) into ``path``'s NEW ``<new_solver>Coeffs`` block --
    ``build_electro_properties`` only synthesises these blocks when an
    override under the matching prefix is present (see
    ``_VIRTUAL_PRESENCE_TRIGGERS``), and a bare ``myocardiumSolver``
    override supplies none.

    Intentionally a raw, unmodified carry-forward, not a resynthesis: the
    catalog has no way to know what a dynamic block's contents *should*
    become under the new solver (e.g. whether a Purkinje network's own 1-D
    solver should also switch) -- that is a separate, deliberate decision
    left to the agent via ordinary ``$ELECTRO_MODEL_COEFFS.*`` overrides
    applied after this one, which correctly resolve against the
    now-renamed ``<new_solver>Coeffs`` scope.
    """
    from omnidriver.openfoam.mutators import ensure_foam_dict

    new_coeffs_scope = f"{new_solver}Coeffs"
    for name, block_text in captured.items():
        ensure_foam_dict(path, name, block_text, scope=[new_coeffs_scope])


def _prune_now_forbidden(
    selectors: dict[str, Any], overrides: dict[str, Any], changed_key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Drop selectors/overrides that become ``forbidden_when`` under the
    context produced by ``selectors`` (with ``changed_key`` already set to
    its new value).

    Switching ``myocardiumSolver`` legitimately makes some of the OLD
    file's selectors meaningless for the new one -- e.g. ``ionicModel``/
    ``tissue`` are ``forbidden_when myocardiumSolver=eikonalSolver``
    because ``eikonalSolverCoeffs`` has no such key at all (there is no 3-D
    reaction-diffusion ODE to select a model for). This is NOT the
    information-loss hazard the dynamic-container carry-forward guards
    against: a forbidden key has no valid location in the new solver's
    coeffs block, exactly like the committed
    ``electroProperties.eikonal`` fixture, which sets neither. Without
    this prune, ``build_electro_properties`` would (correctly) raise
    rather than emit an invalid dict -- pruning is what makes the
    solver-switch case succeed instead of always erroring.
    """
    context = resolve_context(selectors, overrides=overrides)
    entry_by_driver_path = {
        e.driver_path: e for e in _all_electro_entries() if not e.dynamic_path
    }
    entry_by_slot_key = {
        slot_key(e.driver_path): e for e in entry_by_driver_path.values()
    }

    def is_forbidden(entry: DictEntry) -> bool:
        if not entry.forbidden_when:
            return False
        return any(
            _predicate_matches(context, pred_key, expected)
            for pred_key, expected in entry.forbidden_when.items()
        )

    pruned_selectors = dict(selectors)
    for sk in list(pruned_selectors):
        if sk == changed_key:
            continue
        entry = entry_by_slot_key.get(sk)
        if entry is not None and is_forbidden(entry):
            del pruned_selectors[sk]

    pruned_overrides = {
        dp: v
        for dp, v in overrides.items()
        if dp not in entry_by_driver_path or not is_forbidden(entry_by_driver_path[dp])
    }

    return pruned_selectors, pruned_overrides


def regenerate_electro_properties(
    path: "Any",
    driver_path: str,
    value: str,
    extra_overrides: dict[str, str] | None = None,
) -> None:
    """Rewrite ``constant/electroProperties`` at ``path`` in place with one
    selector key (``myocardiumSolver``, ..., see ``_SELECTOR_KEYS``) changed
    to ``value``, preserving everything else the file already had.

    This is the regeneration counterpart to the ordinary
    ``$ELECTRO_MODEL_COEFFS.*`` key-patch route
    (:func:`omnidriver.cardiacfoam.overrides.electro_model_coeffs_scope`):
    changing ``myocardiumSolver`` renames the active ``<solver>Coeffs``
    sub-block and flips which sibling keys the catalog allows, which a
    single key/value/scope patch cannot express. Instead this:

    1. Parses the existing file back into ``{selectors, overrides}`` via
       :func:`parse_electro_properties`.
    2. Captures, verbatim, every dynamic-path container
       (``conductionNetworkDomains``, ``domainCouplings``, ...) present in
       the file (:func:`_capture_dynamic_containers`), and strips their
       parsed values out of ``overrides`` (:func:`_strip_dynamic_overrides`)
       so step 3's rebuild stays blind to the OLD solver's dynamic
       configuration -- it is about to be superseded by step 5's verbatim
       carry-forward, not resynthesised.
    3. Sets the one changed selector, drops any OTHER selector/override
       that the new value makes ``forbidden_when`` (:func:`_prune_now_forbidden`
       -- e.g. ``ionicModel``/``tissue`` under ``myocardiumSolver=eikonalSolver``,
       which has no such keys at all), and rebuilds via
       :func:`build_electro_properties`, which re-validates the whole
       result against the catalog for the new solver.
    4. Merges in ``extra_overrides`` -- other ``$ELECTRO_MODEL_COEFFS.*``
       overrides from the same `step --strict --apply` call, needed for
       any key the new solver requires that has no catalog default and
       that the old file never had (nothing for a later key-patch pass to
       patch) -- then rebuilds via :func:`build_electro_properties`, which
       re-validates the whole result against the catalog for the new
       solver.
    5. Stages the rebuilt text on a scratch copy, reinserts the containers
       captured in step 2 under the newly-named coeffs scope
       (:func:`_carry_forward_dynamic_containers`), then re-parses and
       re-validates THAT result -- this is the only point where the new
       solver and the (unmodified) old dynamic blocks are checked
       together, catching e.g. a switch that leaves the carried-forward
       Purkinje network physically incompatible with the new myocardium
       solver (see ``solver_coupling.SOLVER_COMPATIBILITY_RULES``), which
       step 3's rebuild cannot see by design. Only once this passes is the
       scratch copy's content written to ``path`` -- a rejection here
       leaves the original file at ``path`` completely untouched.

    Raises:
        ValueError: ``driver_path``'s slot key is not a selector key, the
            rebuild fails catalog validation for the new value (e.g. a
            still-missing required field with no default and no
            ``extra_overrides`` entry -- the case-specific gap that
            parameter exists to close), or the carried-forward dynamic
            blocks are physically incompatible with the new selector value.
    """
    import tempfile as _tempfile
    from pathlib import Path as _Path

    path = _Path(path)
    key = slot_key(driver_path)
    if key not in _SELECTOR_KEYS:
        raise ValueError(
            f"regenerate_electro_properties: {driver_path!r} is not a "
            f"regeneration selector key (known: {sorted(_SELECTOR_KEYS)})"
        )

    parsed = parse_electro_properties(path)
    selectors = dict(parsed["selectors"])
    overrides = dict(parsed["overrides"])
    old_solver = selectors.get("myocardiumSolver")

    # Step 2: snapshot dynamic containers from the OLD file before it is
    # overwritten below.
    captured = _capture_dynamic_containers(path, old_solver) if old_solver else {}

    # The intermediate rebuild below must stay blind to the OLD dynamic
    # blocks' own values: they describe the OLD solver's configuration and
    # are about to be discarded here in favour of the verbatim carry-forward
    # a few lines down (_carry_forward_dynamic_containers), not
    # resynthesised for the new solver. Since parse_electro_properties can
    # now structurally round-trip them (see its docstring), they would
    # otherwise leak into this intermediate build_electro_properties call
    # and be validated against a solver they no longer actually describe in
    # the shipped file. The real, final check happens below, once the
    # carried-forward blocks are back in the file for real.
    overrides = _strip_dynamic_overrides(overrides)

    selectors[key] = value
    selectors, overrides = _prune_now_forbidden(selectors, overrides, key)
    if extra_overrides:
        overrides.update(extra_overrides)
    new_text = build_electro_properties(selectors, overrides=overrides)

    new_solver = selectors.get("myocardiumSolver", old_solver)
    if new_solver and captured:
        # Stage the rewrite on a scratch copy rather than `path` directly:
        # the carried-forward blocks are only visible to validation AFTER
        # reinsertion (see the final safety net below), so a failure there
        # must leave the ORIGINAL file at `path` completely untouched
        # instead of shipping a known-incompatible intermediate result.
        with _tempfile.TemporaryDirectory() as scratch_dir:
            scratch = _Path(scratch_dir) / path.name
            scratch.write_text(new_text)
            _carry_forward_dynamic_containers(scratch, new_solver, captured)

            # Final safety net: now that the carried-forward dynamic blocks
            # are back in the file, validate what would ACTUALLY ship. This
            # is the only point in the pipeline where the new solver and
            # the (unmodified) old dynamic blocks are checked together --
            # catches e.g. switching to a solver the carried-forward
            # Purkinje network can never physically couple to (see
            # solver_coupling.SOLVER_COMPATIBILITY_RULES), which the
            # intermediate rebuild above cannot see by design.
            final = parse_electro_properties(scratch)
            try:
                build_electro_properties(final["selectors"], overrides=final["overrides"] or None)
            except ValueError as exc:
                raise ValueError(
                    f"regenerate_electro_properties: switching {key}={value!r} "
                    f"leaves a carried-forward dynamic block incompatible with "
                    f"the new solver -- {exc}"
                ) from exc

            path.write_text(scratch.read_text())
    else:
        path.write_text(new_text)


def build_physics_properties(
    selectors: dict[str, str],
    *,
    overrides: dict[str, str] | None = None,
    typical_value_fallback: bool = True,
) -> str:
    """Synthesise a complete `physicsProperties` dict from intent.

    Mirrors :func:`build_electro_properties` but against
    :data:`PHYSICS_PROPERTY_ENTRIES`. There is no ``<solver>Coeffs``
    wrapper — every physics key lives at the dict root. Today the only
    entry is ``type``; future physics-level selectors slot in unchanged.

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
            constraint violation from `validate_run`.
    """
    context = resolve_context(selectors, overrides=overrides)
    # Scope to physics entries — electro entries don't belong here.
    entries = select_applicable_entries(context, entries=list(PHYSICS_PROPERTY_ENTRIES))
    populated = populate_values(
        entries, context, typical_value_fallback=typical_value_fallback,
    )

    context_ = own_driver_context()
    run = _populated_to_run(
        populated, entries, context_.capabilities.dictionaries.phases(),
    )
    errors = [e for e in validate_run(run, entries=entries, driver_context=context_) if e.level == "error"]
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
    return _foamfile_preamble("physicsProperties") + "\n" + body


# --------------------------------------------------------------------------
# The write channel: `synthesize` (Phase 2 Task 9)
# --------------------------------------------------------------------------


def _typed_value(value: Any) -> tuple[str, Any]:
    """The `ParameterAssignment` kind and coerced value for one selector or
    override value.

    A selector/override value here is `Any`-typed at the call site
    (`electro_overrides: dict[str, Any]` in `sweep.py`), but a
    `ParameterAssignment` carries typed data, never rendered text (2026-09-23
    decision) -- so a value this cannot type is refused by name rather than
    silently flattened to a string. No current caller supplies one (every
    exercised override value is a plain word or a number); if one arises,
    that is a finding about this channel's coverage, not a reason to add a
    `literal`/`text` escape hatch back to `VALUE_KINDS`.
    """
    if isinstance(value, bool):
        return "boolean", value
    if isinstance(value, Integral):
        return "integer", int(value)
    if isinstance(value, Real):
        return "scalar", float(value)
    if isinstance(value, str) and value and value.split() == [value]:
        return "word", value
    raise ValueError(
        f"value {value!r} cannot be carried as a typed case-write parameter "
        f"(must be a bool, a number, or a single whitespace-free word); this "
        f"is content, not a parameter value, and has no carrier in this "
        f"channel yet"
    )


def _selector_parameters(
    document: str, prefix: str, selectors: Mapping[str, Any],
) -> list[ParameterAssignment]:
    parameters = []
    for key, value in selectors.items():
        kind, typed_value = _typed_value(value)
        parameters.append(ParameterAssignment(
            qualified_id=f"{prefix}{key}", owner=PLUGIN_ID, document=document,
            key_path=(key,), binding={}, value=typed_value, value_kind=kind,
            source="case",
        ))
    return parameters


def _override_parameters(
    document: str, overrides: Mapping[str, Any] | None,
) -> list[ParameterAssignment]:
    parameters = []
    for driver_path, value in (overrides or {}).items():
        kind, typed_value = _typed_value(value)
        parameters.append(ParameterAssignment(
            qualified_id=driver_path, owner=PLUGIN_ID, document=document,
            key_path=(slot_key(driver_path),), binding={}, value=typed_value,
            value_kind=kind, source="case",
        ))
    return parameters


def resolve_synthesis_mutation(request: CaseMutationRequest) -> ResolvedMutation:
    """The semantic owner's answer for a `synthesize` request: complete
    document bodies, authored from the same builders `build_and_launch`
    called directly before this migration (`build_electro_properties`,
    `build_physics_properties`, `get_fv_schemes`/`get_fv_solution`,
    `build_control_dict`) -- this does not reimplement dictionary synthesis,
    it packages it.

    Pure: every input is reconstructed from `request.parameters`, and
    `build_electro_properties`/`build_physics_properties`/the system
    templates touch no filesystem.

    `system/fvSchemes`/`fvSolution`/`controlDict` carry
    ``"skip_if_present"`` unless the request asked to `overwrite` -- matching
    the pre-migration ``if not X.exists() or overwrite: write`` guard on each
    of those three files (``electroProperties``/``physicsProperties`` were
    never individually guarded that way and stay unconditional here too).

    `system/controlDict`'s deltaT/endTime is the ``repeated_edits_to_one_file``
    conformance case in its real setting: the pre-migration code wrote a
    freshly templated ``controlDict`` and then called ``update_control_dict``
    on it a SECOND time when the caller passed an explicit ``delta_t``/
    ``end_time`` -- unconditionally, even against a pre-existing file whose
    base write above had just been skipped. Characterized (byte-for-byte,
    including `update_foam_entry`'s re-formatting of the patched line) in
    `tests/test_synthesis_through_the_channel.py`. Reproduced here as one
    content target (the base, always using a default when no explicit value
    was given) plus, only when a value was explicitly given, a separate edit
    target for that one key -- folded by `render_synthesis_case_files` into
    one rendering, not two writes.
    """
    if request.mode != "synthesize":
        raise ValueError(
            f"cardiacFoam's build_and_launch resolves synthesize requests "
            f"only, not {request.mode!r}"
        )

    electro_selectors: dict[str, Any] = {}
    electro_overrides: dict[str, Any] = {}
    physics_selectors: dict[str, Any] = {}
    physics_overrides: dict[str, Any] = {}
    control_values: dict[str, Any] = {}
    dx: float | None = None
    overwrite = False
    include_meshless_polymesh = False
    include_allrun = False

    for parameter in request.parameters:
        key = parameter.key_path[-1]
        if parameter.document == _ELECTRO_DOCUMENT:
            if parameter.qualified_id.startswith(_ELECTRO_SELECTOR_PREFIX):
                electro_selectors[key] = parameter.value
            else:
                electro_overrides[parameter.qualified_id] = parameter.value
        elif parameter.document == _PHYSICS_DOCUMENT:
            if parameter.qualified_id.startswith(_PHYSICS_SELECTOR_PREFIX):
                physics_selectors[key] = parameter.value
            else:
                physics_overrides[parameter.qualified_id] = parameter.value
        elif parameter.document == _CONTROL_DOCUMENT:
            control_values[key] = parameter.value
        elif parameter.document == _BLOCK_MESH_DOCUMENT:
            dx = parameter.value
        elif parameter.document == _SYNTHESIS_META_DOCUMENT:
            # Not a case document at all -- `overwrite`/`include_meshless_
            # polymesh` govern how targets below are built, and have no file
            # of their own to land in. See `_SYNTHESIS_META_DOCUMENT`'s
            # docstring.
            if key == "overwrite":
                overwrite = bool(parameter.value)
            elif key == "include_meshless_polymesh":
                include_meshless_polymesh = bool(parameter.value)
            elif key == "include_allrun":
                include_allrun = bool(parameter.value)
            else:
                raise ValueError(
                    f"synthesis parameter {parameter.qualified_id!r} names "
                    f"undeclared meta key {key!r}"
                )
        else:
            raise ValueError(
                f"synthesis parameter {parameter.qualified_id!r} targets "
                f"undeclared document {parameter.document!r}"
            )

    from omnidriver.cardiacfoam.system_templates import (
        build_control_dict,
        get_fv_schemes,
        get_fv_solution,
    )

    myocardium_solver = electro_selectors.get("myocardiumSolver", "monodomainSolver")
    skip_if_present = not overwrite

    electro_text = build_electro_properties(electro_selectors, overrides=electro_overrides or None)
    physics_text = build_physics_properties(physics_selectors, overrides=physics_overrides or None)
    fv_schemes_text = get_fv_schemes(myocardium_solver)
    fv_solution_text = get_fv_solution(myocardium_solver)
    dt = control_values.get("deltaT_base", 1e-4)
    et = control_values.get("endTime_base", 1.0)
    control_dict_text = build_control_dict(delta_t=dt, end_time=et)

    targets: list[dict[str, Any]] = [
        {"document": _ELECTRO_DOCUMENT, "content": electro_text, "format": _SYNTHESIS_FORMAT},
        {"document": _PHYSICS_DOCUMENT, "content": physics_text, "format": _SYNTHESIS_FORMAT},
        {
            "document": _FV_SCHEMES_DOCUMENT, "content": fv_schemes_text,
            "format": _SYNTHESIS_FORMAT, "skip_if_present": skip_if_present,
        },
        {
            "document": _FV_SOLUTION_DOCUMENT, "content": fv_solution_text,
            "format": _SYNTHESIS_FORMAT, "skip_if_present": skip_if_present,
        },
        {
            "document": _CONTROL_DOCUMENT, "content": control_dict_text,
            "format": _SYNTHESIS_FORMAT, "skip_if_present": skip_if_present,
        },
    ]
    if "deltaT_patch" in control_values:
        targets.append({
            "document": _CONTROL_DOCUMENT, "format": _SYNTHESIS_FORMAT,
            "expanded_key_path": ["deltaT"], "value": control_values["deltaT_patch"],
        })
    if "endTime_patch" in control_values:
        targets.append({
            "document": _CONTROL_DOCUMENT, "format": _SYNTHESIS_FORMAT,
            "expanded_key_path": ["endTime"], "value": control_values["endTime_patch"],
        })
    needs_block_mesh = myocardium_solver in _block_mesh_solvers()
    if needs_block_mesh:
        from omnidriver.openfoam.mesh_provisioning import default_block_mesh_dict_text

        targets.append({
            "document": _BLOCK_MESH_DOCUMENT,
            "content": default_block_mesh_dict_text(dx_m=dx),
            "format": _SYNTHESIS_FORMAT,
            # Never clobbered, regardless of `overwrite` -- a hand-authored
            # custom blockMeshDict/polyMesh must survive a repeat synthesis.
            # Mirrors mesh_provisioning.provision_mesh's own existence guard,
            # which still runs after this commits (idempotent: it is this
            # same file, already there either way).
            "skip_if_present": True,
        })

    if include_allrun:
        # Phase 3 Task 10 (bypass 5): sweep.py::materialize_case used to
        # write this with a bare `write_text` + `chmod` after
        # `build_and_launch` had already returned -- a second, unaudited
        # write outside the channel, and a second transaction for one case
        # materialization (a failure between the two left inputs with no
        # runnable Allrun). Folded into this same plan instead: same body
        # (`needs_block_mesh` -- computed once, above -- decides whether
        # `blockMesh` runs before `cardiacFoam`), same one `commit_case_write`
        # call as every other document here. Never `skip_if_present`: the
        # pre-migration code always re-wrote Allrun's content unconditionally
        # on every call, reused case_root or not.
        from omnidriver.openfoam.case_planning import plan_verbatim_content

        allrun_body = "#!/bin/sh\n" + (
            "blockMesh\ncardiacFoam\n" if needs_block_mesh else "cardiacFoam\n"
        )
        targets.append(plan_verbatim_content("Allrun", allrun_body, executable=True))

    if myocardium_solver in _meshless_solvers() and include_meshless_polymesh:
        # Task 12 (batch P2-H): the bundled single-cell polyMesh fixture,
        # folded in as five ordinary skip_if_present synthesis targets
        # instead of mesh_provisioning.provision_mesh's direct
        # shutil.copyfile. `build_case` has already refused a *partial*
        # five-file state before this function ever runs (see its own
        # docstring) -- reaching here means the real case is either
        # entirely absent (all five render) or already complete (all five
        # skip), never a mix. Reading the fixture's bytes here (not
        # case-dependent state -- the same bundled bytes every time) is the
        # one narrow exception to this function's "pure, touches no
        # filesystem" docstring; it never reads `case_root`.
        from omnidriver.cardiacfoam.mesh_provisioning import meshless_polymesh_fixture

        for name, content in sorted(meshless_polymesh_fixture().items()):
            targets.append({
                "document": f"constant/polyMesh/{name}",
                "content": content,
                "format": _SYNTHESIS_FORMAT,
                "skip_if_present": True,
            })

    expected_effects = tuple(
        f"author {target['document']}" for target in targets if "content" in target
    )
    return ResolvedMutation(
        request=request, targets=tuple(targets), preconditions=(),
        expected_effects=expected_effects, semantic_owner_id=PLUGIN_ID,
    )


def _block_mesh_solvers() -> frozenset[str]:
    """`mesh_provisioning.BLOCK_MESH_SOLVERS`, named for this call site.

    A plain re-export would be a second name for one constant that drifts;
    this stays a function so the import -- and the single set it reads --
    happens at call time, matching every other cross-module reference in
    this file (`from omnidriver.cardiacfoam.mesh_provisioning import ...`
    would create a real import-time dependency this module has not needed
    until now)."""
    from omnidriver.cardiacfoam.mesh_provisioning import BLOCK_MESH_SOLVERS

    return BLOCK_MESH_SOLVERS


def _meshless_solvers() -> frozenset[str]:
    """`mesh_provisioning.MESHLESS_SOLVERS`, named for this call site --
    added 2026-09-23 (R3 finding 7) alongside `_block_mesh_solvers`, for the
    same reason: a function, not a re-exported constant, so the import
    happens at call time rather than creating a new import-time dependency."""
    from omnidriver.cardiacfoam.mesh_provisioning import MESHLESS_SOLVERS

    return MESHLESS_SOLVERS


def build_case(
    electro_selectors: dict[str, str],
    *,
    physics_selectors: dict[str, str],
    case_dir: "Path",
    electro_overrides: "dict[str, str] | None" = None,
    physics_overrides: "dict[str, str] | None" = None,
    overwrite: bool = False,
    delta_t: "float | str | None" = None,
    end_time: "float | str | None" = None,
    dx: "float | None" = None,
    dry_run: bool = False,
    include_allrun: bool = False,
    driver_context: "Any | None" = None,
) -> Any:
    """Resolve and render a from-scratch cardiacFoam case as one reviewable
    `CaseWritePlan` -- the pure half of what `build_and_launch` used to do
    with five bare `write_text` calls plus a second `controlDict` mutation.
    `build_and_launch` commits this plan (through `commit_case_write`) and
    then launches; calling this alone costs only the read `render_case_files`
    needs to decide whether an already-present `blockMeshDict` should join
    the plan at all (never clobbered -- see `mesh_provisioning.provision_mesh`'s
    docstring).

    Does not implement the `overwrite=False` case-already-built guard --
    `build_and_launch` checks that before calling this, and keeps raising the
    exact `FileExistsError` it always has (preserved deliberately: the
    pre-existing regression test
    `test_dict_builder.py::test_existing_case_dir_is_not_overwritten_without_consent`
    asserts that specific type, and this migration does not change it).

    `dry_run` (Task 12, batch P2-H): added so a meshless solver's bundled
    polyMesh fixture -- now folded into this function's own plan instead of
    `build_and_launch` calling `mesh_provisioning.provision_mesh` separately
    -- is excluded from the plan under `dry_run=True`, matching R3 finding
    8's "a dry run must not write a mesh". The `dx` rejection for a meshless
    solver, and the partial-mesh precheck below, both still run
    unconditionally: validation is not part of the filesystem effect a dry
    run skips (same reasoning `provision_mesh`'s own docstring already
    states for its `dx_m` rejection).

    `include_allrun` (Phase 3 Task 10, bypass 5): when True, a hand-runnable
    ``Allrun`` joins this same plan -- see `resolve_synthesis_mutation`'s own
    handling of the `$CARDIACFOAM.synthesis.include_allrun` meta parameter
    this sets below. Unlike `include_meshless_polymesh`, this is not
    `dry_run`-gated: `sweep.py::materialize_case` is the one production
    caller and always wants the script written whether or not the case is
    also being launched immediately, and `Allrun` is a case input, not part
    of the filesystem effect a dry run exists to skip."""
    from pathlib import Path as _Path
    import datetime as _datetime
    import tempfile as _tempfile

    from omnidriver.core.case_write import CaseWritePlan

    # Made absolute here if it is not already: `CaseMutationRequest` below
    # refuses a relative `case_root` outright (R3 blocker 2, 2026-09-23) -- a
    # relative one would resolve against whatever directory the *committing*
    # process happens to be in, silently writing into a different case than
    # the caller named. Only a genuinely relative path is resolved (which
    # also normalizes `..`/symlinks) -- an already-absolute `case_dir` is
    # passed through exactly as given, so this does not change the returned
    # `case_dir` string for the (common) already-absolute case.
    case_dir = _Path(case_dir)
    if not case_dir.is_absolute():
        case_dir = case_dir.resolve()
    myocardium_solver = electro_selectors.get("myocardiumSolver", "monodomainSolver")

    dt = delta_t if delta_t is not None else 1e-4
    et = end_time if end_time is not None else 1.0

    include_meshless_polymesh = False
    if myocardium_solver in _meshless_solvers():
        if dx is not None:
            raise ValueError(
                f"dx has no effect for myocardiumSolver={myocardium_solver!r} "
                "(no spatial mesh -- it has no geometry for dx to resolve)."
            )
        # Validation, not the filesystem effect -- runs unconditionally,
        # matching the `dx` rejection just above and `provision_mesh`'s own
        # documented reasoning for its `dx_m` rejection ("dry_run is not
        # part of the filesystem effect it skips"). A dry run must still
        # report a partial-mesh refusal the real run would give, rather than
        # reporting success for a combination that would fail for real.
        from omnidriver.cardiacfoam.mesh_provisioning import meshless_polymesh_fixture

        poly_mesh_dir = case_dir / "constant" / "polyMesh"
        fixture_names = sorted(meshless_polymesh_fixture())
        present = [name for name in fixture_names if (poly_mesh_dir / name).exists()]
        if present and len(present) != len(fixture_names):
            missing = [name for name in fixture_names if name not in present]
            raise ValueError(
                f"{poly_mesh_dir} has a partially authored mesh (present: "
                f"{present}, missing: {missing}); refusing to complete or "
                f"overwrite it -- author all five files by hand, or "
                f"remove the partial set before calling this again"
            )
        include_meshless_polymesh = not dry_run

    parameters = (
        *_selector_parameters(_ELECTRO_DOCUMENT, _ELECTRO_SELECTOR_PREFIX, electro_selectors),
        *_override_parameters(_ELECTRO_DOCUMENT, electro_overrides),
        *_selector_parameters(_PHYSICS_DOCUMENT, _PHYSICS_SELECTOR_PREFIX, physics_selectors),
        *_override_parameters(_PHYSICS_DOCUMENT, physics_overrides),
        # `_base`: what the freshly-templated document uses (always -- a
        # default when the caller gave none). `_patch`: only present when the
        # caller explicitly gave a value, and folded in as a second effect on
        # top of whichever body `render_synthesis_case_files` used as the
        # base -- matching `update_control_dict`'s pre-migration per-key
        # `is not None` guard exactly (patching only the key that was
        # actually given, never both together by default).
        ParameterAssignment(
            qualified_id="$CARDIACFOAM.control.deltaT_base", owner=PLUGIN_ID,
            document=_CONTROL_DOCUMENT, key_path=("deltaT_base",), binding={},
            value=float(dt), value_kind="scalar",
            source="case" if delta_t is not None else "template",
        ),
        ParameterAssignment(
            qualified_id="$CARDIACFOAM.control.endTime_base", owner=PLUGIN_ID,
            document=_CONTROL_DOCUMENT, key_path=("endTime_base",), binding={},
            value=float(et), value_kind="scalar",
            source="case" if end_time is not None else "template",
        ),
        ParameterAssignment(
            qualified_id="$CARDIACFOAM.synthesis.overwrite", owner=PLUGIN_ID,
            document=_SYNTHESIS_META_DOCUMENT, key_path=("overwrite",), binding={},
            value=bool(overwrite), value_kind="boolean", source="case",
        ),
        ParameterAssignment(
            qualified_id="$CARDIACFOAM.synthesis.include_meshless_polymesh",
            owner=PLUGIN_ID, document=_SYNTHESIS_META_DOCUMENT,
            key_path=("include_meshless_polymesh",), binding={},
            value=bool(include_meshless_polymesh), value_kind="boolean",
            source="case",
        ),
        ParameterAssignment(
            qualified_id="$CARDIACFOAM.synthesis.include_allrun",
            owner=PLUGIN_ID, document=_SYNTHESIS_META_DOCUMENT,
            key_path=("include_allrun",), binding={},
            value=bool(include_allrun), value_kind="boolean",
            source="case",
        ),
    )
    if delta_t is not None:
        parameters = (*parameters, ParameterAssignment(
            qualified_id="$CARDIACFOAM.control.deltaT_patch", owner=PLUGIN_ID,
            document=_CONTROL_DOCUMENT, key_path=("deltaT_patch",), binding={},
            value=float(delta_t), value_kind="scalar", source="case",
        ))
    if end_time is not None:
        parameters = (*parameters, ParameterAssignment(
            qualified_id="$CARDIACFOAM.control.endTime_patch", owner=PLUGIN_ID,
            document=_CONTROL_DOCUMENT, key_path=("endTime_patch",), binding={},
            value=float(end_time), value_kind="scalar", source="case",
        ))
    if myocardium_solver in _block_mesh_solvers() and dx is not None:
        parameters = (*parameters, ParameterAssignment(
            qualified_id="$CARDIACFOAM.mesh.dx", owner=PLUGIN_ID,
            document=_BLOCK_MESH_DOCUMENT, key_path=("dx",), binding={},
            value=float(dx), value_kind="scalar", source="case",
        ))

    source_artifacts = (
        f"cardiacfoam.dict_entries:electro:{myocardium_solver}",
        "cardiacfoam.dict_entries:physics",
        "cardiacfoam.system_templates:fvSchemes+fvSolution+controlDict",
    )
    request = CaseMutationRequest(
        mode="synthesize", case_root=case_dir, adapter_id=PLUGIN_ID,
        workflow="entry", source_artifacts=source_artifacts,
        parameters=parameters, requested_by="cardiacfoam.build_and_launch",
    )
    if driver_context is None:
        driver_context = own_driver_context()

    resolved = driver_context.capabilities.case_writer.resolve(
        request, driver_context=driver_context,
    )
    with _tempfile.TemporaryDirectory(prefix="omnidriver-case-render-") as scratch:
        snapshot_root = _Path(scratch)
        rendered = driver_context.capabilities.case_writer.render(
            resolved, snapshot_root=snapshot_root, driver_context=driver_context,
            execution_env=None,
        )
        identity = getattr(driver_context, "identity", None)
        stack_identity = identity.capability_digest if identity is not None else "0" * 64
        plan = CaseWritePlan(
            request=request, files=rendered, preconditions=resolved.preconditions,
            semantic_owner_id=resolved.semantic_owner_id, stack_identity=stack_identity,
            created_at=_datetime.datetime.now(_datetime.timezone.utc).isoformat(),
            expected_effects=resolved.expected_effects,
        )
    return plan


def build_and_launch(
    electro_selectors: dict[str, str],
    *,
    physics_selectors: dict[str, str],
    case_dir: "Path",
    electro_overrides: "dict[str, str] | None" = None,
    physics_overrides: "dict[str, str] | None" = None,
    overwrite: bool = False,
    dry_run: bool = False,
    pre_solve_commands: "Sequence[str | Sequence[str]] | None" = None,
    openfoam_bashrc: "str | Path | None" = None,
    delta_t: "float | str | None" = None,
    end_time: "float | str | None" = None,
    dx: "float | None" = None,
    include_allrun: bool = False,
    driver_context: "Any | None" = None,
) -> dict:
    """Build both dicts, write them to ``case_dir/constant/``, and (if
    not dry_run) launch the engine on the resulting case.

    Args:
        electro_selectors: selectors for build_electro_properties.
        physics_selectors: selectors for build_physics_properties.
        case_dir: target case directory. Will be created if absent.
        electro_overrides / physics_overrides: optional overrides per
            builder semantics.
        overwrite: when False (default), an existing
            ``case_dir/constant/electroProperties`` raises FileExistsError.
        dry_run: when True, writes the dicts and returns without
            running the engine.
        pre_solve_commands: optional commands to run in ``case_dir`` before
            ``cardiacFoam``. Each item is a string (shell-split) or a list of
            strings. Example: ``["vtkUnstructuredToFoam",
            "setTorsoOrganConductivityField"]``.
        openfoam_bashrc: when set, each command is run after sourcing this
            OpenFOAM bashrc.
        dx: mesh resolution (metres, isotropic cell size) for the generic
            default ``blockMeshDict`` provisioned for spatial solvers with no
            author-supplied mesh. Only meaningful for
            ``monodomainSolver``/``bidomainSolver``/``eikonalSolver``; raises
            ``ValueError`` for ``singleCellSolver`` (no spatial geometry)
            rather than silently having no effect, and if it does not evenly
            divide the default slab's fixed size (no silent rounding).
            Meaningless for real anatomical meshes imported via
            ``vtkUnstructuredToFoam`` -- this only controls the generic
            default slab.
        include_allrun: when True (Phase 3 Task 10, bypass 5), a
            hand-runnable ``Allrun`` joins the same committed plan as the
            dictionaries above -- see ``build_case``'s own docstring for
            the exact rule. ``sweep.py::materialize_case`` is the one
            production caller and always passes True; every other caller
            (tests, a direct launch with no sweep involved) keeps the
            pre-existing default of no ``Allrun`` at all.

    Returns:
        A dict carrying ``case_dir`` (str) and either
        ``status="dry_run_complete"`` or the engine result list under
        ``results``.

    Raises:
        FileExistsError: case_dir/constant/electroProperties exists and
            overwrite=False.
        ValueError: validator rejected one of the synthesized dicts.
    """
    from pathlib import Path as _Path

    from omnidriver.core.case_transaction import commit_case_write

    # Made absolute if not already, without disturbing an already-absolute
    # path's spelling: see the matching comment in `build_case`
    # (R3 blocker 2, 2026-09-23).
    case_dir = _Path(case_dir)
    if not case_dir.is_absolute():
        case_dir = case_dir.resolve()
    electro_path = case_dir / "constant" / "electroProperties"

    # Preserved as a direct check, not a channel precondition (2026-09-23,
    # Phase 2 Task 9): the pre-existing regression test
    # test_dict_builder.py::test_existing_case_dir_is_not_overwritten_without_consent
    # asserts this exact FileExistsError type. Routing it through
    # commit_case_write's precondition recheck instead would surface it as
    # CaseTransactionError -- a real option (the plan's own Task 9 snippet
    # assumes exactly that), but not one this migration commit takes, since
    # it would break that external-facing exception contract for no
    # behavioural gain.
    if electro_path.exists() and not overwrite:
        raise FileExistsError(
            f"{electro_path} already exists; pass overwrite=True to replace."
        )

    # The case-write lease and the transaction journal both live case-
    # adjacent (`.omnidriver/` under `case_root`), so a case root that does
    # not exist yet -- the common case, a from-scratch case_dir -- has
    # nowhere for either to be recorded. Old code got this for free from
    # `constant_dir.mkdir(parents=True, exist_ok=True)` before its first bare
    # `write_text`; `commit_case_write`'s atomic replace creates a WRITE
    # TARGET's parent directories itself, but not the case root the lease
    # needs before any target is even known.
    case_dir.mkdir(parents=True, exist_ok=True)

    myocardium_solver = electro_selectors.get("myocardiumSolver", "monodomainSolver")

    # `own_driver_context()`, not the caller's `driver_context` -- matching
    # `build_electro_properties`/`build_physics_properties`'s own existing
    # behaviour, which already validates against `own_driver_context()`
    # regardless of what this function's caller passed. The `driver_context`
    # PARAMETER is reserved for the launch phase below, exactly as before
    # this migration; threading it into the write phase too would be a
    # behaviour change (a caller-supplied context previously had zero
    # influence on what got written).
    write_context = driver_context if driver_context is not None else own_driver_context()
    plan = build_case(
        electro_selectors, physics_selectors=physics_selectors, case_dir=case_dir,
        electro_overrides=electro_overrides, physics_overrides=physics_overrides,
        overwrite=overwrite, delta_t=delta_t, end_time=end_time, dx=dx,
        dry_run=dry_run, include_allrun=include_allrun, driver_context=write_context,
    )
    commit_case_write(plan, driver_context=write_context, execution_env=None)

    # `needs_block_mesh` is pure set membership -- `_block_mesh_solvers()`
    # already computes exactly it -- so it no longer costs a call to a
    # function that can write bytes (R3 finding 7, 2026-09-23).
    needs_block_mesh = myocardium_solver in _block_mesh_solvers()

    # Migrated 2026-09-23 (Task 12, batch P2-H): `MESHLESS_SOLVERS`' bundled
    # 1-cell polyMesh fixture used to be copied here via a direct
    # `provision_mesh(...)` call, bypassing `commit_case_write` entirely.
    # `build_case` above now folds those same five files into its own plan
    # (as `skip_if_present` synthesis targets, excluded under `dry_run` --
    # see its docstring), so this branch has nothing left to do:
    # `commit_case_write` just wrote them, journaled, the same way it wrote
    # every other case document. `provision_mesh` is still the right tool
    # for `ionic_catalog_verification.py`'s direct use, which does not go
    # through `build_and_launch`. **Corrected 2026-09-24 (Phase 3 Task 10):**
    # "provision_mesh itself is unchanged" no longer holds -- its
    # BLOCK_MESH_SOLVERS branch (dead: `ionic_catalog_verification.py`
    # always calls it with `myocardium_solver="singleCellSolver"`) was
    # deleted. `ionic_catalog_verification.py`'s own call is unaffected,
    # since it only ever takes the MESHLESS_SOLVERS branch, which this
    # task did not touch.

    if dry_run:
        return {
            "case_dir": str(case_dir),
            "status": "dry_run_complete",
            "needs_block_mesh": needs_block_mesh,
        }

    from omnidriver.core.compatibility import resolve_public_driver_context

    driver_context = resolve_public_driver_context(driver_context)
    make_spec = driver_context.capabilities.tutorials.catalog()["make_generic_case_spec"]
    from omnidriver.core.runtime.execution_context import resolve_execution_context
    from omnidriver.openfoam.openfoam_environment import load_openfoam_environment
    from omnidriver.core.runtime.workflow import normalize_workflow_dag, validate_workflow_commands
    from omnidriver.core.runtime.workflow_orchestrator import run_workflow
    from omnidriver.core.runtime.workflow_state import initial_workflow_state

    spec = make_spec(
        cases_root=case_dir.parent,
        case_dir_name=case_dir.name,
        solver_command="cardiacFoam",
        pre_solve_commands=list(pre_solve_commands or ()),
        explicit_bashrc=openfoam_bashrc,
    )
    execution_context = resolve_execution_context(spec)
    workflow_dag, _dag_diagnostics = normalize_workflow_dag(
        spec.metadata.get("workflow_dag"), driver_context=driver_context,
    )
    command_diagnostics = validate_workflow_commands(
        workflow_dag, driver_context=driver_context,
    )
    if command_diagnostics:
        raise ValueError(
            "build_and_launch's workflow_dag failed command validation: "
            + "; ".join(d.message for d in command_diagnostics)
        )

    env = load_openfoam_environment(explicit_bashrc=openfoam_bashrc).env
    outcome = run_workflow(
        workflow_dag,
        initial_workflow_state(workflow_dag),
        case_root=execution_context.case_root,
        output_dir=execution_context.output_dir,
        env=env,
    )
    return {
        "case_dir": str(case_dir),
        "status": "complete" if outcome.state.status == "completed" else "failed",
        "workflow_state": outcome.state.to_json(),
    }
