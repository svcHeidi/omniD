"""OpenFOAM writers still on the direct-write path (review finding M2, the
``utils.py``/``case_planning.py`` split).

Everything PURE that used to live here -- ``plan_delta_t``, ``plan_end_time``,
``plan_write_interval``, ``plan_block_mesh_resolution``, ``plan_dict_block``,
``plan_verbatim_content``, and the text-level ``_rewrite_hex_block_lines``
helper they share -- moved to :mod:`omnidriver.openfoam.case_planning`, which
contains no writer at all. This module is the writer half: it stays banned
for a tutorial-record axis module to import from
(``scripts/check-case-writes.py``), exactly like ``mutators``/
``foam_backend`` already are, since it is now unambiguously writer-only.
"""

from pathlib import Path

from .mutators import update_foam_entry


def set_delta_t(control_dict_path: Path, delta_t_seconds: float) -> None:
    """Not yet retired (Phase 3 Task 6's completion, 2026-09-23): still has
    one caller, `niederer_2012.py`'s `mesh_family == "tet"` branch -- a
    source-artifact/mesh path that never migrates onto the channel (Task 7's
    classification, same as every other tet branch in this package). Its
    sibling `set_end_time` and `replace_block_mesh_resolutions` retired in
    this same commit, both having lost their last caller when the eleven
    tutorials completed their migration; this one stays until that one
    caller either migrates or is itself retired."""
    update_foam_entry(control_dict_path, "deltaT", delta_t_seconds)
