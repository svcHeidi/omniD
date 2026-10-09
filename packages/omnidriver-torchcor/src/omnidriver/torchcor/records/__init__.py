"""TorchCor tutorial-record registrations; records are pure data (scripts/check-case-writes.py)."""
from omnidriver.core.tutorial_records import build_tutorial_record_catalog

from ..conformance_studies import STUDIES
from .nversion import RECORD

TUTORIAL_RECORDS = build_tutorial_record_catalog((RECORD,), conformance=STUDIES)
