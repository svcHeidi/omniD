from __future__ import annotations

import datetime
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping

from omnidriver.core.case_transaction import CaseTransactionError, commit_case_write
from omnidriver.core.case_write import (
    CaseMutationRequest,
    CaseWritePlan,
    ParameterAssignment,
    RenderedFile,
    ResolvedMutation,
    _digest_bytes,
)
from omnidriver.core.runtime.attempt_lease import case_lease_is_held

from . import case_rendering
from .literals import (
    parse_boolean_literal,
    parse_dimensioned_literal,
    parse_integer_list_literal,
    parse_scalar_list_literal,
    parse_vector3_list_literal,
    parse_vector3_literal,
    parse_word_list_literal,
)
from .mutators import update_foam_entry

if TYPE_CHECKING:
    from omnidriver.core.plugin_interface import DriverContext

#: This module's identity on every `ParameterAssignment`/`CaseMutationRequest`
#: it produces (Phase 3 Task 5, "--apply joins the channel"). Deliberately
#: not a solver plugin's own identity (e.g. cardiacFoam's `"org.cardiacfoam"`):
#: this module resolves overrides against WHICHEVER plugin's declared
#: `override_scopes`/`dict_regeneration` the composed stack carries, so it
#: cannot claim to be any one of them.
_OWNER = "org.omnidriver.openfoam.apply_overrides"


@dataclass(frozen=True)
class OverrideScope:
    """One ``$TOKEN.`` override scope a plugin declares for `step --strict
    --apply`.

    token: the bare scope name after ``$`` and before the first ``.`` (e.g.
        ``"ELECTRO_MODEL_COEFFS"`` for ``"$ELECTRO_MODEL_COEFFS.myocardiumSolver"``).
    file_relpath: the case-relative dict file this scope's overrides write
        into (e.g. ``"constant/electroProperties"``).
    catalog_group: the dictionary-catalog group name this scope's overrides
        are validated against (``DictionaryCatalogCapability.catalog()
        .entries_for(catalog_group)``).
    resolve_entry: given the full ``driver_path`` and the case root, return
        ``(scope_path, key)`` ready for
        :func:`omnidriver.openfoam.mutators.update_foam_entry`.
        Plugin-owned: how a token's dotted suffix maps onto nested OpenFOAM
        scope segments is catalog-specific (e.g. which ``<solver>Coeffs``
        block is active for this case), not something core can infer.
    """

    token: str
    file_relpath: str
    catalog_group: str
    resolve_entry: Callable[[str, Path], tuple[list[str] | None, str]]


@dataclass(frozen=True)
class RegenerationScope:
    """One bare (non-``$``-prefixed) "selector" override a plugin declares
    for `step --strict --apply` that must REGENERATE a dict file rather
    than key-patch it, because changing the value restructures the file --
    renames a sub-block, changes which sibling keys are legal -- instead of
    changing one leaf in place. The motivating case is cardiacFoam's
    ``myocardiumSolver``: switching it renames ``<oldSolver>Coeffs`` to
    ``<newSolver>Coeffs`` and flips which keys the catalog's
    ``applicable_when``/``required_when``/``forbidden_when`` predicates
    allow, none of which ``update_foam_entry`` (a single key/value/scope
    patch) can express.

    selector_keys: the bare ``driver_path`` names this scope owns (e.g.
        ``{"myocardiumSolver"}`` for the cardiac plugin). Deliberately a
        small, explicit set: a selector only belongs here if changing it
        actually restructures the file. Plain leaf selectors that only
        change a value in place (e.g. cardiacFoam's ``ionicModel``,
        ``tissue``) stay on the ordinary ``$TOKEN.`` :class:`OverrideScope`
        path instead -- routing them through regeneration too would be a
        capability the catalog does not need yet.
    file_relpath: the case-relative dict file this scope regenerates (e.g.
        ``"constant/electroProperties"``).
    catalog_group: the dictionary-catalog group name used to validate enum
        values for these selector keys (mirrors
        :attr:`OverrideScope.catalog_group`).
    regenerate: given the on-disk file path, the full ``driver_path``, the
        new value, and any OTHER ``$TOKEN.``-scoped overrides from the same
        `step --strict --apply` call that target this same
        ``file_relpath`` (``{driver_path: value}``, empty if none),
        rewrite the file in place from its current content with that one
        selector changed. The extra-overrides map exists because
        ``update_foam_entry`` can only patch a key that already exists --
        a solver switch can make a *new* key required with no catalog
        default (e.g. eikonalSolver's ``stimulusLocationMin``, absent from
        a monodomain source and un-defaultable, case-specific geometry),
        and there would otherwise be no way for such a value to reach the
        file: too late to key-patch it in afterward (nothing to patch),
        and the rebuild has no default to fall back on. Plugin-owned: how
        to decompose the existing file into selectors/overrides, rebuild
        it, and preserve whatever the rebuild pipeline cannot itself
        round-trip is catalog-specific, not something core can infer.
    """

    selector_keys: frozenset[str]
    file_relpath: str
    catalog_group: str
    regenerate: Callable[[Path, str, str, dict[str, str]], None]


def _is_safe_system_path(path_str: str) -> bool:
    """Validate that the path is strictly inside system/ and has no traversal segments."""
    if not path_str.startswith("system/"):
        return False
    path = PurePath(path_str)
    return not path.is_absolute() and ".." not in path.parts


class OverrideError(ValueError):
    """An override is malformed, non-applyable, out-of-enum, or failed to apply."""


def _catalog_entries(
    driver_context: "DriverContext",
) -> tuple[set[str], dict[str, Any], tuple[OverrideScope, ...], tuple[RegenerationScope, ...]]:
    catalog = driver_context.capabilities.dictionaries.catalog()
    scopes = driver_context.capabilities.override_scopes.scopes()
    regeneration_scopes = driver_context.capabilities.dict_regeneration.scopes()
    scoped_entries: dict[str, Any] = {}
    for scope in scopes:
        for entry in catalog.entries_for(scope.catalog_group):
            scoped_entries[entry.driver_path] = entry
    for regen_scope in regeneration_scopes:
        for entry in catalog.entries_for(regen_scope.catalog_group):
            scoped_entries.setdefault(entry.driver_path, entry)
    return (
        {entry.driver_path for entry in catalog.entries_for("controlDict")},
        scoped_entries,
        scopes,
        regeneration_scopes,
    )


def _match_dynamic_entry(dp: str, all_entries: Iterable[Any]) -> Any | None:
    """Return the dynamic catalog entry whose template matches concrete *dp*."""
    for entry in all_entries:
        if not getattr(entry, "dynamic_path", False):
            continue

        template = entry.driver_path
        pattern_parts: list[str] = []
        previous_end = 0
        for placeholder in re.finditer(r"<[^.<>]+>", template):
            pattern_parts.append(re.escape(template[previous_end:placeholder.start()]))
            pattern_parts.append(r"[^.]+")
            previous_end = placeholder.end()
        pattern_parts.append(re.escape(template[previous_end:]))

        if re.fullmatch("".join(pattern_parts), dp):
            return entry
    return None


def _scope_token(dp: str) -> str:
    """Return the bare token between "$" and the first "." (or the whole
    remainder if there is no "."). ``dp`` must already be known to start
    with "$"."""
    return dp[1:].split(".", 1)[0]


def _document_relpath_for(
    dp: str,
    *,
    scope_by_token: dict[str, "OverrideScope"],
    regen_scope_by_key: dict[str, "RegenerationScope"],
) -> str:
    """The case-relative document one override's ``driver_path`` addresses.

    Factored out of ``override_target_paths`` (2026-09-23, Phase 3 Task 5) so
    the channel migration's own document-set computation (which relpaths to
    snapshot-copy before staging) shares one routing decision with the
    existing path-safety check, rather than a second copy that could drift
    from it. ``dp`` must already have passed ``validate_overrides``.
    """
    if ":" in dp:
        return dp.partition(":")[0]
    if dp in regen_scope_by_key:
        return regen_scope_by_key[dp].file_relpath
    if dp.startswith("$"):
        return scope_by_token[_scope_token(dp)].file_relpath
    return "system/controlDict"


def validate_overrides(overrides: Any, *, driver_context: "DriverContext") -> None:
    """Reject anything not safely applyable, *before* any write. Raises OverrideError."""
    if not isinstance(overrides, list):
        raise OverrideError(
            "overrides payload must be a JSON list of {driver_path, value} objects"
        )
    control_dict_keys, scoped_entries, scopes, regeneration_scopes = _catalog_entries(driver_context)
    scope_by_token = {scope.token: scope for scope in scopes}
    regen_scope_by_key: dict[str, RegenerationScope] = {
        key: regen_scope
        for regen_scope in regeneration_scopes
        for key in regen_scope.selector_keys
    }
    for ov in overrides:
        if not isinstance(ov, dict) or "driver_path" not in ov or "value" not in ov:
            raise OverrideError(
                f"each override must be an object with 'driver_path' and 'value' (got {ov!r})"
            )
        dp = ov["driver_path"]
        if not isinstance(dp, str) or not dp:
            raise OverrideError("override driver_path must be a non-empty string")
        if ":" in dp:
            file_path, _, entry_path = dp.partition(":")
            if not _is_safe_system_path(file_path):
                raise OverrideError(f"override file path {file_path!r} is not a safe system/ path")
            if not entry_path:
                raise OverrideError(f"override driver_path {dp!r} is missing an entry path after ':'")
            continue
        elif not dp.startswith("$"):
            if dp in regen_scope_by_key:
                # A bare selector that RESTRUCTURES the file (renames a
                # sub-block, changes which sibling keys are legal) rather
                # than patching one leaf in place -- e.g. myocardiumSolver.
                # Still enum-checked against the catalog exactly like any
                # other entry; only the *application* differs (regenerate
                # vs. key-patch), not the trust boundary.
                entry = scoped_entries.get(dp)
                enum_values = getattr(entry, "enum_values", None)
                if enum_values and ov["value"] not in enum_values:
                    raise OverrideError(
                        f"override {dp!r} value {ov['value']!r} not in enum {tuple(enum_values)}"
                    )
                continue
            # Backward compatibility: flat strings are treated as controlDict entries.
            # Still must be a real controlDict key -- otherwise this silently passes
            # validation and, at apply time, either raises a raw KeyError (no
            # foamDictionary) or silently writes a brand-new bogus key into
            # controlDict (foamDictionary auto-creates missing keys on `-set`).
            if dp not in control_dict_keys:
                known = ", ".join(sorted(control_dict_keys))
                raise OverrideError(
                    f"override driver_path {dp!r} is not a known controlDict entry. "
                    f"Known controlDict entries: {known}"
                )
            continue

        if "<" in dp or ">" in dp:
            raise OverrideError(
                f"override driver_path {dp!r} contains a placeholder; substitute the "
                f"concrete name"
            )

        token = _scope_token(dp)
        if token not in scope_by_token:
            known = ", ".join(f"${t}" for t in sorted(scope_by_token)) or "(none declared)"
            raise OverrideError(
                f"override driver_path {dp!r} uses unknown scope token {'$' + token!r}. "
                f"Known scope tokens: {known}"
            )

        entry = scoped_entries.get(dp)
        if entry is None:
            entry = _match_dynamic_entry(dp, scoped_entries.values())
            if entry is None:
                raise OverrideError(
                    f"override driver_path {dp!r} is not catalog-addressable / applyable"
                )
        enum_values = getattr(entry, "enum_values", None)
        if enum_values and ov["value"] not in enum_values:
            raise OverrideError(
                f"override {dp!r} value {ov['value']!r} not in enum {tuple(enum_values)}"
            )


def apply_overrides(
    overrides: list[dict[str, Any]],
    *,
    case_root: Path,
    driver_context: "DriverContext",
    execution_env: Mapping[str, str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Apply overrides through the case-write channel (Phase 3 Task 5,
    "--apply joins the channel" -- bypass 4).

    Validate routing before any writes, exactly as before. What changes is
    where the writes land: every touched document is staged into a private
    snapshot (case_root is never read or written directly), a
    `CaseMutationRequest`/`ParameterAssignment` per override describes what
    is about to change, and `case_transaction.commit_case_write` replaces
    the real files atomically, journalled, with automatic rollback on
    failure -- case_root is untouched on any validation or staging failure
    (stronger than the pre-channel `_restore_on_failure`, which restored
    case_root only after writing to it), and crash-recoverable via the
    journal on a failure during the commit itself, which no prior mechanism
    on this path provided at all.

    `commit_case_write` is called with ``case_lease_held=True`` when this
    thread already holds the case lease -- true for `--apply` reached via
    `cli.py`'s `--apply` dispatch (`_dispatch_context` holds it for the
    whole `step`), which is why `case_transaction.py` grew that parameter.
    A standalone caller (e.g. this module's own unit tests, calling
    `apply_overrides()` directly with no lease held) is unaffected: the
    flag is only passed when a held lease is actually detected, and
    `commit_case_write` acquires its own otherwise, exactly as it always has.
    """
    validate_overrides(overrides, driver_context=driver_context)
    if not overrides:
        # `clone_and_patch` requires at least one parameter
        # (`CaseMutationRequest.__post_init__`); an override list that
        # resolves to nothing is a no-op, not a mutation with zero effects
        # -- the same rule `cardiaccore.workflows.overrides
        # .apply_input_overrides_planned` already applies. Matches this
        # function's own pre-channel behaviour: `apply_overrides([], ...)`
        # has always been a well-defined no-op
        # (`test_applying_overrides_is_supported`).
        return ()

    case_root = Path(case_root)
    scope_by_token = {
        scope.token: scope
        for scope in driver_context.capabilities.override_scopes.scopes()
    }
    regen_scope_by_key: dict[str, RegenerationScope] = {
        key: regen_scope
        for regen_scope in driver_context.capabilities.dict_regeneration.scopes()
        for key in regen_scope.selector_keys
    }
    _, scoped_entries, _, _ = _catalog_entries(driver_context)
    controldict_entries = _control_dict_entries(driver_context)

    # Re-validates and raises OverrideError on a symlinked/escaping target
    # BEFORE anything is staged -- override_target_paths's own refusal,
    # unchanged; its return value itself isn't otherwise needed below,
    # which computes case-relative strings (for the snapshot copy and
    # RenderedFile.path) via the same routing decision.
    override_target_paths(overrides, case_root=case_root, driver_context=driver_context)
    relpaths = sorted({
        _document_relpath_for(
            ov["driver_path"], scope_by_token=scope_by_token,
            regen_scope_by_key=regen_scope_by_key,
        )
        for ov in overrides
    })

    with tempfile.TemporaryDirectory(prefix="omnidriver-apply-render-") as scratch:
        snapshot_root = Path(scratch)
        for relpath in relpaths:
            case_rendering._snapshot_copy(case_root, snapshot_root, relpath)

        parameters = _stage_overrides_into_snapshot(
            overrides,
            snapshot_root=snapshot_root,
            scope_by_token=scope_by_token,
            regen_scope_by_key=regen_scope_by_key,
            scoped_entries=scoped_entries,
            controldict_entries=controldict_entries,
        )

        rendered: list[RenderedFile] = []
        for relpath in relpaths:
            source = case_root / relpath
            # Every relpath above was written by _stage_overrides_into_snapshot
            # without raising, which -- since every route requires its target
            # to already exist (add_if_missing is never set) -- proves this
            # source existed the whole time and is untouched (only the
            # snapshot copy was ever written to).
            before_digest = _digest_bytes(source.read_bytes())
            mode = source.stat().st_mode & 0o7777
            content = (snapshot_root / relpath).read_bytes()
            rendered.append(RenderedFile(
                path=relpath, content=content, mode=mode, exists_before=True,
                before_digest=before_digest, renderer_id=_OWNER,
                format=case_rendering.FORMAT,
            ))

        request = CaseMutationRequest(
            mode="clone_and_patch", case_root=case_root, adapter_id=_OWNER,
            workflow="apply_overrides", source_artifacts=(), parameters=tuple(parameters),
            requested_by="openfoam.apply_overrides",
        )
        targets = tuple(
            {
                "qualified_id": parameter.qualified_id,
                "document": parameter.document,
                "expanded_key_path": list(parameter.expanded_key_path()),
                "value": parameter.value,
                "format": case_rendering.FORMAT,
            }
            for parameter in parameters
        )
        resolved = ResolvedMutation(
            request=request, targets=targets, preconditions=(),
            expected_effects=tuple(
                f"apply override {parameter.qualified_id!r}" for parameter in parameters
            ),
            semantic_owner_id=_OWNER,
        )
        # Gives the `environment` precondition kind (declared in
        # `core.case_write`, implemented here, checked in
        # `core.case_transaction`) its second real emitter -- until now the
        # only caller was cardiacCore's Task 8 channel consumer
        # (`workflows.overrides.apply_input_overrides_planned`). Discharges
        # the note Task 1 Step 3 recorded ("implemented-and-thin").
        preconditions = case_rendering.patch_preconditions(
            resolved, case_root=case_root, execution_env=execution_env,
        )
        identity = getattr(driver_context, "identity", None)
        stack_identity = (
            identity.capability_digest if identity is not None else "0" * 64
        )
        plan = CaseWritePlan(
            request=request, files=tuple(rendered), preconditions=preconditions,
            semantic_owner_id=_OWNER, stack_identity=stack_identity,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    try:
        commit_case_write(
            plan, driver_context=driver_context, execution_env=execution_env,
            case_lease_held=case_lease_is_held(case_root),
        )
    except CaseTransactionError as exc:
        raise OverrideError(f"failed to commit overrides: {exc}") from exc

    if execution_env is None:
        return ()

    from .effective_dictionary import resolve_effective_foam_entry

    evidence: list[dict[str, Any]] = []
    for override in overrides:
        driver_path = override["driver_path"]
        if ":" in driver_path:
            relpath, _, entry_path = driver_path.partition(":")
        elif driver_path in regen_scope_by_key:
            relpath = regen_scope_by_key[driver_path].file_relpath
            entry_path = driver_path
        elif driver_path.startswith("$"):
            scope = scope_by_token[_scope_token(driver_path)]
            scope_path, key = scope.resolve_entry(driver_path, case_root)
            relpath = scope.file_relpath
            entry_path = "/".join((*(scope_path or ()), key))
        else:
            relpath = "system/controlDict"
            entry_path = driver_path
        result = resolve_effective_foam_entry(
            case_root / relpath,
            entry_path,
            bashrc=None,
            env=execution_env,
        )
        evidence.append({
            "driver_path": driver_path,
            "requested_value": override["value"],
            # Raw spellings are preserved on both sides: `requested_value`
            # above and `value` from `asdict(result)` below. `matches_requested`
            # is a typed comparison of the two, not a rewrite of either.
            "matches_requested": (
                result.status == "resolved"
                and effective_values_agree(override["value"], result.value)
            ),
            **asdict(result),
        })
    return tuple(evidence)


def override_target_paths(
    overrides: list[dict[str, Any]],
    *,
    case_root: Path,
    driver_context: "DriverContext",
) -> tuple[Path, ...]:
    """Resolve the complete finite mutation target set without writing."""
    validate_overrides(overrides, driver_context=driver_context)
    scope_by_token = {
        scope.token: scope
        for scope in driver_context.capabilities.override_scopes.scopes()
    }
    regen_scope_by_key: dict[str, RegenerationScope] = {
        key: regen_scope
        for regen_scope in driver_context.capabilities.dict_regeneration.scopes()
        for key in regen_scope.selector_keys
    }
    paths: set[Path] = set()
    for ov in overrides:
        dp = ov["driver_path"]
        relpath = _document_relpath_for(
            dp, scope_by_token=scope_by_token, regen_scope_by_key=regen_scope_by_key,
        )
        target = case_root / relpath
        resolved_root = case_root.resolve()
        if (
            not target.parent.resolve().is_relative_to(resolved_root)
            or not target.resolve().is_relative_to(resolved_root)
        ):
            raise OverrideError(f"override target is outside the case: {relpath}")
        if target.is_symlink():
            raise OverrideError(
                f"override target may not be a symlink: {relpath}"
            )
        paths.add(target)
    return tuple(sorted(paths))


def _effective_value_text(value: Any) -> str:
    """Render an override as the scalar text the native query must observe."""
    from .mutators import _format_value

    return _format_value(value).strip()


def _as_comparable_text(text: str):
    """Parse one native scalar/word/vector spelling into a comparable value.

    Returns a float for a number, a bool for an OpenFOAM boolean word, a tuple
    of floats for a parenthesised vector, and the stripped text otherwise.
    """
    stripped = text.strip().rstrip(";").strip()
    if not stripped:
        return None
    if stripped in {"true", "yes", "on"}:
        return True
    if stripped in {"false", "no", "off"}:
        return False
    if stripped.startswith("(") and stripped.endswith(")"):
        parts = stripped[1:-1].split()
        try:
            return tuple(float(part) for part in parts)
        except ValueError:
            return stripped
    try:
        return float(stripped)
    except ValueError:
        return stripped


def _as_comparable(value: Any):
    """Parse a requested override *or* a native resolution into a comparable
    value, dispatching on the Python type actually in hand.

    A number becomes a ``float``, an OpenFOAM boolean word or a Python ``bool``
    stays a ``bool``, a list/tuple and a parenthesised vector string both
    become a tuple of floats, and anything else is compared as text.

    Corrected 2026-09-22 (audit finding F1b, second pass): the first draft
    always rendered the *requested* side through ``_effective_value_text``
    (``str(value)``) before parsing it back. ``str([1, 2, 3])`` is the Python
    literal ``"[1, 2, 3]"``, not the OpenFOAM vector spelling ``"(1 2 3)"``, so
    a correct vector override compared unequal to its own resolution. Dispatch
    on the requested value's own type instead of round-tripping it through
    text formatting meant for writing a dictionary, not for comparison.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)):
        try:
            return tuple(float(item) for item in value)
        except (TypeError, ValueError):
            return tuple(value)
    if isinstance(value, str):
        return _as_comparable_text(value)
    return value


def effective_values_agree(requested: Any, resolved: str | None) -> bool:
    """Whether a native resolution is the value that was requested.

    Compared as parsed values, not as text: a requested ``1e-3`` resolves
    through ``foamDictionary`` as ``0.001``, and rejecting that is rejecting a
    correct edit. Added 2026-09-22 (audit finding F1b).

    Deliberately NOT a tolerance. ``0.001`` and ``0.0010000001`` are different
    configurations, and a comparison that calls them equal hides exactly the
    drift this check exists to find. The raw spellings are preserved in the
    evidence record either way, so a reader can always see what was written and
    what came back.

    An unparseable or absent resolution is not agreement. "I could not read it"
    is reported as a non-match so the caller sees an unverified edit, never a
    passed check.
    """
    if resolved is None:
        return False
    left = _as_comparable(requested)
    right = _as_comparable_text(resolved)
    if left is None or right is None:
        return False
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right


#: value_kind -> text-to-typed parser, for a raw string override value that
#: needs interpreting before it fits `validate_value_shape`'s closed shape
#: vocabulary. Mirrors `omnidriver.cardiacfoam.overrides._TEXT_PARSERS`
#: (same reasoning, same `omnidriver.openfoam.literals` functions -- see
#: that module's own docstring on why parsing lives there and not here) but
#: widened with `scalar`/`integer`: cardiacFoam's tutorial call sites always
#: pass an already-typed Python float for those two kinds (Task 3's own
#: finding), but `--apply` values arrive from the CLI and `sweep.json` as
#: strings (``{"driver_path": "deltaT", "value": "0.0005"}``), so this route
#: needs a parser those production call sites never did. `word`/`enum` are
#: excluded: a JSON string already IS the correct shape for those, and
#: `validate_value_shape` accepts any non-empty, whitespace-free string
#: (a plausible number like "1e-6" is a perfectly valid "word" spelling too).
_TEXT_PARSERS: dict[str, Callable[[str], Any]] = {
    "scalar": lambda text: _parse_number_text(text, what="scalar"),
    "integer": lambda text: _parse_integer_text(text),
    "boolean": parse_boolean_literal,
    "dimensioned_scalar": parse_dimensioned_literal,
    "dimensioned_tensor": parse_dimensioned_literal,
    "vector3": parse_vector3_literal,
    "word_list": parse_word_list_literal,
    "scalar_list": parse_scalar_list_literal,
    "integer_list": parse_integer_list_literal,
    "vector3_list": parse_vector3_list_literal,
}

def _parse_number_text(text: str, *, what: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{text!r} is not a {what}") from exc


def _parse_integer_text(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        pass
    number = _parse_number_text(text, what="integer")
    if not number.is_integer():
        raise ValueError(f"{text!r} is not an integer")
    return int(number)


def _typed_value_for_apply(value_kind: str, value: Any) -> tuple[Any, tuple[str, ...]]:
    """The typed value a `ParameterAssignment` records, plus any raw-text
    evidence to write back verbatim.

    Mirrors `cardiaccore.overrides._typed_value_for_entry` /
    `cardiacfoam.overrides._typed_value_for_entry` (Gap 1's "the raw
    spelling is still evidence"): unlike those two, the caller here
    (`_stage_overrides_into_snapshot`) does not use this typed value or its
    evidence to decide what gets WRITTEN at all -- the write call already
    happened with the raw override value, unchanged from the pre-channel
    write path, which is what guarantees byte-for-byte parity with it. This
    function exists purely to produce a typed, shape-valid value for the
    `ParameterAssignment` AUDIT record; `evidence_refs` records the original
    spelling there too, so a reader of the plan can see what was actually
    typed even though it is not what drove the write.
    """
    parse = _TEXT_PARSERS.get(value_kind)
    if parse is not None and isinstance(value, str):
        return parse(value), (value,)
    return value, ()


def _inferred_value_kind(value: Any) -> str | None:
    """A `value_kind` for an override this module's catalog cannot
    declare -- the ``system/<file>:<entry>`` route, which
    `validate_overrides` only path-safety-checks, never catalog-validates
    (see its own docstring). Dispatches on the Python type actually in
    hand, never on whether the text *looks* numeric: `validate_value_shape`
    accepts any non-empty, whitespace-free string as a "word", including one
    that also happens to parse as a number ("1e-6"), so classifying every
    such string as "word" is not imprecise -- it is the most conservative
    true statement this route can make with no catalog entry to consult.
    ``None`` means genuinely unclassifiable (empty string, a string
    containing whitespace, or an unsupported JSON type such as a list or a
    mapping) -- refused by the caller rather than guessed at.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "scalar"
    if isinstance(value, str) and value and value.split() == [value]:
        return "word"
    return None


def _control_dict_entries(driver_context: "DriverContext") -> dict[str, Any]:
    """driver_path -> `DictEntry`, for every controlDict entry the catalog
    declares -- `_catalog_entries` discards everything but the bare path
    set (`validate_overrides` only ever needed membership), so this is
    built separately, for the one extra fact the channel needs: each
    entry's `value_kind`.
    """
    catalog = driver_context.capabilities.dictionaries.catalog()
    return {entry.driver_path: entry for entry in catalog.entries_for("controlDict")}


def _catalog_entry_for_apply(
    dp: str,
    *,
    scoped_entries: dict[str, Any],
) -> Any | None:
    """The catalog `DictEntry` a ``$TOKEN.``/regeneration-selector
    ``driver_path`` addresses -- the direct-or-dynamic match
    `validate_overrides` already performed to accept ``dp`` in the first
    place (see that function), re-run here for the one additional fact it
    does not return: the matched entry's `value_kind`. Kept as its own,
    small function rather than threading a return value back through
    `validate_overrides` -- that function's control flow (and its 20-plus
    pinned error messages) stays untouched; this duplicates roughly four
    lines of matching, not `validate_overrides`'s trust decisions."""
    entry = scoped_entries.get(dp)
    if entry is not None:
        return entry
    return _match_dynamic_entry(dp, scoped_entries.values())


def _stage_overrides_into_snapshot(
    overrides: list[dict[str, Any]],
    *,
    snapshot_root: Path,
    scope_by_token: dict[str, OverrideScope],
    regen_scope_by_key: dict[str, RegenerationScope],
    scoped_entries: dict[str, Any],
    controldict_entries: dict[str, Any],
) -> list[ParameterAssignment]:
    """Apply every override into `snapshot_root`, building one
    `ParameterAssignment` per override as a byproduct.

    Byte-for-byte the same routing and write calls as the pre-channel
    `_apply_validated_overrides` (removed 2026-09-23, Phase 3 Task 5) --
    ``case_root`` replaced by ``snapshot_root`` throughout, so `case_root`
    is never read or written by this function at all. `scope.resolve_entry`
    and `regen_scope.regenerate` are given `snapshot_root` too (not the real
    `case_root`), which is what preserves the one behaviour that a naive
    "copy touched files, then apply" split would have broken: within a
    single `apply_overrides()` call, cardiacFoam's `resolve_entry` detects
    the ACTIVE `<solver>Coeffs` block by reading `constant/electroProperties`
    (see `overrides._resolve_electro_model_coeffs_entry`) -- the same file a
    prior override in the SAME call may have just regenerated. Passing
    `snapshot_root` throughout means a later override's `resolve_entry` sees
    that prior write, exactly as it would reading `case_root` directly today;
    passing the untouched `case_root` instead would silently resolve against
    the pre-regeneration solver.

    The caller has already copied every document `override_target_paths`
    names into `snapshot_root`, so every read/write below targets a file
    that already exists there -- an override addressing one that does not
    exist under the real case still raises the same `FileNotFoundError`,
    now surfacing from the snapshot copy instead of `case_root` (message
    unchanged; only the path differs), wrapped into `OverrideError` exactly
    as before.
    """
    parameters: list[ParameterAssignment] = []
    for ov in overrides:
        dp, value = ov["driver_path"], ov["value"]
        try:
            if ":" in dp:
                file_path, _, entry_path = dp.partition(":")
                # foamDictionary spells this scope as "solvers/V/tolerance";
                # update_foam_entry takes it apart. Going through it rather
                # than straight to foamDictionary keeps this route usable
                # without a sourced OpenFOAM, like every other override path.
                *scope_path, key = entry_path.split("/")
                update_foam_entry(
                    snapshot_root / file_path, key, value, scope=scope_path or None
                )
                document, key_path = file_path, tuple((*scope_path, key))
                kind = _inferred_value_kind(value)
                if kind is None:
                    raise ValueError(
                        f"value {value!r} has no closed shape this route can "
                        f"describe (expected a boolean, a number, or a single "
                        f"whitespace-free word); {dp!r} is not catalog-declared, "
                        f"so its value_kind cannot be looked up"
                    )
            elif not dp.startswith("$") and dp in regen_scope_by_key:
                regen_scope = regen_scope_by_key[dp]
                # Other $TOKEN. overrides in this same call that target the
                # scope's file: the rebuild needs to see these (not just
                # the selector) because update_foam_entry can only patch a
                # key that already exists, and the new solver may require
                # a key the old file never had (see RegenerationScope.regenerate).
                extra_overrides = {
                    other["driver_path"]: other["value"]
                    for other in overrides
                    if other is not ov
                    and str(other.get("driver_path", "")).startswith("$")
                    and scope_by_token.get(_scope_token(other["driver_path"])) is not None
                    and scope_by_token[_scope_token(other["driver_path"])].file_relpath
                    == regen_scope.file_relpath
                }
                regen_scope.regenerate(
                    snapshot_root / regen_scope.file_relpath, dp, value, extra_overrides,
                )
                document, key_path = regen_scope.file_relpath, (dp,)
                entry = _catalog_entry_for_apply(dp, scoped_entries=scoped_entries)
                if entry is None:
                    raise AssertionError(
                        f"{dp!r} routed as a regeneration selector but has no "
                        f"catalog entry; validate_overrides should have "
                        f"refused it already"
                    )
                kind = entry.value_kind
            elif not dp.startswith("$"):
                update_foam_entry(snapshot_root / "system" / "controlDict", dp, value)
                document, key_path = "system/controlDict", (dp,)
                entry = controldict_entries.get(dp)
                if entry is None:
                    raise AssertionError(
                        f"{dp!r} routed as a controlDict entry but has no "
                        f"catalog entry; validate_overrides should have "
                        f"refused it already"
                    )
                kind = entry.value_kind
            else:
                token = _scope_token(dp)
                scope = scope_by_token.get(token)
                if scope is None:
                    raise OverrideError(f"unknown scope token {'$' + token!r}")
                scope_path, key = scope.resolve_entry(dp, snapshot_root)
                update_foam_entry(
                    snapshot_root / scope.file_relpath, key, value, scope=scope_path,
                )
                document = scope.file_relpath
                key_path = tuple((*(scope_path or ()), key))
                entry = _catalog_entry_for_apply(dp, scoped_entries=scoped_entries)
                if entry is None:
                    raise AssertionError(
                        f"{dp!r} passed validate_overrides but matches no "
                        f"catalog entry here; the two lookups have drifted"
                    )
                kind = entry.value_kind
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            raise OverrideError(f"failed to apply override {dp!r}: {exc}") from exc

        typed_value, evidence_refs = _typed_value_for_apply(kind, value)
        parameters.append(ParameterAssignment(
            qualified_id=dp, owner=_OWNER, document=document, key_path=key_path,
            binding={}, value=typed_value, value_kind=kind, source="case",
            evidence_refs=evidence_refs,
        ))
    return parameters
