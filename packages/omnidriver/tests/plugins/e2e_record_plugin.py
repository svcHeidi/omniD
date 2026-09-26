"""A zero-argument-constructible tutorial-record plugin, for the manual
end-to-end CLI proof of step 2b item 2 (docs/superpowers/specs/2026-09-24-
tutorials-are-pointers-design.md).

Not a pytest test module (no ``test_`` prefix): this exists so ``--plugin
plugins.e2e_record_plugin:E2ERecordPlugin`` can be loaded by a real,
separately-invoked ``python -m omnidriver`` process, which cannot pass
constructor kwargs the way ``MinimalTestPlugin(tutorial_records=...)`` can
in-process. Everything a record/axis/validator/comparator/case-writer needs
is hardcoded here instead.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.tutorial_records import AxisContract, AxisResult, TutorialRecord, WorkflowStep

from plugins.minimal_plugin import MinimalTestPlugin

_FORMAT = "e2e_json_dictionary"


def _deep_set(node: dict, key_path: list[str], value: str) -> None:
    for segment in key_path[:-1]:
        node = node.setdefault(segment, {})
    node[key_path[-1]] = value


def _known_catalog_validator(document: str, key_path: tuple, value):
    catalog = {("constant/mesh.json", ("cells",)): "integer"}
    if (document, key_path) in catalog:
        return catalog[(document, key_path)], True
    raise KeyError(f"{document}:{'.'.join(key_path)} is not in this e2e catalog")


def _typed_agree(value_kind: str, requested, current) -> bool:
    if current is None:
        return False
    try:
        if value_kind == "integer":
            return int(requested) == int(current)
    except (TypeError, ValueError):
        return False
    return str(requested) == str(current)


def _number_cells_axis() -> AxisContract:
    def resolve(value, staged_case_root: Path) -> AxisResult:
        from omnidriver.core.tutorial_records import AxisPatch

        return AxisResult(
            patches=(
                AxisPatch(
                    document="constant/mesh.json", key_path=("cells",),
                    value=int(value), value_kind="integer",
                ),
            ),
        )

    return AxisContract(name="number_cells", value_kind="integer", resolve=resolve)


_TOY_RECORD = TutorialRecord(
    name="toyTutorial",
    native_case_relpath="toyTutorial",
    allowed_axes=frozenset({"number_cells"}),
    workflow_steps=(WorkflowStep(
        step_id="solve", command=("touch", "solved.marker"),
        consumes=("constant/mesh.json",), produces=("solved.marker",),
    ),),
)


class E2ERecordPlugin(MinimalTestPlugin):
    def __init__(self) -> None:
        super().__init__(
            solver_commands=frozenset({"touch"}),
            tutorial_records={"toyTutorial": _TOY_RECORD},
            axis_catalog={"number_cells": _number_cells_axis()},
            record_key_validator=_known_catalog_validator,
            case_value_comparator=_typed_agree,
        )

    def get_supported_mutation_modes(self):
        return frozenset({"clone_and_patch"})

    def get_record_key_catalog(self, case_root):
        del case_root
        return ({"document": "constant/mesh.json", "key": "cells", "value_kind": "integer",
                 "description": "the toy's cell count"},)

    def get_agent_guidance(self):
        return ({"title": "toy record", "text": "toyTutorial writes solved.marker; number_cells patches constant/mesh.json:cells."},)

    def resolve_case_mutation(self, request, *, driver_context):
        targets = tuple(
            {
                "qualified_id": p.qualified_id,
                "document": p.document,
                "expanded_key_path": list(p.expanded_key_path()),
                "value": p.value,
                "format": _FORMAT,
            }
            for p in request.parameters
        )
        expected_effects = tuple(
            f"set {p.qualified_id} in {p.document}" for p in request.parameters
        )
        return ResolvedMutation(
            request=request, targets=targets, preconditions=(),
            expected_effects=expected_effects, semantic_owner_id=self.plugin_id,
        )

    def get_rendered_formats(self):
        return frozenset({_FORMAT})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        # P2 fix (docs/superpowers/specs/2026-09-24-tutorials-are-pointers-
        # design.md, "Owner decisions" dated 2026-09-25): this already reads
        # whatever is at `snapshot_root/<document>` and merges the patched
        # keys on top of it -- a PATCH, never a replace. Before the fix, core
        # (`record_execution.commit_record_case`) handed every renderer an
        # EMPTY `snapshot_root`, so this code found nothing, treated an
        # existing multi-key document as brand new, and silently committed a
        # file holding ONLY the keys it touched -- discarding every sibling
        # key. Core now seeds `snapshot_root` with the real document before
        # calling this (`_seed_snapshot_root`), so `path.exists()` here is
        # finally truthful and this merge is correct. See
        # `test_commit_record_case_preserves_sibling_keys_in_a_multi_key_document`
        # (packages/omnidriver/tests/core/test_tutorial_records.py) for the
        # regression pin, and `case_transaction._check_render_exists_before`
        # for the transaction-level guard that refuses a renderer whose
        # `exists_before` claim disagrees with disk.
        by_document: dict[str, list] = {}
        for target in resolved.targets:
            by_document.setdefault(target["document"], []).append(target)
        rendered = []
        for document, targets in by_document.items():
            path = Path(snapshot_root) / document
            exists_before = path.exists()
            before_digest = _digest_bytes(path.read_bytes()) if exists_before else None
            content_obj = json.loads(path.read_text()) if exists_before else {}
            for target in targets:
                _deep_set(content_obj, target["expanded_key_path"], str(target["value"]))
            content = (json.dumps(content_obj, sort_keys=True) + "\n").encode()
            rendered.append(RenderedFile(
                path=document, content=content, mode=None,
                exists_before=exists_before, before_digest=before_digest,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)

    def get_config_value_reader(self):
        def _read(document_path: Path, key_path: tuple):
            if not document_path.exists():
                return None
            node = json.loads(document_path.read_text())
            *scope, key = key_path
            for segment in scope:
                if not isinstance(node, dict) or segment not in node:
                    return None
                node = node[segment]
            if not isinstance(node, dict) or key not in node:
                return None
            return node[key]

        return _read

    def get_case_value_comparator(self):
        return _typed_agree

    def has_case_marker(self, case_root) -> bool:
        """This e2e fixture's own recognizable marker file -- a committed
        record's staged case is always this plugin's case, the same way a
        real adapter recognizes its own dictionary file
        (cardiacfoam's ``has_case_marker`` checks for ``constant/
        electroProperties``); this fixture checks for its own toy
        ``constant/mesh.json`` instead."""
        return (Path(case_root) / "constant" / "mesh.json").exists()

    # No ``is_case_runnable_without_workflow`` (removed 2026-09-25, wave-2
    # review I4): it existed only to get this fixture's record runs past
    # run_document_exec's runnable-case gate, which core no longer applies
    # to a record run carrying its own steps
    # (``run_document_exec._is_record_run_with_steps``).

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None) -> tuple:
        """The toy's one real check: its solver command resolves on the supplied PATH."""
        del workflow_dag, environment_source, driver_context
        import shutil
        from omnidriver.core.planning_types import StrictDiagnostic

        path = (env or os.environ).get("PATH", "")
        return tuple(
            StrictDiagnostic(level="error", code="e2e_command_not_found",
                             message=f"{command!r} is not on PATH={path!r}")
            for command in sorted(self._solver_commands)
            if shutil.which(command, path=path) is None
        )

    def get_loaded_environment(self, *, environment_source=None, driver_context=None) -> dict:
        del environment_source, driver_context
        return dict(os.environ)

    def get_configured_environment(self, env, driver_context) -> dict:
        del driver_context
        return dict(env)
