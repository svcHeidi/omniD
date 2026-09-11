"""Display metadata for exported adapter tutorial catalogs.

Tutorial factories and their domain meanings belong to an adapter. This
module is the thin display layer around the selected adapter's registry: it
adds titles, summaries, thumbnails, tags, and presets for human-facing
catalogs without adding solver behavior or new tutorials.

The exporter cross-checks display entries against the active adapter registry
so a developer cannot ship a card without a backend factory or omit a
registered tutorial from the home page.

If we later move tutorials into a JSON-authored format, only this module and
the exporter are replaced.

The ``preset`` field shape mirrors the v1 ``applicable_when`` predicate
language used by ``report_catalog`` (flat ``"phase.field": value``
keys, no operator objects).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TutorialDisplay:
    """One row of the home-page tutorial strip."""

    id: str  # MUST match an entry in REGISTERED_TUTORIALS
    title: str
    summary: str
    thumbnail: str
    tags: tuple[str, ...] = ()
    preset: dict[str, Any] = field(default_factory=dict)





def to_record(t: TutorialDisplay) -> dict:
    """Serialize one display entry to the JSON record shape."""
    return {
        "id": t.id,
        "title": t.title,
        "summary": t.summary,
        "thumbnail": t.thumbnail,
        "tags": list(t.tags),
        "preset": dict(t.preset),
    }
