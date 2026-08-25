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
#     sweep_materialize
#
# Description
#     Materializes a resolved sweep case via build_and_launch and Allrun.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from pathlib import Path
from typing import Any


def materialize_case(
    *, case_dir: Path, routed: dict[str, Any], driver_context=None,
) -> None:
    """Materialize via the selected plugin while preserving the public API."""

    from .core.compatibility import resolve_public_driver_context
    from .core.plugin_capabilities import SweepMaterializationRequest

    driver_context = resolve_public_driver_context(driver_context)
    driver_context.capabilities.sweep_materializer.materialize(
        SweepMaterializationRequest(case_dir=case_dir, routed=routed),
    )
