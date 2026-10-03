"""Catalogue-path vocabulary over the plugin's own ``DictEntry`` values; reads no file and knows no OpenFOAM dictionary.

Kept apart from the OpenFOAM C++ scanner so a plugin's ``get_plan_diagnostics`` can call ``catalogued_paths`` without importing ``omnidriver.openfoam``."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omnidriver.core.contracts.dictionary import DictEntry

# Any plugin-declared override scope token, not just the built-in cardiac
# plugin's $ELECTRO_MODEL_COEFFS -- this is a syntactic "$TOKEN." shape,
# never resolved to a file or scope path here, so no plugin lookup is
# needed to recognize and strip it.
_SCOPE_TOKEN_PREFIX_RE = re.compile(r"^\$[A-Z][A-Z0-9_]*\.")

#: A ``<name>`` segment of a driver path: any instance of a block.
PLACEHOLDER = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>")


def slot_key(driver_path: str) -> str:
    """A driver path without its leading ``$SCOPE_TOKEN.``: the key a resolved
    dictionary's leaf has below that scope. A multi-segment path stays whole,
    so nested leaves never collide with a top-level key of the same name."""
    return _SCOPE_TOKEN_PREFIX_RE.sub("", driver_path, count=1)


def catalogued_paths(entries: Iterable["DictEntry"]) -> tuple[str, ...]:
    """Scope-stripped catalogue paths, for position-aware matching: a case
    file gives position, so a trail is compared with these full paths and an
    author's instance label under a ``<placeholder>`` is told from a real
    misspelling."""
    return tuple(slot_key(entry.driver_path) for entry in entries)
