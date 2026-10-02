"""Catalogue-path vocabulary over the plugin's own ``DictEntry`` values.

Core owns ``DictEntry``, so it owns the scope-stripped form of a
``driver_path``; nothing here reads a file, parses C++, or knows an OpenFOAM
dictionary. This is split from the OpenFOAM C++ scanner because a plugin's plan
diagnostics (``get_plan_diagnostics``) call ``catalogued_paths`` -- keeping it
here lets a plugin do that without importing ``omnidriver.openfoam``.
"""

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
