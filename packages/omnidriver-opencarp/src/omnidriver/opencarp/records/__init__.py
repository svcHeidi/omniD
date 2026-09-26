"""openCARP tutorial-record registrations (Task 11 onward).

Records address a study key and return a patch; they never write a case
directly (scripts/check-case-writes.py scans this package for exactly that)."""
from omnidriver.core.tutorial_records import build_tutorial_record_catalog

from .niederer_n_version import RECORD

#: Built with build_tutorial_record_catalog (shared with
#: cardiacfoam.records), so a second record sharing RECORD.name is refused
#: by name rather than silently overwriting this one.
TUTORIAL_RECORDS = build_tutorial_record_catalog((RECORD,))
