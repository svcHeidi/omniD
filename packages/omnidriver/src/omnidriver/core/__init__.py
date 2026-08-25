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
#     __init__
#
# Description
#     Exposes reusable components for the module context.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

"""Core shared modules for the omnidriver orchestrator.

Deliberately no eager re-exports here: ``core.introspection`` transitively
imports ``core.strict_planning``, which imports ``omnidriver.openfoam`` for
environment preflight checks. Re-exporting from this ``__init__.py`` would
run that chain the moment anything imports a single ``omnidriver.core.*``
submodule, creating a circular import the instant ``omnidriver.openfoam``
itself needs any ``omnidriver.core`` symbol (as it does, e.g. for
``StrictDiagnostic``). Import submodules directly: ``from
omnidriver.core.introspection import describe_tutorial``, not ``from
omnidriver.core import describe_tutorial``.
"""
