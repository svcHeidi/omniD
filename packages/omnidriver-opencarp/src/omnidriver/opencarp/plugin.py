"""OpenCARPPlugin: openCARP as one self-contained provider (spec §7)."""
from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.plugin_profile import load_plugin_profile

from .catalog import load_catalog, template_name
from .environment import AUXILIARY_COMMANDS, REDACTION_PATTERNS, SOLVER_COMMANDS, opencarp_environment_diagnostics
from .lat_reader import LAT_FORMAT, LatPerNodeReader
from .par_format import ParFormatError, format_value, patch_par, read_raw, unquote, values_agree
from .records import AXIS_CATALOG, TUTORIAL_RECORDS
from .validation import check_indices, read_documents, record_key_validator

_FORMAT = "opencarp_par"


def _is_quoted(raw: str) -> bool:
    return len(raw) >= 2 and raw[0] == raw[-1] == '"'


class OpenCARPPlugin:
    plugin_name = "openCARP"
    plugin_id = "org.omnidriver.opencarp"
    plugin_version = "0.1.0"
    plugin_api_version = "2"

    # -- required contract (the dictionary-shaped members are optional since 2026-09-26, spec A3, so none are stubbed)
    def get_profile(self):
        with resources.as_file(resources.files(__package__).joinpath("opencarp.yaml")) as path:
            return load_plugin_profile(path)

    def get_capabilities(self):
        return {}

    def get_tutorial_catalog(self):
        return {"registered_tutorials": (), "spec_factories": {}}

    def validate_configuration(self, spec):
        return ()

    def validate_run_semantics(self, context):
        return ()

    def predict_data_artifacts(self, case_root, spec):
        return ()          # records declare their artifacts through step `produces` (K4)

    # No is_case_runnable_without_workflow (removed 2026-09-25, wave-2 review
    # I4): it answered, from one record's file (nversion.par), a question core
    # asked only to gate record runs; core no longer asks it of a record run
    # carrying its steps (run_document_exec._is_record_run_with_steps).

    # -- records
    def get_tutorial_records(self):
        return dict(TUTORIAL_RECORDS)

    def get_axis_catalog(self):
        return dict(AXIS_CATALOG)

    def get_record_key_validator(self):
        return record_key_validator

    def get_case_value_comparator(self):
        return values_agree

    def get_config_value_reader(self):
        def _read(document_path: Path, key_path: tuple):
            if not Path(document_path).is_file():
                return None
            key = ".".join(key_path)
            raw = read_raw(Path(document_path).read_text(), key)
            if raw is None:
                return None
            spec = load_catalog().parameters.get(template_name(key))
            if spec is not None and spec.value_kind == "boolean" and unquote(raw) not in ("0", "1"):
                raise ParFormatError(
                    f"{document_path}: {key} = {raw!r}; openCARP reads every Flag spelling except 0/false "
                    "as on (F1). The native file must say 0 or 1."
                )
            if spec is not None and spec.value_kind == "string" and not _is_quoted(raw) and "=" in raw:
                # F10: unquoted, openCARP silently drops everything from an
                # '=' on, so the raw text this reader parsed (everything up
                # to the trailing whitespace/comment) is not what openCARP
                # actually reads. Refuse rather than report a value openCARP
                # would truncate.
                raise ParFormatError(
                    f"{document_path}: {key} = {raw!r} is unquoted and contains '='; openCARP "
                    "silently truncates everything from the '=' on (F10). The native file must "
                    "quote this value."
                )
            return unquote(raw)

        return _read

    # -- case writer
    def get_supported_mutation_modes(self):
        return frozenset({"clone_and_patch"})

    def get_rendered_formats(self):
        return frozenset({_FORMAT})

    def resolve_case_mutation(self, request, *, driver_context):
        targets = tuple(
            {"qualified_id": p.qualified_id, "document": p.document,
             "key": ".".join(p.expanded_key_path()), "value": p.value,
             "value_kind": p.value_kind, "format": _FORMAT}
            for p in request.parameters
        )
        return ResolvedMutation(
            request=request, targets=targets, preconditions=(),
            expected_effects=tuple(f"set {t['key']} in {t['document']}" for t in targets),
            semantic_owner_id=self.plugin_id,
        )

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        by_document: dict[str, dict[str, str]] = {}
        for target in resolved.targets:
            by_document.setdefault(target["document"], {})[target["key"]] = format_value(target["value"], target["value_kind"])
        rendered = []
        for document, values in by_document.items():
            path = Path(snapshot_root) / document      # seeded from the case by core (P2)
            exists_before = path.is_file()
            before = path.read_bytes() if exists_before else b""
            text = patch_par(before.decode(), values)
            check_indices(text)                        # F2, refused by name before any run
            rendered.append(RenderedFile(
                path=document, content=text.encode(), mode=None, exists_before=exists_before,
                before_digest=_digest_bytes(before) if exists_before else None,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)

    # -- commands and environment
    def get_solver_commands(self):
        return SOLVER_COMMANDS

    def get_auxiliary_commands(self):
        return AUXILIARY_COMMANDS

    def get_environment_commands(self):
        return frozenset()

    def is_installed_environment_command(self, command):
        return False

    def get_utility_manifests(self):
        return {}

    def get_utility_roots(self):
        return ()

    def get_environment_diagnostics(self, workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None):
        del explicit_bashrc, driver_context
        return opencarp_environment_diagnostics(workflow_dag, env if env is not None else os.environ)

    def get_loaded_environment(self, *, explicit_bashrc=None, driver_context=None):
        del explicit_bashrc, driver_context
        return dict(os.environ)

    def get_configured_environment(self, env, driver_context):
        del driver_context
        return dict(env)

    def get_log_redaction_patterns(self):
        return REDACTION_PATTERNS     # consumed by core's redact_step_logs (K9); corrected 2026-09-25, was "once Task 12 lands"

    # -- record surface (C10, Task 10a)
    def get_record_key_catalog(self, case_root):
        # Review I1 (2026-09-25): was every ``*.par`` in the case against the
        # binary's whole parameter list. Now only a document some record step
        # passes with ``+F`` (the only ones openCARP reads), minus the keys a
        # record's command line assigns after it (F14: silently overridden) --
        # the same facts record_key_validator refuses by, from the same
        # records. A template one of whose instances the command line owns
        # (``imp_region[Int].im_sv_init``) is omitted whole: the catalogue has
        # no "every index but 0" form, and listing a key the validator refuses
        # is the defect I1 names.
        entries = []
        documents = read_documents(TUTORIAL_RECORDS)
        for document in sorted(d for d in documents if (Path(case_root) / d).is_file()):
            owned_templates = {template_name(key) for key in documents[document]}
            for spec in load_catalog().parameters.values():
                if spec.value_kind is None or spec.name in owned_templates:
                    continue
                entries.append({
                    "document": document, "key": spec.name, "value_kind": spec.value_kind,
                    "default": spec.default, "description": spec.description,
                    "minimum": spec.minimum, "maximum": spec.maximum, "menu": list(spec.menu),
                })
        return tuple(entries)

    def get_agent_guidance(self):
        text = resources.files(__package__).joinpath("guidance.md").read_text()
        return ({"title": "openCARP: what the binary does that a reader would not guess", "text": text},)

    # -- results as quantities (results-as-quantities, Task 5)
    def get_artifact_value_reader(self, artifact_format: str):
        """The LAT reader for the record's per-node LAT file; no other format is read."""
        return LatPerNodeReader() if artifact_format == LAT_FORMAT else None
