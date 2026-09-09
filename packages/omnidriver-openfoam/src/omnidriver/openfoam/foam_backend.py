from __future__ import annotations

import difflib
import re
import warnings
from pathlib import Path
from typing import Any

from foamlib import Dimensioned, FoamFile

ScopeArg = str | list[str] | tuple[str, ...] | None

_TRUE_TOKENS = {"yes", "true", "on"}
_FALSE_TOKENS = {"no", "false", "off"}


def _normalize_scope(scope: ScopeArg) -> tuple[str, ...]:
    if scope is None:
        return ()
    if isinstance(scope, str):
        stripped = scope.strip()
        if not stripped:
            raise ValueError("scope cannot be an empty string")
        return (stripped,)
    parts = tuple(str(item).strip() for item in scope)
    if not parts or any(not part for part in parts):
        raise ValueError("scope must contain one or more non-empty names")
    return parts


def coerce_value(value: Any) -> Any:
    """Convert a driverFOAM override value into a type foamlib will store.

    Override values arrive from ``sweep.json`` and the CLI as strings, but
    foamlib is type-strict on write: it refuses a ``str`` that would be read
    back as something else (``"1e-6"``, ``"0.0"``, ``"uniform 0"`` all raise
    ``ValueError``). Anything that is not clearly numeric or boolean is left as
    a string and allowed to fail loudly in foamlib -- that refusal is a feature,
    because it is what rejects an injected ``"1e-6;  rogue  1"``.

    One class was left unhandled by the above: an OpenFOAM dimensioned
    literal (``"[-1 -3 3 0 0 2 0] (0.1 ... )"`` for a dimensioned tensor like
    ``conductivity``, or ``"[0 -1 0 0 0 0 0] 3"`` for a dimensioned scalar
    like ``chi``/``cm``) or a bare vector/list (``"(0.001 0.002 0.006)"``).
    Left as a plain string, foamlib parses the string's *content*, recognises
    it would read back as a ``Dimensioned``/array, and refuses to store a
    ``str`` there -- the same type-strictness described above, just with no
    branch here to satisfy it. Measured directly against 1.7.5.

    Only tokens that start with ``[`` (a dimension set) or ``(`` (a bare
    vector/list) are attempted here, via ``FoamFile.loads``, foamlib's own
    deserializer -- so the exact grammar this project already depends on
    elsewhere is what decides the type, not a hand-rolled parser that could
    disagree with it on an edge case. Deliberately scoped to that leading-
    character check rather than "try loads() on anything left over": a
    bare-word token like ``"uniform 0"`` also parses via ``loads()`` (to
    ``0.0``), which would silently change today's documented "fails loudly"
    behaviour for that shape. Restricting to `[`/`(` leaves every other
    unhandled string exactly as before -- this only ever adds a type for the
    dimensioned-literal/bare-list shapes that previously had none.
    """
    if not isinstance(value, str):
        return value

    token = value.strip()
    lowered = token.lower()
    if lowered in _TRUE_TOKENS:
        return True
    if lowered in _FALSE_TOKENS:
        return False

    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass

    if token.startswith("[") or token.startswith("("):
        try:
            parsed = FoamFile.loads(token)
        except Exception:
            return token
        if not isinstance(parsed, str):
            return parsed

    return token


def _dimensioned_component_count(value: Dimensioned) -> int:
    """Number of raw components a ``Dimensioned``'s value carries.

    1 for a dimensioned scalar (a plain Python number); ``len(...)`` for a
    dimensioned vector/tensor/symmTensor (a numpy array). Used to route the
    latter around foamlib's writer entirely -- see ``update_entry``.
    """
    raw = value.value
    return len(raw) if hasattr(raw, "__len__") else 1


_ENTRY_SEPARATOR_RE = re.compile(r'(?<![\w"])([A-Za-z_]\w*)( )([^\s{};"][^{};]*;)')


def _reformat_separators(line: str) -> str:
    """Widen ``key value;`` to ``key    value;`` (tier 1's four-space form).

    Matches ``identifier<one space>value;`` anywhere in the line, not just at
    the start, so it also fixes an inline entry like ``Vm { tolerance 1e-12; }``
    without touching the ``Vm {`` that precedes it. The negative lookbehind
    excludes a key immediately preceded by a quote, so it does not fire inside
    a quoted string like ``note "a value with { a brace";``.
    """

    def repl(match: re.Match[str]) -> str:
        key, _space, rest = match.groups()
        return f"{key}    {rest}"

    return _ENTRY_SEPARATOR_RE.sub(repl, line)


def normalize_output(before: str, after: str) -> str:
    """Reshape foamlib's write into the byte form the line-based tier emits.

    foamlib writes ``k 250;`` (one space) and, *measured directly against
    1.7.5*, inserts a blank line both before the edited entry and at
    end-of-file. Tier 1 writes ``k    250;`` (four spaces) and inserts
    nothing.

    A whole-file heuristic scan cannot fix this safely: reformatting every
    line matching ``key value;`` also rewrites lines foamlib never touched --
    e.g. an existing ``note  "a value with { a brace";`` two-space entry
    would be corrupted to four spaces even though foamlib left it
    byte-identical. Instead, diff ``before`` against ``after`` and act only
    on the lines the write actually changed: reformat their separator width,
    and drop any *purely inserted* blank line. Unchanged lines pass through
    verbatim, so untouched entries -- however they happen to be spaced --
    are never rewritten.
    """
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)

    out: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.extend(after_lines[j1:j2])
            continue
        for line in after_lines[j1:j2]:
            if line.strip() == "":
                continue
            out.append(_reformat_separators(line))
    return "".join(out)


def _require_file(file_path: Path) -> None:
    if not file_path.exists():
        raise FileNotFoundError(f"Dictionary file not found: {file_path}")


def _reject_directive_shaped(value: Any) -> None:
    """Mirror ``mutators._format_value``'s tier-1 guard on this tier too.

    Without this, tier 2 relies solely on foamlib's own type-strictness to
    reject dangerous values -- which is narrower than tier 1's explicit
    rule. Measured directly: foamlib accepts ``'#includeEtcFuncs'``, a bare
    ``'#'``, and ``'PCG#calc'`` completely unconverted (none of them read
    back as another type, so foamlib's type check has nothing to object
    to), even though tier 1 rejects all three as directive-shaped. Enforcing
    the same explicit rule here, rather than depending on what foamlib
    happens to catch, is what makes the "both tiers reject this" claim in
    SECURITY.md actually true.

    The stringify below is unconditional -- applied to every value type, not
    just ``str`` -- exactly like ``mutators._format_value``. An earlier
    version special-cased non-``str`` inputs and returned immediately for
    them (``if not isinstance(value, str): return``), which let a container
    value bypass the guard entirely: ``update_foam_entry``'s delegation
    passes through whatever type the original caller supplied, and a
    ``dict``/``list`` containing a directive-shaped string never hit the
    ``isinstance`` check, so it reached foamlib completely unscreened.
    Reproduced directly: ``{"codeInclude": '#{ system("id"); #}'}`` was
    accepted and written to disk as a live coded block. Tier 1 has no
    equivalent hole because it stringifies every value before screening,
    regardless of type; this guard now does the same.
    """
    value = str(value)
    if ";" in value or "\n" in value:
        raise ValueError(
            f"override value {value!r} contains a statement separator; "
            "a value may not introduce additional dictionary entries"
        )
    if "#" in value:
        raise ValueError(
            f"override value {value!r} contains an OpenFOAM directive; "
            "directives are not permitted in override values"
        )


def update_entry(
    file_path: Path,
    key: str,
    value: Any,
    *,
    scope: ScopeArg = None,
    add_if_missing: bool = False,
) -> None:
    """Set ``key`` within ``scope``, failing closed when the key is absent.

    ``add_if_missing`` with no ``scope`` is rejected here for the same
    reason tier 1 rejects it in ``mutators.py``'s ``update_foam_entry``:
    without a scope there
    is no well-defined insertion point. Mirroring the guard keeps the two
    tiers agreeing on a case that tier 1's own ``raise ValueError`` already
    intercepts *before* any fallback to this module would ever run --
    leaving this adapter more permissive here would document a capability
    that the real, composed ``update_foam_entry`` never actually exposes.
    """
    _require_file(file_path)
    if add_if_missing and scope is None:
        raise ValueError("add_if_missing requires a scope")
    _reject_directive_shaped(value)
    path = tuple(_normalize_scope(scope)) + (key,)

    coerced = coerce_value(value)
    if isinstance(coerced, Dimensioned) and _dimensioned_component_count(coerced) > 1:
        # foamlib has no fixed-arity vector/tensor writer -- only
        # `Dimensioned`, whose value always goes through foamlib's generic
        # sized-list serialiser once it has more than one component (a
        # 6-component symmTensor becomes "6(...)", but so does a
        # 3-component vector -- confirmed directly, it is not about
        # length). OpenFOAM's actual reader for these fields is the
        # fixed-arity VectorSpace parser, which does not accept a leading
        # count and rejects it outright. Measured directly against a real
        # solve: writing `conductivity` this way and then running
        # cardiacFoam produced
        #   FOAM FATAL IO ERROR: Expected a '(' while reading VectorSpace,
        #   found ... label 6
        # A dimensioned *scalar* (chi, cm, ...) has nothing to size-prefix
        # and is unaffected -- only this multi-component case is rerouted.
        #
        # The original override string is already valid OpenFOAM syntax --
        # that is how it was recognised as dimensioned in coerce_value at
        # all -- so splice it in verbatim instead of asking foamlib to
        # reserialise it. Local import: mutators imports this module at its
        # own top level, so importing mutators from here at module load
        # time would cycle; deferring to call time resolves it, since by
        # then both modules have finished loading.
        if add_if_missing:
            raise NotImplementedError(
                "add_if_missing is not supported for a multi-component "
                "dimensioned override; the entry must already exist"
            )
        from omnidriver.openfoam.mutators import splice_raw_entry_text

        if not splice_raw_entry_text(file_path, key, str(value).strip(), scope=scope):
            raise ValueError(
                f"cannot write multi-component dimensioned value {value!r} to "
                f"{key!r}: not found as a single-line scalar entry in "
                f"{file_path} (scope={scope!r})"
            )
        return

    before = file_path.read_text()
    foam_file = FoamFile(file_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        try:
            if not add_if_missing:
                try:
                    foam_file[path]
                except KeyError as exc:
                    raise KeyError(
                        f"Key '{key}' not found in scope '{scope}' in {file_path}"
                        if scope is not None
                        else f"Key '{key}' not found in {file_path}"
                    ) from exc
            foam_file[path] = coerced
        except KeyError:
            raise
        except (TypeError, ValueError) as exc:
            # Catches foamlib's own ValueError (type-inconsistent value) and
            # FoamFileDecodeError (a ValueError subclass raised by a parse
            # failure on either the pre-check read or the write). Neither
            # foamlib exception type is allowed to escape unmapped -- see
            # the spec's Exception contract.
            file_path.write_text(before)
            raise ValueError(f"cannot write value {value!r} to {key!r}: {exc}") from exc

    file_path.write_text(normalize_output(before, file_path.read_text()))


def remove_dict(
    file_path: Path,
    dict_name: str,
    *,
    scope: ScopeArg = None,
    missing_ok: bool = False,
) -> None:
    """Delete a sub-dictionary block.

    foamlib's ``del`` leaves the emptied block as a whitespace-only line
    between its braces (measured: ``solvers\\n{\\n    Vm {...}\\n}\\n`` becomes
    ``solvers\\n{\\n    \\n}\\n``), not a clean removal. Route through
    ``normalize_output`` so the stray line is dropped along with the same
    blank-line class ``update_entry`` already has to handle.
    """
    _require_file(file_path)
    path = tuple(_normalize_scope(scope)) + (dict_name,)

    before = file_path.read_text()
    foam_file = FoamFile(file_path)
    try:
        del foam_file[path]
    except KeyError:
        if missing_ok:
            return
        raise KeyError(f"Dictionary '{dict_name}' not found in {file_path}") from None
    except (TypeError, ValueError) as exc:
        # Mirrors update_entry's mapping: `del` re-parses the whole file, so
        # a FoamFileDecodeError elsewhere in the file (a ValueError subclass)
        # can surface here even when the target path itself is well-formed.
        file_path.write_text(before)
        raise ValueError(f"cannot remove dictionary {dict_name!r}: {exc}") from exc

    file_path.write_text(normalize_output(before, file_path.read_text()))
