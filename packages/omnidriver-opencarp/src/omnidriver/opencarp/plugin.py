"""OpenCARPPlugin: openCARP as one self-contained provider."""
from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.plugin_profile import load_plugin_profile

from .case_rules import case_diagnostics
from .catalog import load_catalog, template_name
from .environment import AUXILIARY_COMMANDS, REDACTION_PATTERNS, SOLVER_COMMANDS, opencarp_environment_diagnostics
from .lat_reader import LAT_FORMAT, LatPerNodeReader
from .parallel import parallel_steps
from .par_format import ParFormatError, format_value, patch_par, read_raw, unquote, values_agree
from .records import TUTORIAL_RECORDS
from .validation import check_indices, read_documents, record_key_validator

_FORMAT = "opencarp_par"


def _is_quoted(raw: str) -> bool:
    return len(raw) >= 2 and raw[0] == raw[-1] == '"'


class OpenCARPPlugin:
    plugin_name = "openCARP"
    plugin_id = "org.omnidriver.opencarp"
    plugin_version = "0.1.0"
    plugin_api_version = "3"

    def get_profile(self):
        with resources.as_file(resources.files(__package__).joinpath("opencarp.yaml")) as path:
            return load_plugin_profile(path)

    # -- records
    def get_tutorial_records(self):
        return dict(TUTORIAL_RECORDS)

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
                # Unquoted, openCARP silently drops everything from an '='
                # on, so the raw text this reader parsed (everything up to
                # the trailing whitespace/comment) is not what openCARP
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
            request=request, targets=targets,
            expected_effects=tuple(f"set {t['key']} in {t['document']}" for t in targets),
            semantic_owner_id=self.plugin_id,
        )

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        by_document: dict[str, dict[str, str]] = {}
        for target in resolved.targets:
            by_document.setdefault(target["document"], {})[target["key"]] = format_value(target["value"], target["value_kind"])
        rendered = []
        for document, values in by_document.items():
            path = Path(snapshot_root) / document      # seeded from the case by core
            exists_before = path.is_file()
            before = path.read_bytes() if exists_before else b""
            text = patch_par(before.decode(), values)
            check_indices(text)                        # refused by name before any run
            rendered.append(RenderedFile(
                path=document, content=text.encode(), mode=None, exists_before=exists_before,
                before_digest=_digest_bytes(before) if exists_before else None,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)

    # -- rules
    def validate_run_semantics(self, case_root):
        return case_diagnostics(case_root)

    def get_plan_diagnostics(self, case_root, *, workflow_dag, env, scratch_root, driver_context):
        del workflow_dag, env, scratch_root, driver_context
        return tuple(item for item in case_diagnostics(case_root) if item.level != "error")

    # -- commands and environment
    def get_solver_commands(self):
        return SOLVER_COMMANDS

    def get_auxiliary_commands(self):
        return AUXILIARY_COMMANDS

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None):
        del environment_source, driver_context      # openCARP needs no environment source
        return opencarp_environment_diagnostics(workflow_dag, env if env is not None else os.environ)

    # -- parallel
    def get_solve_step_commands(self):
        return SOLVER_COMMANDS      # the step a parallel request runs under mpirun

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        return parallel_steps(step, request=request, read_value=read_value, allocation=allocation)

    def get_log_redaction_patterns(self):
        return REDACTION_PATTERNS     # consumed by core's redact_step_logs

    # -- record surface
    def get_record_key_catalog(self, case_root):
        # Only a document some record step passes with ``+F`` (the only ones
        # openCARP reads), minus the keys a record's command line assigns
        # after it (silently overridden) -- the same facts
        # record_key_validator refuses by, from the same records. A template
        # one of whose instances the command line owns
        # (``imp_region[Int].im_sv_init``) is omitted whole: the catalogue
        # has no "every index but 0" form, and listing a key the validator
        # refuses would itself be a defect.
        entries = []
        catalog = load_catalog()
        # The catalogue's only source is the binary's +Help (catalog_generation.py).
        source_ref = f"openCARP {catalog.identity.get('tag')} +Help"
        documents = read_documents(TUTORIAL_RECORDS)
        for document in sorted(d for d in documents if (Path(case_root) / d).is_file()):
            owned_templates = {template_name(key) for key in documents[document]}
            for spec in catalog.parameters.values():
                if spec.value_kind is None or spec.name in owned_templates:
                    continue
                entries.append({
                    "document": document, "key": spec.name, "value_kind": spec.value_kind,
                    "default": spec.default, "description": spec.description, "unit": spec.units,
                    "minimum": spec.minimum, "maximum": spec.maximum, "menu": list(spec.menu),
                    "source_refs": [source_ref],
                })
        return tuple(entries)

    def get_agent_guidance(self):
        text = resources.files(__package__).joinpath("guidance.md").read_text()
        return ({"title": "openCARP: what the binary does that a reader would not guess", "text": text},)

    # -- results as quantities
    def get_artifact_value_reader(self, artifact_format: str):
        """The LAT reader for the record's per-node LAT file; no other format is read."""
        return LatPerNodeReader() if artifact_format == LAT_FORMAT else None
