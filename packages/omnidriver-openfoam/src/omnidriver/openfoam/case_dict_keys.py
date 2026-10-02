"""Warn about case-dictionary keys the active plugin's catalogue does not
know: the reverse of `dict_keys_scanner` (what C++ accepts vs. what was
actually written). OpenFOAM ignores an unrecognised key silently."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

_WILDCARD = re.compile(r"<[^>]+>")

SKIP_ENV_VAR = "SKIP_CASE_DICT_KEY_DIAGNOSTICS"

# OpenFOAM's runtime-selection convention: a model selected by <key> reads its
# settings from a sibling <modelName>Coeffs sub-dictionary, which belongs to
# OpenFOAM rather than any plugin's catalogue -- so it's exempted here rather
# than warned on every case (a misspelling, e.g. "...Coefs", still is).
_RTS_COEFFS_SUFFIX = "Coeffs"


def _scope_relative(trail: tuple[str, ...]) -> tuple[str, ...]:
    """Drop a leading runtime-selection scope dict, aligning an absolute
    trail with catalogue paths (expressed relative to inside `<model>Coeffs`,
    since parsing strips their `$SCOPE_TOKEN.` prefix)."""
    if trail and trail[0].endswith(_RTS_COEFFS_SUFFIX):
        return trail[1:]
    return trail


def _prefixes(catalogued_paths: Iterable[str]) -> set[tuple[str, ...]]:
    """Every catalogue path and every prefix of one, as segment tuples --
    a container (`ecgDomains`) is legitimate even with no path ending there."""
    out: set[tuple[str, ...]] = set()
    for path in catalogued_paths:
        segments = tuple(path.split("."))
        for i in range(1, len(segments) + 1):
            out.add(segments[:i])
    return out


def _matches(trail: tuple[str, ...], known: set[tuple[str, ...]]) -> bool:
    """Does ``trail`` match a catalogue prefix, ``<placeholder>`` matching any?"""
    for candidate in known:
        if len(candidate) != len(trail):
            continue
        if all(
            _WILDCARD.fullmatch(c) or c == t
            for c, t in zip(candidate, trail)
        ):
            return True
    return False


def case_dict_key_diagnostics(
    case_root: str | Path,
    *,
    catalogued_paths: Iterable[str],
    dict_relpaths: Sequence[str],
    scanned: Callable[[str, tuple[str, ...]], bool] | None = None,
) -> tuple[StrictDiagnostic, ...]:
    """Warn (never error) about keys in `dict_relpaths` absent from the
    catalogue; the catalogue deliberately omits keys OpenFOAM itself owns, so
    an unmatched key needs human judgement rather than a failed plan.

    ``scanned(relpath, trail)`` says whether the solver's own source reads
    that key: the plan then reports it once, as an uncatalogued note, and this
    check stays silent.

    Matching is by position, not bare name: a trail matches a catalogue path
    (or a path prefix) with `<placeholder>` segments matching any name --
    otherwise an author's own instance label (e.g. `ecgDomains { ECG {...} }`)
    is indistinguishable from a misspelling. Honors `SKIP_ENV_VAR`; a parse
    or IO failure reports `case_dict_inspection_unavailable` instead of
    emitting spurious key warnings for that file.
    """
    if os.environ.get(SKIP_ENV_VAR):
        return ()

    known = _prefixes(catalogued_paths)
    root = Path(case_root)
    diagnostics: list[StrictDiagnostic] = []

    for relpath in dict_relpaths:
        path = root / relpath
        try:
            if not path.is_file():
                continue
            from foamlib import FoamFile

            parsed = FoamFile(path)
            unmatched = [
                trail for trail in _unmatched(parsed, known)
                if scanned is None or not scanned(relpath, trail)
            ]
        except Exception as exc:
            diagnostics.append(
                diagnostic(
                    "warning",
                    "case_dict_inspection_unavailable",
                    f"{relpath}: dictionary key inspection unavailable: "
                    f"{type(exc).__name__}: {exc}",
                    source=relpath,
                )
            )
            continue
        for trail in unmatched:
            where = ".".join(trail)
            diagnostics.append(
                diagnostic(
                    "warning",
                    "uncatalogued_case_dict_key",
                    (
                        f"{relpath}: key {where!r} is not in the active "
                        "plugin's dictionary catalogue. OpenFOAM ignores "
                        "unrecognised keys, so if this is a misspelling the "
                        "solver will silently fall back to its default."
                    ),
                    source=relpath,
                    field=trail[-1],
                )
            )
    return tuple(diagnostics)


def _unmatched(
    node: Mapping,
    known: set[tuple[str, ...]],
    trail: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    """Outermost unmatched keys, depth-first; an unmatched container is
    reported once and not descended into, so one misspelled container
    doesn't bury the reported key under every key beneath it."""
    found: list[tuple[str, ...]] = []
    for key in node:
        value = node[key]
        full = trail + (str(key),)
        if not _matches(_scope_relative(full), known) and not str(key).endswith(
            _RTS_COEFFS_SUFFIX
        ):
            found.append(full)
            continue
        if hasattr(value, "keys"):
            found.extend(_unmatched(value, known, full))
    return found
