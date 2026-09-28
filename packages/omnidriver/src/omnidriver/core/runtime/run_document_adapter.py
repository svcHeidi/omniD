from __future__ import annotations

from dataclasses import asdict
from typing import Any

from omnidriver.core.planning_types import StrictDiagnostic, artifact_to_json, diagnostic
from omnidriver.core.specs.validation import validate_run
from ..plugin_capabilities import RunDocumentConfigurationRequest
from .configuration_source import resolve_configuration_source
from .models import DataArtifact
from .run_model import RunDocument
from .workflow_state import WorkflowRunState


def _run_document_from_case(
    *,
    entry: str,
    spec,
    launch: dict[str, Any],
    workflow_dag: dict[str, Any] | None,
    workflow_state: WorkflowRunState | None,
    expected_artifacts: tuple[DataArtifact, ...],
    driver_context,
) -> tuple[RunDocument, tuple[StrictDiagnostic, ...]]:
    config, configuration_diagnostics = (
        driver_context.capabilities.run_document_configuration.build(
            RunDocumentConfigurationRequest(spec),
        )
    )
    diagnostics: list[StrictDiagnostic] = list(configuration_diagnostics)

    # A generic case or tutorial record's configuration lives in the case
    # files it already staged (spec.metadata["generic_case"]); a factory
    # tutorial's lives in the document. Stated explicitly here
    # (RunDocument.configurationSource) rather than re-inferred by execution,
    # which never sees the spec.
    configuration_source = (
        "case" if spec.metadata and spec.metadata.get("generic_case") else "document"
    )
    source_decision = resolve_configuration_source(configuration_source, config)
    diagnostics.extend(source_decision.diagnostics)

    if source_decision.validate_document_config:
        import jsonschema

        config_schema = driver_context.capabilities.run_document_configuration.schema()
        try:
            jsonschema.validate(config, config_schema)
        except jsonschema.exceptions.ValidationError as exc:
            diagnostics.append(diagnostic(
                "error",
                "plugin_config_schema_violation",
                f"Plugin-declared config schema rejected the built config: {exc.message}",
                field=".".join(str(part) for part in exc.absolute_path) or "",
            ))

    run_doc = RunDocument(
        id=f"plan-{entry}",
        name=entry,
        status="planned" if not diagnostics else "failed",
        intent={"source": "strict_plan"},
        plugin=driver_context.identity.to_json(),
        config=config,
        configurationSource=configuration_source,
        resolvedEntry={
            "entry": entry,
            "entryKind": spec.metadata.get("entry_kind"),
            "entryPath": spec.metadata.get("entry_path"),
            "resolvedName": spec.metadata.get("entry_name", entry),
            "sourceType": spec.metadata.get("source_type"),
            "workflowFamily": spec.metadata.get("workflow_family"),
            "isRunnable": True,
            # A record case run in parallel says so, with the scheduler
            # allocation checked against; a serial one carries no key.
            **({"parallel": spec.metadata["parallel"]} if "parallel" in spec.metadata else {}),
            # Every input this case resolved; absent when the record declares none.
            **({"inputs": spec.metadata["inputs"]} if "inputs" in spec.metadata else {}),
        },
        workflowDag=workflow_dag,
        workflowState=workflow_state.to_json() if workflow_state else None,
        launch={
            "action": launch.get("action"),
            "command": launch.get("command", []),
            "commandDisplay": launch.get("command_display", ""),
            "workflowStatePath": launch.get("workflow_state_path"),
            "caseRoot": launch.get("case_root"),
            "setupRoot": launch.get("setup_root"),
            "outputDir": launch.get("output_dir"),
        },
        expectedArtifacts=[artifact_to_json(artifact) for artifact in expected_artifacts],
        validation={"status": "not_run", "diagnostics": []},
    )
    # `validate_run` applies only when this document's own `config` is the
    # configuration to check -- the same `resolve_configuration_source`
    # decision above, not a second, independent generic-case check.
    validator_diagnostics = (
        validate_run(run_doc, driver_context=driver_context)
        if source_decision.validate_document_config
        else ()
    )
    diagnostics.extend(validator_diagnostics)
    run_doc.validation = {
        "status": "ok" if not diagnostics else "failed",
        "diagnostics": [asdict(d) for d in diagnostics],
    }
    run_doc.status = "planned" if not any(d.level == "error" for d in diagnostics) else "failed"
    return run_doc, tuple(diagnostics)
