"""cardiacFOAM's tutorial records (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``).

``TUTORIAL_RECORDS`` aggregates every record this package registers, wired
to the cardiac stack through ``CardiacFoamPlugin.get_tutorial_records``.
Each record carries its own axes (``TutorialRecord.axes``), so adding a new
tutorial record means adding it here, not touching the plugin itself.
Corrected 2026-09-26 (record-scoped axes): this module also built one
``AXIS_CATALOG`` from every record's axes with ``dict.update``, so two
records defining ``dimension`` differently shared whichever came last.

Scanned in full by ``scripts/check-case-writes.py`` (design §5's static
gate): nothing under this package may import or call a writer. Every record
and axis is pure data / a pure function; only ``core.case_transaction
.commit_case_write`` ever writes a case.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import build_tutorial_record_catalog

from .niederer_2011 import RECORD as _NIEDERER_2011_RECORD
from .manufactured_eikonal_ecg import RECORD as _MANUFACTURED_EIKONAL_ECG_RECORD
from .restitution_curves import RECORD as _RESTITUTION_CURVES_RECORD
from .manufactured_bidomain import RECORD as _MANUFACTURED_BIDOMAIN_RECORD
from .manufactured_bath_bidomain import RECORD as _MANUFACTURED_BATH_BIDOMAIN_RECORD
from .single_cell import RECORD as _SINGLE_CELL_RECORD
from .manufactured_monodomain_pseudo_ecg import RECORD as _MANUFACTURED_MONODOMAIN_PSEUDO_ECG_RECORD
from .cable_1d_restitution import RECORD as _CABLE_1D_RESTITUTION_RECORD
from .cable_1d_cv_convergence import RECORD as _CABLE_1D_CV_CONVERGENCE_RECORD
from .manufactured_monodomain_1d3d import RECORD as _MANUFACTURED_MONODOMAIN_1D3D_RECORD

#: Built with build_tutorial_record_catalog, not a dict comprehension, so
#: two records sharing a name are refused by name instead of one silently
#: overwriting the other (the same hazard 7d79ec9 closed for two axes
#: sharing a name inside one record).
TUTORIAL_RECORDS = build_tutorial_record_catalog((
    _RESTITUTION_CURVES_RECORD,
    _MANUFACTURED_BIDOMAIN_RECORD,
    _NIEDERER_2011_RECORD,
    _MANUFACTURED_EIKONAL_ECG_RECORD,
    _MANUFACTURED_BATH_BIDOMAIN_RECORD,
    _SINGLE_CELL_RECORD,
    _MANUFACTURED_MONODOMAIN_PSEUDO_ECG_RECORD,
    _CABLE_1D_RESTITUTION_RECORD,
    _CABLE_1D_CV_CONVERGENCE_RECORD,
    _MANUFACTURED_MONODOMAIN_1D3D_RECORD,
))
