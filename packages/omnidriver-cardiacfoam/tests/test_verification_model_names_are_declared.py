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
#     test_verification_model_names_are_declared
#
# Description
#     A predicate may not gate on a verifier the catalogue does not declare.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""A predicate may not gate on a verifier the catalogue does not declare.

Entries gate their applicability on which verification model a case selected,
via ``applicable_when={"...verificationModel.type": (...)}``. The set of
selectable models is itself declared, as the ``enum_values`` of the matching
``verificationModel.type`` entry. Those two are the same fact, written twice,
and until 2026-09-19 nothing compared them.

They had drifted. Native commit ``5a8be782`` renamed
``bathECGManufacturedVerifier`` to ``manufacturedBathBidomainECGVerifier`` and
moved the dictionary it reads from ``manufacturedBidomain`` to
``verificationModel``. The catalogue's ``enum_values`` were updated; one
``applicable_when`` predicate was not. It gated on a name no case could ever
set, so the entry it guarded was silently unreachable -- inapplicable to every
case, forever, with nothing failing.

This guard needs no native checkout: it is an internal-consistency check
between two declarations in one file, so it runs everywhere, including in CI
where the native tree is absent. That is deliberate. The native-resolution
question -- does each ``source_refs`` path still exist? -- is a different check
needing a supplied source root, and a test that silently skips without one
would be no check at all.
"""

from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

_CTX = _driver_context(CardiacFoamPlugin(), source="test:verification_model_names")

_TYPE_KEY_SUFFIX = "verificationModel.type"


def _declared_types() -> dict[str, frozenset[str]]:
    """Selectable model names, keyed by the driver path that declares them."""
    return {
        entry.driver_path: frozenset(entry.enum_values)
        for entry in _CTX.capabilities.dictionaries.entries()
        if entry.driver_path.endswith(_TYPE_KEY_SUFFIX) and entry.enum_values
    }


def test_every_gated_verifier_name_is_selectable() -> None:
    declared = _declared_types()
    assert declared, "no verificationModel.type entry declares its enum_values"

    offenders: list[str] = []
    for entry in _CTX.capabilities.dictionaries.entries():
        for key, value in (entry.applicable_when or {}).items():
            if not key.endswith(_TYPE_KEY_SUFFIX):
                continue
            names = value if isinstance(value, tuple) else (value,)
            allowed = declared.get(key)
            if allowed is None:
                offenders.append(
                    f"{entry.driver_path}\n      gates on {key!r}, which no entry declares"
                )
                continue
            for name in names:
                if name not in allowed:
                    offenders.append(
                        f"{entry.driver_path}\n      gates on {name!r}, which is not in "
                        f"{key}'s enum_values"
                    )

    assert offenders == [], (
        "these entries gate on a verification model no case can select, so they "
        "are inapplicable to every case and nothing says so:\n  "
        + "\n  ".join(offenders)
        + "\n\nEither the predicate names a renamed or deleted verifier, or the "
        "enum_values of the type key are missing one."
    )
