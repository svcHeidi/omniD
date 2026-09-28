"""cardiacFOAM's tutorial records, aggregated into ``TUTORIAL_RECORDS`` and wired
to the cardiac stack through ``CardiacFoamPlugin.get_tutorial_records``.

Scanned by ``scripts/check-case-writes.py``: nothing here may import or call a
writer. Every record and axis is pure data / a pure function; only
``core.case_transaction.commit_case_write`` ever writes a case.
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

#: Built with build_tutorial_record_catalog, not a dict comprehension: two
#: records sharing a name are refused by name, not silently overwritten.
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
