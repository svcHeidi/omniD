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
#: it produces. Not a solver plugin's own identity: this module resolves
#: overrides against whichever plugin's declared `override_scopes`/
#: `dict_regeneration` the composed stack carries, so it cannot claim to be
#: any one of them.
_OWNER = "org.omnidriver.openfoam.apply_overrides"


@dataclass(frozen=True)
class OverrideScope:
    """One ``$TOKEN.`` override scope a plugin declares for `step --strict
    --apply`.

    token: bare scope name after ``$`` and before the first ``.``.
    file_relpath: case-relative dict file this scope's overrides write into.
    catalog_group: catalog group its overrides are validated against.
    resolve_entry: given ``driver_path`` and the case root, returns
        ``(scope_path, key)`` for
        :func:`omnidriver.openfoam.mutators.update_foam_entry`. Plugin-owned:
        the mapping from a token's dotted suffix to nested OpenFOAM scope
        segments is catalog-specific.
    """

    token: str
    file_relpath: str
    catalog_group: str
    resolve_entry: Callable[[str, Path], tuple[list[str] | None, str]]


@dataclass(frozen=True)
class RegenerationScope:
    """One bare (non-``$``-prefixed) "selector" override a plugin declares
    for `step --strict --apply` that must regenerate a dict file rather than
    key-patch it, because changing the value restructures the file -- renames
    a sub-block, changes which sibling keys are legal -- instead of changing
    one leaf in place.

    selector_keys: the bare ``driver_path`` names this scope owns. Only
        selectors that actually restructure the file belong here; plain leaf
        selectors that change a value in place stay on the ordinary
        ``$TOKEN.`` :class:`OverrideScope` path.
    file_relpath: case-relative dict file this scope regenerates.
    catalog_group: catalog group used to validate enum values for these
        selector keys.
    regenerate: given the on-disk file path, the full ``driver_path``, the
        new value, and any other ``$TOKEN.``-scoped overrides from the same
        call targeting this same ``file_relpath`` (``{driver_path: value}``,
        empty if none), rewrite the file in place with that one selector
        changed. The extra-overrides map covers a key the new selector value
        requires but that ``update_foam_entry`` cannot patch because it does
        not yet exist in the file. Plugin-owned: decomposing and rebuilding
        the file is catalog-specific.
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
    """Bare token between ``$`` and the first ``.``; ``dp`` must start with ``$``."""
    return dp[1:].split(".", 1)[0]


def _document_relpath_for(
    dp: str,
    *,
    scope_by_token: dict[str, "OverrideScope"],
    regen_scope_by_key: dict[str, "RegenerationScope"],
) -> str:
    """The case-relative document one override's ``driver_path`` addresses;
    ``dp`` must already have passed ``validate_overrides``."""
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
                # A regeneration selector is enum-checked exactly like any
                # other entry; only the application differs.
                entry = scoped_entries.get(dp)
                enum_values = getattr(entry, "enum_values", None)
                if enum_values and ov["value"] not in enum_values:
                    raise OverrideError(
                        f"override {dp!r} value {ov['value']!r} not in enum {tuple(enum_values)}"
                    )
                continue
            # Must be a real controlDict key: foamDictionary auto-creates a
            # missing key on `-set`, so an unchecked one would silently write
            # a bogus new key instead of failing.
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
    """Validate every override's routing, then stage the writes into a
    private snapshot and commit them atomically via
    `case_transaction.commit_case_write`. ``case_root`` is never read or
    written directly, and is left untouched if validation, staging, or the
    commit itself fails.

    Raises `OverrideError` on a failed validation or a failed commit.
    """
    validate_overrides(overrides, driver_context=driver_context)
    if not overrides:
        # CaseMutationRequest.__post_init__ requires at least one parameter.
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

    # Re-validates and raises on a symlinked/escaping target before anything
    # is staged; the return value itself isn't needed here.
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
            # Every route requires its target to exist already, so source
            # is guaranteed to exist and is untouched here.
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
            expected_effects=resolved.expected_effects,
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
            # `matches_requested` is a typed comparison; the raw spellings
            # above and in `asdict(result)` below are left as-is.
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
    from .literals import _format_value

    return _format_value(value).strip()


def _as_comparable_text(text: str):
    """Parse one native scalar/word/vector spelling into a comparable value.

    Returns a float for a number, a bool for an OpenFOAM boolean word, a tuple
    of floats for a parenthesised or unparenthesised whitespace-separated
    vector (``blockMeshDict``'s hex-cell-counts convention omits the
    parentheses), and the stripped text otherwise.
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
    parts = stripped.split()
    if len(parts) > 1:
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
    value, dispatching on the Python type actually in hand rather than
    round-tripping through ``str()`` first (``str([1, 2, 3])`` is not the
    OpenFOAM vector spelling ``"(1 2 3)"``).

    A number becomes a ``float``, an OpenFOAM boolean word or a Python ``bool``
    stays a ``bool``, a list/tuple or vector string becomes a tuple of floats,
    and anything else is compared as text.
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
    """Whether a native resolution is the value that was requested, compared
    as parsed values rather than text (a requested ``1e-3`` resolves through
    ``foamDictionary`` as ``0.001``).

    Deliberately not a tolerance: two different values are never called
    equal. An unparseable or absent resolution is reported as a non-match,
    never a passed check.
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
#: vocabulary. Widened with `scalar`/`integer` beyond
#: `omnidriver.cardiacfoam.overrides._TEXT_PARSERS`: `--apply` values arrive
#: from the CLI and `sweep.json` as strings, unlike cardiacFoam's own
#: already-typed call sites. `word`/`enum` are excluded: a JSON string
#: already is the correct shape for those.
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
    evidence to write back verbatim. Unlike its cardiacCore/cardiacFoam
    counterparts, this typed value is never used to decide what gets
    written -- `_stage_overrides_into_snapshot` already wrote the raw
    override value; this exists only to produce a shape-valid value for
    the `ParameterAssignment` audit record.
    """
    parse = _TEXT_PARSERS.get(value_kind)
    if parse is not None and isinstance(value, str):
        return parse(value), (value,)
    return value, ()


def _inferred_value_kind(value: Any) -> str | None:
    """A `value_kind` for the ``system/<file>:<entry>`` route, which
    `validate_overrides` never catalog-validates, so there is no declared
    kind to look up. Dispatches on the Python type in hand, not on whether
    the text looks numeric: a numeric-looking string is still classified
    as "word", the most conservative true statement with no catalog entry
    to consult. Returns ``None`` when genuinely unclassifiable, so the
    caller refuses rather than guesses.
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
    """driver_path -> `DictEntry` for every controlDict entry the catalog
    declares, including each entry's `value_kind` (`_catalog_entries`
    discards that, keeping only the bare path set)."""
    catalog = driver_context.capabilities.dictionaries.catalog()
    return {entry.driver_path: entry for entry in catalog.entries_for("controlDict")}


def _catalog_entry_for_apply(
    dp: str,
    *,
    scoped_entries: dict[str, Any],
) -> Any | None:
    """The catalog `DictEntry` a ``$TOKEN.``/regeneration-selector
    ``driver_path`` addresses. Re-runs the direct-or-dynamic match
    `validate_overrides` already performed, to get its `value_kind`, rather
    than threading a return value back through that function's control flow.
    """
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
    `ParameterAssignment` per override as a byproduct. `case_root` is never
    read or written by this function; `scope.resolve_entry` and
    `regen_scope.regenerate` are given `snapshot_root` instead, so that
    within one call, a later override's `resolve_entry` (e.g. cardiacFoam's,
    detecting the active `<solver>Coeffs` block) sees a prior override's
    write to the same file rather than resolving against the file's
    pre-call state.
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
                # See RegenerationScope.regenerate: the rebuild needs sibling
                # $TOKEN. overrides in this same call, not just the selector.
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
