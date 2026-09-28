"""Solver-neutral report-catalog infrastructure.

Owns the shared machinery -- ``ReportDefinition``, the ``applicable_when``
predicate evaluator, and the JSON record shape. Which reports exist is
solver-specific data owned by the plugin that authors them, reached through
``driver_context.capabilities.report_catalog.reports()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# --- v1 URL templates -------------------------------------------------------

#: ``{port}``/``{kind}`` are substituted by the consumer. No ``{runId}``
#: placeholder yet -- the report frontend does not route by run.
URL_TEMPLATE = "http://localhost:{port}/{kind}"

#: Bundled offline fallback path.
STUB_URL = "/reports/stub.html"


# --- definition record ------------------------------------------------------


@dataclass(frozen=True)
class ReportDefinition:
    """One row of the report catalog; fields are emitted directly by the exporter."""

    id: str
    title: str
    kind: str  # v1: only "iframe"
    url_template: str
    applicable_when: Mapping[str, Any] | None = None
    show_by_default: bool = True
    description: str = ""


# --- predicate evaluator (v1: flat key-equality) ---------------------------


def _shallow_get(cfg: Mapping[str, Any], dotted: str) -> Any | _Missing:
    """Resolve a dotted ``"a.b.c"`` path; ``MISSING`` if any segment is absent
    (an absent path does not match, rather than matching ``None``)."""
    cur: Any = cfg
    for seg in dotted.split("."):
        if not isinstance(cur, Mapping) or seg not in cur:
            return MISSING
        cur = cur[seg]
    return cur


class _Missing:
    """Sentinel for "path absent"; distinct from ``None`` so a field
    explicitly set to ``None`` still counts as present."""

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

    ``None`` always matches; otherwise each ``"dotted.path": scalar`` entry
    is ANDed together. A mapping value is rejected with ``ValueError`` --
    v1 is flat key-equality only, and must fail loudly rather than silently
    mis-filter once richer operators (``$in``, ``$gt``, ...) exist.
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

    Kept here, not in the export script, so tests and other consumers can
    call it directly without spawning a subprocess.
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
