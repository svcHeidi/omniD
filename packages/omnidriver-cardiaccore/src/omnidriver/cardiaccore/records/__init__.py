"""cardiacCore's tutorial records (step S; design doc
docs/superpowers/specs/2026-09-28-supplied-inputs-design.md).

``humanSlab`` (S3) is the one record with a supplied input: its bundle
(mesh, fiber, sheet, uvc_*) lives only in the owner's local checkout, never
committed, so it proves ``--input`` end to end against real anatomy. Kept
even though ``idealizedHeart`` below covers the same workflow shape (slab):
it is the only non-toy exercise of the supplied-input mechanism S1-S3
built, and its data is real patient anatomy, not an idealized mesh -- a
different, still-useful axis of coverage (S4's coordinator follow-up,
"keep it only if it adds something the idealized one doesn't").

``idealizedHeart``, ``idealizedHeartEndocardial`` and
``idealizedHeartPigTransmural`` (S4) are the three variants reconfigured on
cardiacFOAM's own idealized biventricular mesh, tracked natively
(``cases/idealized*``, Git LFS) -- no supplied input needed at all.

``cardiaccore-pig-transmural-purkinje`` has no native tutorial at all and is
not migrated.

Scanned in full by ``scripts/check-case-writes.py``: nothing here may
import or call a writer.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import build_tutorial_record_catalog

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
))
