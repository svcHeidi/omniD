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
#     test_adapter_never_asks_who_it_is
#
# Description
#     cardiacFOAM's own modules must state their identity, not discover it.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""cardiacFOAM's own modules must state their identity, not discover it.

``default_driver_context()`` consults the plugin registry, which raises ``LookupError`` once a second adapter is installed.
Core's mirror guard (``test_core_context_is_explicit.py``) cannot see this package, so the two are complementary.
"""

from __future__ import annotations

import ast
import pathlib

import omnidriver.cardiacfoam

# From the imported package, not the repo layout: a repo-relative path scans zero files under a wheel.
_SRC_ROOT = pathlib.Path(omnidriver.cardiacfoam.__file__).resolve().parent

# Helpers that resolve an adapter from the ambient registry.
_FORBIDDEN = frozenset({"default_driver_context", "absent_default_driver_context"})

# No exemptions: this package has no public edge; use own_context.own_driver_context() instead.
_EXEMPT: frozenset[str] = frozenset()


def _forbidden_calls(path: pathlib.Path) -> list[tuple[int, str]]:
    """Every call to a registry-resolving helper, as (line, name)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name in _FORBIDDEN:
            found.append((node.lineno, name))
    return found


def test_the_adapter_never_resolves_its_own_identity_from_the_registry() -> None:
    assert _SRC_ROOT.is_dir(), f"cardiacFOAM source root not found at {_SRC_ROOT}"

    scanned = 0
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        if path.name in _EXEMPT:
            continue
        scanned += 1
        for lineno, name in _forbidden_calls(path):
            offenders.append(f"{path.relative_to(_SRC_ROOT)}:{lineno}: {name}()")

    # A guard that scanned nothing would pass silently.
    assert scanned > 20, (
        f"expected to scan cardiacFOAM's modules, but found only {scanned} "
        f"file(s) under {_SRC_ROOT} -- this guard is not looking where it thinks"
    )

    assert offenders == [], (
        "cardiacFOAM source asks the omnidriver.plugins registry which adapter "
        "it is, so these calls raise LookupError whenever a second adapter is "
        "installed:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse omnidriver.cardiacfoam.own_context.own_driver_context(), which "
        "states the identity instead of discovering it, or thread an explicit "
        "DriverContext down from the caller."
    )
