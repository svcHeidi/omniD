"""Solver-neutral report definitions, filtering, and serialization.

Plugins own concrete report catalogs. ``applicable_when`` supports flat
key-equality predicates over resolved run configuration. Report URLs are
templates whose ``port`` and ``kind`` fields are filled by consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# --- URL templates ----------------------------------------------------------

#: ``port`` is supplied by the consumer; ``kind`` comes from the report id.
URL_TEMPLATE = "http://localhost:{port}/{kind}"

#: Bundled offline fallback path.
STUB_URL = "/reports/stub.html"


# --- definition record ------------------------------------------------------


@dataclass(frozen=True)
class ReportDefinition:
    """One row of the report catalog.

    Fields are emitted directly by the report catalog exporter. Naming stays
    Pythonic (``snake_case``).
    """

    id: str
    title: str
    kind: str  # v1: only "iframe"
    url_template: str
    applicable_when: Mapping[str, Any] | None = None
    show_by_default: bool = True
    description: str = ""


# --- predicate evaluator (v1: flat key-equality) ---------------------------


def _shallow_get(cfg: Mapping[str, Any], dotted: str) -> Any | _Missing:
    """Resolve a dotted ``"a.b.c"`` path against a nested mapping.

    Returns ``MISSING`` if any segment is absent — a missing path is
    treated as "does not match", not as "matches None".
    """
    cur: Any = cfg
    for seg in dotted.split("."):
        if not isinstance(cur, Mapping) or seg not in cur:
            return MISSING
        cur = cur[seg]
    return cur


class _Missing:
    """Sentinel for "this path is absent from the config".

    Distinct from ``None`` because a config field explicitly set to
    ``None`` should still be considered present (and equal to ``None``
    for matching purposes).
    """

    _instance: "_Missing | None" = None

    def __new__(cls) -> "_Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover — debug aid only
        return "<MISSING>"


MISSING = _Missing()


def matches(
    predicate: Mapping[str, Any] | None,
    config: Mapping[str, Any],
) -> bool:
    """Evaluate the v1 ``applicable_when`` predicate against a config.

    Rules:
    - ``predicate is None`` ⇒ always matches.
    - Each entry must be ``"dotted.path": scalar``. AND across entries.
    - A value that is itself a mapping is treated as an *operator
      object* and rejected with ``ValueError`` — v2 will introduce
      operators (``$in``, ``$gt``, …) but v1 must fail loudly so a
      forward-compat doc never silently mis-filters.
    """
    if predicate is None:
        return True
    for path, expected in predicate.items():
        if isinstance(expected, Mapping):
            raise ValueError(
                f"unsupported predicate operator at {path!r}: "
                f"v1 applicable_when is flat key-equality only "
                f"(operators like $in / $gt land in v2)"
            )
        actual = _shallow_get(config, path)
        if actual is MISSING or actual != expected:
            return False
    return True


# --- helper used by the exporter and tests ---------------------------------


def to_record(r: ReportDefinition) -> dict:
    """Serialize one definition to the JSON record shape.

    Kept here (not in the export script) so tests can call it without
    spawning a subprocess and so any future programmatic consumer
    (a CI lint, a docs renderer) gets the same shape.
    """
    return {
        "id": r.id,
        "title": r.title,
        "kind": r.kind,
        "url_template": r.url_template,
        # ``None`` is a meaningful marker on the wire — keep it.
        "applicable_when": (
            None if r.applicable_when is None else dict(r.applicable_when)
        ),
        "show_by_default": r.show_by_default,
        "description": r.description,
    }
