"""Python model for the adapter-neutral Run document.

Its shape is defined in ``schemas/run-document.json`` (the single source
of truth); this module provides a Python dataclass for code that wants
to construct, validate, or round-trip a Run programmatically.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from importlib import resources
from typing import Any, Literal

import jsonschema

# No ``Phase`` literal here any more. Core used to spell cardiacFoam's four
# editing phases (anatomy/physics/stimulus/solver) as a closed type, which
# put one solver's vocabulary in the solver-neutral package. A plugin
# declares its own phases through ``get_phases()``; ``primary_phase()``
# takes that order as a parameter. See test_phases_are_plugin_declared.py.
Status = Literal["draft", "queued", "planning", "planned", "running", "completed", "failed"]

# Where a RunDocument's plugin configuration lives. See
# schemas/run-document.json's own "configurationSource" description for the
# full contract (step 4c, docs/superpowers/specs/
# 2026-09-24-tutorials-are-pointers-design.md): "document" means `config`
# itself carries the configuration; "case" means the staged/committed case
# files do, and `config` must be empty. There is deliberately no third,
# inferred value -- see `core.runtime.configuration_source`, the one
# function both `run_document_adapter` (planning) and `run_document_exec`
# (execution) call to decide what a given source implies.
ConfigurationSource = Literal["document", "case"]

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
    # Plugin-defined: the core schema constrains ``config`` to an object but
    # imposes no shape on the per-phase values (P2.2). Annotating the values
    # as ``dict`` would assert a guarantee the schema no longer makes;
    # ``specs.validation.validate_run`` enforces the mapping shape and
    # reports violations as diagnostics.
    config: dict[str, Any]
    #: No default (see the module-level note above): every caller that
    #: builds a RunDocument -- planning, a test, a hand-authored document --
    #: must say explicitly where its configuration lives.
    configurationSource: ConfigurationSource
    version: str = "3"
    createdAt: str = ""
    lastModified: str = ""
    intent: dict[str, Any] = field(default_factory=dict)
    plugin: dict[str, str] | None = None
    resolvedEntry: dict[str, Any] | None = None
    workflowDag: dict[str, Any] | None = None
    workflowState: dict[str, Any] | None = None
    launch: dict[str, Any] | None = None
    expectedArtifacts: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Any] | None = None
    reports: dict[str, Any] | None = None
    terminalStatusValues: list[str] = field(
        default_factory=lambda: ["completed", "failed"]
    )

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("version") != "3":
            raise ValueError("RunDocument.to_json emits only version '3'")
        if data.get("reports") is None:
            data.pop("reports", None)
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
            config=data["config"],
            configurationSource=data["configurationSource"],
            version=data.get("version", "3"),
            createdAt=data.get("createdAt", ""),
            lastModified=data.get("lastModified", ""),
            intent=data.get("intent", {}),
            plugin=data.get("plugin"),
            resolvedEntry=data.get("resolvedEntry"),
            workflowDag=data.get("workflowDag"),
            workflowState=data.get("workflowState"),
            launch=data.get("launch"),
            expectedArtifacts=data.get("expectedArtifacts", []),
            validation=data.get("validation", {}),
            results=data.get("results"),
            reports=data.get("reports"),
            terminalStatusValues=data.get(
                "terminalStatusValues", ["completed", "failed"]
            ),
        )
