"""TorchCorPlugin: TorchCor as one self-contained provider."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.plugin_profile import load_plugin_profile

from .case_json import CaseJsonError, patch, read_value, values_agree

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
    def get_case_value_comparator(self):
        return values_agree

    def get_config_value_reader(self):
        def _read(document_path: Path, key_path: tuple):
            path = Path(document_path)
            return read_value(path.read_text(), ".".join(key_path)) if path.is_file() else None

        return _read

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
                # An unvalidated key only replaces one the case holds, so a typo adds nothing.
                if target["operation"] == "set" and read_value(text, key) is None:
                    raise CaseJsonError(f"{document}:{key} is not in the case, and an unvalidated key is never added")
            rendered.append(RenderedFile(
                path=document, content=patch(text, {k: t["value"] for k, t in targets.items()}).encode(),
                mode=None, exists_before=exists_before,
                before_digest=_digest_bytes(before) if exists_before else None,
                renderer_id=self.plugin_id, format=CASE_FORMAT,
            ))
        return tuple(rendered)
