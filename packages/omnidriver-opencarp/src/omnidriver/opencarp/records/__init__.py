"""openCARP tutorial-record registrations (Task 11 onward).

Records address a study key and return a patch; they never write a case
directly (scripts/check-case-writes.py scans this package for exactly that)."""
from .niederer_n_version import DX_AXIS, RECORD

TUTORIAL_RECORDS = {RECORD.name: RECORD}
AXIS_CATALOG = {DX_AXIS.name: DX_AXIS}
