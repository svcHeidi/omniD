"""TorchCorPlugin: TorchCor as one self-contained provider."""
from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.planning_types import diagnostic
from omnidriver.core.plugin_profile import load_plugin_profile

from .activation_reader import ACTIVATION_FORMAT, NearestNodeReader
from .case_json import CaseJsonError, patch, read_value, values_agree
from .catalog import CASE_DOCUMENT, repository_catalog, runner_of
from .environment import SOLVER_COMMANDS, torchcor_environment_diagnostics
from .records import TUTORIAL_RECORDS
from .validation import case_diagnostics, validate_key

CASE_FORMAT = "torchcor_case_json"


class TorchCorPlugin:
    plugin_name = "TorchCor"
    plugin_id = "org.omnidriver.torchcor"
    plugin_version = "0.1.0"
    plugin_api_version = "3"

    def get_profile(self):
        with resources.as_file(resources.files(__package__).joinpath("torchcor.yaml")) as path:
            return load_plugin_profile(path)

    # -- records
    def get_tutorial_records(self):
        return dict(TUTORIAL_RECORDS)

    def get_record_key_validator(self, *, driver_context):
        return lambda document, key_path, value: validate_key(repository_catalog(driver_context), document, key_path, value)

    def get_case_value_comparator(self):
        return values_agree

    def get_config_value_reader(self):
        def _read(document_path: Path, key_path: tuple):
            path = Path(document_path)
            return read_value(path.read_text(), ".".join(key_path)) if path.is_file() else None

        return _read

    def get_record_key_catalog(self, case_root, *, driver_context):
        catalog = repository_catalog(driver_context)
        if catalog is None:
            return ({"document": CASE_DOCUMENT, "key": "<any>", "validated": False},)
        source_refs = [f"{catalog.runner} --describe"]
        entries = [
            {"document": CASE_DOCUMENT, "key": key, "value_kind": spec["kind"], "unit": spec["unit"],
             "description": spec["description"], "default": spec["default"], "minimum": spec["minimum"],
             "exclusive_minimum": spec["exclusive_minimum"], "maximum": spec["maximum"], "menu": spec["menu"],
             "source_refs": source_refs}
            for key, spec in catalog.keys.items()
        ]
        # The fields of ionic_options and ionic_init depend on the model, so only the case's own model's are listed.
        path = Path(case_root) / CASE_DOCUMENT
        model = catalog.ionic_models.get(read_value(path.read_text(), "ionic_model")) if path.is_file() else None
        if model is not None:
            entries += [
                {"document": CASE_DOCUMENT, "key": f"{field}.{name}", "value_kind": spec["kind"], "default": spec["default"],
                 **({"menu": spec["menu"]} if spec.get("menu") is not None else {}), "source_refs": source_refs}
                for field, listed in (("ionic_options", "options"), ("ionic_init", "init"))
                for name, spec in model[listed].items()
            ]
        return tuple(entries)

    # -- rules
    def validate_run_semantics(self, case_root, *, driver_context):
        located = runner_of(driver_context)
        return () if located is None else case_diagnostics(case_root, *located)

    def get_plan_diagnostics(self, case_root, *, workflow_dag, env, scratch_root, driver_context):
        del case_root, workflow_dag, env, scratch_root
        if driver_context.repository is not None:
            return ()
        return (diagnostic(
            "info", "torchcor_runner_not_supplied",
            "case.json keys are written unvalidated: select the stack with --repo naming the solver repository, "
            "whose runner describes the keys it takes", source=CASE_DOCUMENT,
        ),)

    # -- commands and environment
    def get_solver_commands(self):
        return SOLVER_COMMANDS

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None):
        del environment_source, driver_context
        return torchcor_environment_diagnostics(workflow_dag, env if env is not None else os.environ)

    def get_agent_guidance(self):
        text = resources.files(__package__).joinpath("guidance.md").read_text()
        return ({"title": "TorchCor: what the runner and the library do that a reader would not guess", "text": text},)

    # -- case writer
    def get_supported_mutation_modes(self):
        return frozenset({"clone_and_patch"})

    def get_rendered_formats(self):
        return frozenset({CASE_FORMAT})

    def resolve_case_mutation(self, request, *, driver_context):
        targets = tuple(
            {"qualified_id": p.qualified_id, "document": p.document, "key": ".".join(p.expanded_key_path()),
             "value": p.value, "value_kind": p.value_kind, "operation": p.operation, "format": CASE_FORMAT}
            for p in request.parameters
        )
        return ResolvedMutation(
            request=request, targets=targets,
            expected_effects=tuple(f"set {t['key']} in {t['document']}" for t in targets),
            semantic_owner_id=self.plugin_id,
        )

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        by_document: dict[str, dict] = {}
        for target in resolved.targets:
            by_document.setdefault(target["document"], {})[target["key"]] = target
        rendered = []
        for document, targets in by_document.items():
            path = Path(snapshot_root) / document      # seeded from the case by core
            exists_before = path.is_file()
            before = path.read_bytes() if exists_before else b""
            text = before.decode()
            for key, target in targets.items():
                # A key no runner judged ("set", not "ensure") only replaces one the case holds, so a typo adds nothing.
                if target["operation"] == "set" and read_value(text, key) is None:
                    raise CaseJsonError(
                        f"{document}:{key} is not in the case, and with no runner to judge keys (--plugin torchcor alone) "
                        "a key only replaces one the case holds; select the stack with --repo to add it"
                    )
            rendered.append(RenderedFile(
                path=document, content=patch(text, {k: t["value"] for k, t in targets.items()}).encode(),
                mode=None, exists_before=exists_before,
                before_digest=_digest_bytes(before) if exists_before else None,
                renderer_id=self.plugin_id, format=CASE_FORMAT,
            ))
        return tuple(rendered)

    # -- results as quantities
    def get_artifact_value_reader(self, artifact_format: str):
        return NearestNodeReader() if artifact_format == ACTIVATION_FORMAT else None
