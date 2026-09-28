"""Generic OpenFOAM tutorial-record axes: every axis here is a PARAMETERISED
BUILDER a tutorial record instantiates with its own document/formula, never
a fixed-name axis registered into a plugin's catalog directly.

Scanned by ``scripts/check-case-writes.py``: every module in this package
may import from ``..case_planning``, ``..literals`` and
``omnidriver.core.tutorial_records`` only -- never a writer.
"""

from .block_mesh_resolution import block_mesh_resolution_axis

__all__ = ["block_mesh_resolution_axis"]
