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
#     own_context
#
# Description
#     The DriverContext this adapter means when it means itself.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""The context this adapter means when it means itself.

``default_driver_context()`` answers the question "which adapter should serve
a caller who named none?" by looking at the ``omnidriver.plugins`` entry-point
group. That is the right question at a *public edge*, where the caller really
did decline to choose. It is the wrong question inside cardiacFOAM's own
modules, which are not asking who the user selected -- they are asking which
dictionary vocabulary to validate against, and the answer is statically known
to be this one.

Asking the registry instead made the answer depend on what else happened to be
installed: with `omnidriver-openfoam` alongside `omnidriver-cardiacfoam` there
are two entries and no unique default, so ``build_electro_properties`` raised
``LookupError`` rather than building a dictionary. That is the
supplied-versus-discovered rule in `future/ENVIRONMENT_CONTRACT.md` §12: a
plugin's own identity has no ambient truth to discover, so discovering it
invents an answer -- or, here, refuses to.

Corrected 2026-09-18, when integrating the three adapter branches made a third
plugin installable and the failure impossible to keep ignoring; it had in fact
been failing for any install with more than one adapter, which is every install
CI's test-cardiac job builds.
"""

from __future__ import annotations


def own_driver_context():
    """Build a ``DriverContext`` for cardiacFOAM without consulting the registry.

    Fresh per call, matching ``default_discovered_context``'s contract -- a
    context is cheap and callers are entitled to mutate what they are given.

    The imports are function-local because ``cardiacfoam_plugin`` reaches back
    into ``tutorials.generic_case``, which is one of this helper's callers.
    """
    from omnidriver.core.plugin_interface import driver_context
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    return driver_context(CardiacFoamPlugin(), source="omnidriver.cardiacfoam")


__all__ = ["own_driver_context"]
