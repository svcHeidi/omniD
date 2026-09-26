"""OpenFOAM writers still on the direct-write path (review finding M2, the
``utils.py``/``case_planning.py`` split).

Everything PURE that used to live here -- ``plan_delta_t``, ``plan_end_time``,
``plan_write_interval``, ``plan_block_mesh_resolution``, ``plan_dict_block``,
``plan_verbatim_content``, and the text-level ``_rewrite_hex_block_lines``
helper they share -- moved to :mod:`omnidriver.openfoam.case_planning`, which
contains no writer at all.

**Corrected 2026-09-26 (5.4b-N).** ``set_delta_t`` is retired: its own
docstring already said it would be, "until that one caller either migrates
or is itself retired" -- that caller was ``niederer_2011.py``'s
``mesh_family == "tet"`` branch, deleted in the same commit as this one
(migrated onto a tutorial record,
``packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/records/
niederer_2011.py``). ``grep -rn "set_delta_t(" packages/*/src`` (excluding
this module's own former definition) now returns zero. This module is kept,
empty of writers, as the writer half's known location (``scripts/
check-case-writes.py``'s scanned-roots comment on ``case_planning.py``
names it by contrast) rather than deleted outright, since a future direct
writer may still need to land here rather than in the pure planner module.
"""
