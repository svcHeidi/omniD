from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .runtime.models import DataArtifact


@dataclass(frozen=True)
class StrictDiagnostic:
    level: str
    code: str
    message: str
    source: str = ""
    field: str = ""


@dataclass(frozen=True)
class SimulationAuditItem:
    stage: str
    status: str
    points: int
    max_points: int
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


def diagnostic(
    level: str,
    code: str,
    message: str,
    *,
    source: str = "",
    field: str = "",
) -> StrictDiagnostic:
    return StrictDiagnostic(
        level=level,
        code=code,
        message=message,
        source=source,
        field=field,
    )


def has_error(diagnostics: tuple[StrictDiagnostic, ...]) -> bool:
    return any(diagnostic.level == "error" for diagnostic in diagnostics)


def has_warning(diagnostics: tuple[StrictDiagnostic, ...]) -> bool:
    return any(diagnostic.level == "warning" for diagnostic in diagnostics)


def artifact_to_json(artifact: DataArtifact) -> dict[str, Any]:
    payload = asdict(artifact)
    payload["variables"] = list(artifact.variables)
    return payload

