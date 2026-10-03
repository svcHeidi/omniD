"""cardiacCore's tutorial records. ``humanSlab`` needs an uncommitted anatomy bundle via ``--input``; the idealized-heart variants use a native mesh.
Scanned by ``scripts/check-case-writes.py``: nothing here may import or call a writer.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import build_tutorial_record_catalog

from ..conformance_studies import STUDIES

from .human_slab import RECORD as _HUMAN_SLAB_RECORD
from .idealized_heart import (
    IDEALIZED_HEART as _IDEALIZED_HEART_RECORD,
    IDEALIZED_HEART_ENDOCARDIAL as _IDEALIZED_HEART_ENDOCARDIAL_RECORD,
    IDEALIZED_HEART_PIG_TRANSMURAL as _IDEALIZED_HEART_PIG_TRANSMURAL_RECORD,
)

TUTORIAL_RECORDS = build_tutorial_record_catalog((
    _HUMAN_SLAB_RECORD,
    _IDEALIZED_HEART_RECORD,
    _IDEALIZED_HEART_ENDOCARDIAL_RECORD,
    _IDEALIZED_HEART_PIG_TRANSMURAL_RECORD,
), conformance=STUDIES)
