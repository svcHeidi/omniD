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

``default_driver_context()`` answers "which adapter did a caller who named none
mean?" by consulting the ``omnidriver.plugins`` entry-point group. That is the
right question at a public edge. Inside this package it is the wrong question
twice over: these modules are not serving an ambiguous caller, and the answer
they need -- which dictionary vocabulary to validate against -- is statically
this package.

The distinction matters because the ambient answer depends on what else is
installed. With one adapter installed the call succeeds and nothing looks
wrong; with two there is no unique default and it raises ``LookupError``. So
the defect is invisible in exactly the environment a developer is most likely
to have, and fatal in the environment CI builds. On 2026-09-18 that was the
state of things: ``build_electro_properties`` could not build a dictionary at
all whenever ``omnidriver-openfoam`` was installed beside this package, which
is every install CI's test-cardiac job makes. 235 of that job's tests failed on
this one cause, and had been failing long enough that the job's redness had
stopped being informative.

Core has the mirror-image guard in ``test_core_context_is_explicit.py``, which
scans ``core/`` and ``openfoam/`` for ``resolve_public_driver_context``. It
cannot see this package -- an adapter's source is outside its scope -- so the
two guards are complementary, not redundant.

This guard scans only cardiacFOAM. ``omnidriver-cardiaccore`` needs the same
one; when a second adapter needs identical test machinery, that is the signal
to lift it into shared test support rather than copy it a third time.
"""

from __future__ import annotations

import ast
import pathlib

import omnidriver.cardiacfoam

# Resolved from the imported package, not from the repository layout: this
# package is always importable in its own test environment, whereas a
# repo-relative path silently yields a directory that does not exist when the
# tests run against an installed wheel -- which would make this guard pass by
# scanning zero files. That false-reassurance failure mode has bitten this
# repository before, so the file count is asserted below rather than assumed.
_SRC_ROOT = pathlib.Path(omnidriver.cardiacfoam.__file__).resolve().parent

# The name that resolves an adapter from the ambient registry, and the core
# helper that does the same thing when handed None.
_FORBIDDEN = frozenset({"default_driver_context", "legacy_default_driver_context"})

# No exemptions. This package has no public edge of its own: callers who want a
# different adapter select it before reaching here, and callers who reach here
# already mean cardiacFOAM. If you think you need an entry in this set, you
# almost certainly want own_context.own_driver_context() instead.
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

    # A guard that scanned nothing would pass silently, which is the failure
    # mode this repository has hit more than once.
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
