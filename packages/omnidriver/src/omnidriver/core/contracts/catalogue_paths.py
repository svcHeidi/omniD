"""Catalogue-path vocabulary over the plugin's own ``DictEntry`` values.

Core owns ``DictEntry``, so it owns parsing a ``driver_path`` into its
scope-stripped, wildcard-aware form; nothing here reads a file, parses C++,
or knows an OpenFOAM dictionary. This is split from the OpenFOAM C++ scanner
because a plugin's plan diagnostics (``get_plan_diagnostics``) call
``catalogued_paths`` -- keeping it here lets a plugin do that without importing
``omnidriver.openfoam``. ``omnidriver.openfoam.dict_keys_scanner`` re-exports
these for the legal C++ drift direction.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omnidriver.core.contracts.dictionary import DictEntry


@dataclass(frozen=True)
class CataloguePath:
    driver_path: str            # original value from DictEntry
    normalised: str             # driver_path with a leading $SCOPE_TOKEN. stripped
    leaf: str                   # last dot-segment
    parents: tuple[str, ...]    # all segments before the leaf
    has_wildcard: bool          # True if any segment matches <...>

    # Whether the entry is flagged as dynamic_path=True in the catalogue.
    dynamic_path: bool



_WILDCARD_RE = re.compile(r"<[^>]+>")
# Any plugin-declared override scope token, not just the built-in cardiac
# plugin's $ELECTRO_MODEL_COEFFS -- this is a syntactic "$TOKEN." shape,
# never resolved to a file or scope path here, so no plugin lookup is
# needed to recognize and strip it.
_SCOPE_TOKEN_PREFIX_RE = re.compile(r"^\$[A-Z][A-Z0-9_]*\.")



def _parse_path(driver_path: str, is_dynamic: bool) -> CataloguePath:
    normalised = _SCOPE_TOKEN_PREFIX_RE.sub("", driver_path, count=1)

    segments = normalised.split(".")
    leaf = segments[-1]
    parents = tuple(segments[:-1])
    has_wildcard = any(_WILDCARD_RE.search(s) for s in segments)

    return CataloguePath(
        driver_path=driver_path,
        normalised=normalised,
        leaf=leaf,
        parents=parents,
        has_wildcard=has_wildcard,
        dynamic_path=is_dynamic,
    )


def iter_catalogue_paths(
    entries: Iterable["DictEntry"],
) -> Iterable[CataloguePath]:
    """Yield paths from the active plugin's explicit dictionary catalogue."""
    for entry in entries:
        yield _parse_path(entry.driver_path, entry.dynamic_path)


def _as_paths(entries):
    """Accept either DictEntry objects or already-parsed CataloguePath ones."""
    items = list(entries)
    if items and isinstance(items[0], CataloguePath):
        return items
    return list(iter_catalogue_paths(items))


def catalogued_paths(entries: Iterable["DictEntry"]) -> tuple[str, ...]:
    """Scope-stripped catalogue paths, for position-aware matching.

    ``catalogued_names`` flattens the catalogue to a set of bare names, which
    is all the C++ side can use -- a regex match on source gives no position.
    A case file does give position, so ``core/specs/case_dict_keys.py`` uses
    these full paths instead and can tell an author's instance label under a
    ``<placeholder>`` from a real misspelling.
    """
    return tuple(path.normalised for path in _as_paths(entries))

