"""cardiacFOAM's tutorial records and their axes (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``).

``TUTORIAL_RECORDS``/``AXIS_CATALOG`` aggregate every record/axis this
package registers -- one dict each, wired to the cardiac stack through
``CardiacFoamPlugin.get_tutorial_records``/``get_axis_catalog``. Adding a
new tutorial record means adding it (and its own axes) to both dicts here,
not touching the plugin itself.

Scanned in full by ``scripts/check-case-writes.py`` (design §5's static
gate): nothing under this package may import or call a writer. Every record
and axis is pure data / a pure function; only ``core.case_transaction
.commit_case_write`` ever writes a case.
"""

from __future__ import annotations

from .restitution_curves import AXES as _RESTITUTION_CURVES_AXES
from .restitution_curves import RECORD as _RESTITUTION_CURVES_RECORD

TUTORIAL_RECORDS = {
    _RESTITUTION_CURVES_RECORD.name: _RESTITUTION_CURVES_RECORD,
}

AXIS_CATALOG = dict(_RESTITUTION_CURVES_AXES)
