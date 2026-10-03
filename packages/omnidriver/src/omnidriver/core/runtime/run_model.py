"""Python model for the adapter-neutral Run document, whose shape ``schemas/run-document.json`` defines.

For code that constructs, validates or round-trips a Run."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from importlib import resources
from typing import Any, Literal

import jsonschema

# Deliberately no ``Phase`` literal: a plugin's phase names are its own, which
# keeps solver vocabulary out of this package.
Status = Literal["planned", "failed"]

_SCHEMA = json.loads(
    resources.files("omnidriver.schemas")
    .joinpath("run-document.json")
    .read_text()
)


@dataclass
class RunDocument:
    """Run document as defined by ``schemas/run-document.json``.

    Construction does not validate; call :meth:`to_json` to produce a
    schema-validated dict, or :meth:`from_json` to parse with validation.
    """

    id: str
    name: str
    status: Status
    version: str = "3"
    intent: dict[str, Any] = field(default_factory=dict)
    plugin: dict[str, str] | None = None
    resolvedEntry: dict[str, Any] | None = None
    workflowDag: dict[str, Any] | None = None
    workflowState: dict[str, Any] | None = None
    launch: dict[str, Any] | None = None
    expectedArtifacts: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("version") != "3":
            raise ValueError("RunDocument.to_json emits only version '3'")
        if data.get("plugin") is None:
            data.pop("plugin", None)
        jsonschema.validate(data, _SCHEMA)
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "RunDocument":
        jsonschema.validate(data, _SCHEMA)
        return cls(
            id=data["id"],
            name=data["name"],
            status=data["status"],
            version=data.get("version", "3"),
            intent=data.get("intent", {}),
            plugin=data.get("plugin"),
            resolvedEntry=data.get("resolvedEntry"),
            workflowDag=data.get("workflowDag"),
            workflowState=data.get("workflowState"),
            launch=data.get("launch"),
            expectedArtifacts=data.get("expectedArtifacts", []),
            validation=data.get("validation", {}),
        )
