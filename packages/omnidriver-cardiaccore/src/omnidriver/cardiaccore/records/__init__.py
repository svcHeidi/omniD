"""cardiacCore's tutorial records (step S; design doc
docs/superpowers/specs/2026-09-28-supplied-inputs-design.md).

Only ``humanSlab`` exists here (S3): the only variant with a tracked native
case folder today (design §1.4). ``humanEndocardial`` and
``pigMorphometricTransmural`` fit the same mechanism once their own native
case folders are tracked (S4); ``cardiaccore-pig-transmural-purkinje`` has
no native tutorial at all and is not migrated.

Scanned in full by ``scripts/check-case-writes.py``: nothing here may
import or call a writer.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import build_tutorial_record_catalog

from .human_slab import RECORD as _HUMAN_SLAB_RECORD

TUTORIAL_RECORDS = build_tutorial_record_catalog((
    _HUMAN_SLAB_RECORD,
))
