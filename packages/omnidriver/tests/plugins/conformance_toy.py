"""The toy conformance target: E2ERecordPlugin's toyTutorial.

The native case is written into tmp_path by the caller's test, the same way
test_sweep_run_plugin_propagation builds it, but with a second key
(``label``). A one-key document cannot show a sibling key being lost; that
is how P2 hid.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from omnidriver.conformance import ConformanceTarget

TESTS_ROOT = Path(__file__).resolve().parents[1]
TOY_PLUGIN = "plugins.e2e_record_plugin:E2ERecordPlugin"

import json as _json

from omnidriver.core.case_write import RenderedFile, _digest_bytes
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

from plugins.e2e_record_plugin import E2ERecordPlugin, _FORMAT, _deep_set

REPLACING_PLUGIN = "plugins.conformance_toy:ReplacingRendererPlugin"
NO_CONSUMES_PLUGIN = "plugins.conformance_toy:NoConsumesPlugin"


class ReplacingRendererPlugin(E2ERecordPlugin):
    """Truthful about exists_before, but writes a document holding only the
    patched keys. case_transaction accepts it; only C4 can catch it."""

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        rendered = []
        for target in resolved.targets:
            path = Path(snapshot_root) / target["document"]
            exists_before = path.exists()
            content_obj: dict = {}
            _deep_set(content_obj, target["expanded_key_path"], str(target["value"]))
            rendered.append(RenderedFile(
                path=target["document"], content=(_json.dumps(content_obj) + "\n").encode(),
                mode=None, exists_before=exists_before,
                before_digest=_digest_bytes(path.read_bytes()) if exists_before else None,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)


def write_toy_native_case(cases_root: Path) -> Path:
    native = cases_root / "toyTutorial"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1", "label": "toy"}))
    return native


def toy_conformance_target(tmp_path: Path, *, plugin: str = TOY_PLUGIN) -> ConformanceTarget:
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    return ConformanceTarget(
        plugin=plugin,
        record="toyTutorial",
        cases_root=cases_root,
        scratch_root=tmp_path / "scratch",
        base_study={},
        patch=("constant/mesh.json:cells", 7),
        untouched=("constant/mesh.json", ("label",)),
        sweep_name="number_cells",
        sweep_values=(2, 3),
        unknown_name="cell_count",
        solver_command="touch",
        environment={
            "PYTHONPATH": os.pathsep.join([str(TESTS_ROOT), os.environ.get("PYTHONPATH", "")]),
        },
    )


class NoConsumesPlugin(E2ERecordPlugin):
    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            allowed_axes=frozenset({"number_cells"}),
            workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker"),
                                         produces=("solved.marker",)),),
        )}


GHOST_CONSUMES_PLUGIN = "plugins.conformance_toy:GhostConsumesPlugin"


class GhostConsumesPlugin(E2ERecordPlugin):
    """Declares it consumes a file the native case does not have. Provenance
    still lists the path (as ``unavailable``); C8 must not count that."""

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            allowed_axes=frozenset({"number_cells"}),
            workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker"),
                                         consumes=("constant/mesh.json", "does/not/exist.json"),
                                         produces=("solved.marker",)),),
        )}


NATIVE_WRITING_PLUGIN = "plugins.conformance_toy:NativeWritingPlugin"
#: Where NativeWritingPlugin's axis writes its stray file. Supplied through
#: the target's ``environment`` so it reaches the sweep's child processes.
STRAY_ROOT_VARIABLE = "CONFORMANCE_TOY_STRAY_ROOT"
STRAY_NAME = "stray-from-axis.txt"


class NativeWritingPlugin(E2ERecordPlugin):
    """Its number_cells axis also writes a file straight into the directory
    named by ``STRAY_ROOT_VARIABLE`` -- the native cases root, in the bite
    test -- outside the record's own subtree, where C7's digest never looks."""

    def __init__(self) -> None:
        super().__init__()
        from dataclasses import replace

        axis = self._axis_catalog["number_cells"]
        original = axis.resolve

        def resolve(value, staged_case_root):
            root = os.environ.get(STRAY_ROOT_VARIABLE)
            if root:
                (Path(root) / STRAY_NAME).write_text("written by an axis\n")
            return original(value, staged_case_root)

        self._axis_catalog = {**self._axis_catalog, "number_cells": replace(axis, resolve=resolve)}


NO_PRODUCES_PLUGIN = "plugins.conformance_toy:NoProducesPlugin"
SILENT_PREFLIGHT_PLUGIN = "plugins.conformance_toy:SilentPreflightPlugin"


class NoProducesPlugin(E2ERecordPlugin):
    """Its record declares no outputs, so a run proves nothing about them."""

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            allowed_axes=frozenset({"number_cells"}),
            workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker"),
                                         consumes=("constant/mesh.json",)),),
        )}


class SilentPreflightPlugin(E2ERecordPlugin):
    """A preflight that ignores its ``env`` and never reports anything."""

    def get_environment_diagnostics(self, workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None) -> tuple:
        del workflow_dag, env, explicit_bashrc, driver_context
        return ()


SILENT_SURFACE_PLUGIN = "plugins.conformance_toy:SilentSurfacePlugin"
UNLISTED_KEY_PLUGIN = "plugins.conformance_toy:UnlistedKeyPlugin"
INDEXED_KEY_PLUGIN = "plugins.conformance_toy:IndexedKeyPlugin"
DOCUMENTED_PLUGIN = "plugins.conformance_toy:DocumentedCasePlugin"


class SilentSurfacePlugin(E2ERecordPlugin):
    """Implements neither record-surface hook, as a plugin that predates C10
    would: an agent reading describe learns nothing it may address."""

    get_record_key_catalog = None
    get_agent_guidance = None


class UnlistedKeyPlugin(E2ERecordPlugin):
    """A catalogue that omits the one key the target's own patch names."""

    def get_record_key_catalog(self, case_root):
        del case_root
        return ({"document": "constant/mesh.json", "key": "label", "value_kind": "string"},)


class IndexedKeyPlugin(E2ERecordPlugin):
    """Lists an indexed key in template form only, with ``[Int]``."""

    def get_record_key_catalog(self, case_root):
        del case_root
        return ({"document": "constant/mesh.json", "key": "cells[Int].count", "value_kind": "integer"},)


class DocumentedCasePlugin(E2ERecordPlugin):
    """Gives the native case's README.md the core role ``case.documentation``."""

    def get_profile(self):
        from dataclasses import replace

        from omnidriver.core.plugin_profile import CaseFileRule

        profile = super().get_profile()
        rule = CaseFileRule(path="README.md", kind="documentation", role="case.documentation", required="conditional")
        return replace(profile, case_files=(*profile.case_files, rule))


KINDLESS_KEY_PLUGIN = "plugins.conformance_toy:KindlessKeyPlugin"


class KindlessKeyPlugin(E2ERecordPlugin):
    """Lists the target's key, but a second entry has no value kind."""

    def get_record_key_catalog(self, case_root):
        return (*super().get_record_key_catalog(case_root), {"document": "constant/mesh.json", "key": "label"})


LOG_REDACTION_PLUGIN = "plugins.conformance_toy:LogRedactingPlugin"
#: The fake credential this plugin's solve step prints, standing in for the
#: CI token openCARP's build header embeds in every run (K9, G3).
FAKE_CREDENTIAL_URL = "https://user:SECRET@host/x.git"


class LogRedactingPlugin(E2ERecordPlugin):
    """Its solve step prints a fake credential URL to stdout, the way
    openCARP's build header embeds a CI token in every real run. Declares
    ``get_log_redaction_patterns`` so ``workflow_runner`` scrubs the secret
    from the kept step log (K9)."""

    def __init__(self) -> None:
        super().__init__()
        # "sh" joins "touch" in the authorized command surface -- the step
        # below execs "sh" directly; "touch" inside its "-c" script is never
        # checked against command_authorization on its own.
        self._solver_commands = frozenset({"touch", "sh"})

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            allowed_axes=frozenset({"number_cells"}),
            workflow_steps=(WorkflowStep(
                step_id="solve",
                command=("sh", "-c", f"echo {FAKE_CREDENTIAL_URL}; touch solved.marker"),
                consumes=("constant/mesh.json",), produces=("solved.marker",),
            ),),
        )}

    def get_log_redaction_patterns(self):
        return (r"(?<=://)[^/\s@]+(?=@)",)      # only the credential; every match is replaced whole (I3)


REFUSING_RENDERER_PLUGIN = "plugins.conformance_toy:RefusingRendererPlugin"
REFUSING_RESOLVER_PLUGIN = "plugins.conformance_toy:RefusingResolverPlugin"
#: The refusal text both plugins below raise, so a test can find it verbatim.
TOY_REFUSAL = "cells = 7 is refused by the toy's own format rule"


class ToyFormatError(ValueError):
    """A plugin's own refusal type, the way openCARP's ``ParFormatError`` is."""


class RefusingRendererPlugin(E2ERecordPlugin):
    """Its renderer refuses a value the key validator accepted, the way
    openCARP's refuses an index beyond its count (F2) only at render."""

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        raise ToyFormatError(TOY_REFUSAL)


class RefusingResolverPlugin(E2ERecordPlugin):
    """Its resolver refuses, as ``resolve_case_mutation``'s contract allows."""

    def resolve_case_mutation(self, request, *, driver_context):
        raise ToyFormatError(TOY_REFUSAL)
