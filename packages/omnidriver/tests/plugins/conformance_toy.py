"""The toy conformance target: E2ERecordPlugin's toyTutorial."""
from __future__ import annotations

import json
import os
from pathlib import Path

from omnidriver.conformance import ConformanceTarget, QuantityTarget
from omnidriver.core.runtime import mpi

TOY_PLUGIN = "plugins.e2e_record_plugin:E2ERecordPlugin"

import json as _json

from omnidriver.core.case_write import RenderedFile, _digest_bytes
from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.tutorial_records import RecordInput, TutorialRecord, WorkflowStep

from plugins.e2e_record_plugin import _TOY_RECORD, E2ERecordPlugin, _FORMAT, _deep_set, _number_cells_axis
from plugins.quantity_toy import VALUES_FORMAT, QuantityToyPlugin, write_quantity_toy_case, write_toy_reference

REPLACING_PLUGIN = "plugins.conformance_toy:ReplacingRendererPlugin"
NO_CONSUMES_PLUGIN = "plugins.conformance_toy:NoConsumesPlugin"


class ReplacingRendererPlugin(E2ERecordPlugin):
    """Truthful about exists_before, but writes a document holding only the patched keys."""

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
    )


class NoConsumesPlugin(E2ERecordPlugin):
    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            axes=(_number_cells_axis(),),
            workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker"),
                                         produces=("solved.marker",)),),
        )}


GHOST_CONSUMES_PLUGIN = "plugins.conformance_toy:GhostConsumesPlugin"


class GhostConsumesPlugin(E2ERecordPlugin):
    """Declares it consumes a file the native case does not have."""

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            axes=(_number_cells_axis(),),
            workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker"),
                                         consumes=("constant/mesh.json", "does/not/exist.json"),
                                         produces=("solved.marker",)),),
        )}


NATIVE_WRITING_PLUGIN = "plugins.conformance_toy:NativeWritingPlugin"
#: Where NativeWritingPlugin's axis writes its stray file. Supplied through
#: the environment so it reaches the sweep's child processes.
STRAY_ROOT_VARIABLE = "CONFORMANCE_TOY_STRAY_ROOT"
STRAY_NAME = "stray-from-axis.txt"


class NativeWritingPlugin(E2ERecordPlugin):
    """Its number_cells axis also writes a file straight into the directory named by ``STRAY_ROOT_VARIABLE`` -- the native cases root, in the bite test -- outside the record's own subtree, where C7's digest never looks."""

    def get_tutorial_records(self):
        from dataclasses import replace

        (axis,) = _TOY_RECORD.axes
        original = axis.resolve

        def resolve(value, staged_case_root):
            root = os.environ.get(STRAY_ROOT_VARIABLE)
            if root:
                (Path(root) / STRAY_NAME).write_text("written by an axis\n")
            return original(value, staged_case_root)

        return {"toyTutorial": replace(_TOY_RECORD, axes=(replace(axis, resolve=resolve),))}


NO_PRODUCES_PLUGIN = "plugins.conformance_toy:NoProducesPlugin"
SILENT_PREFLIGHT_PLUGIN = "plugins.conformance_toy:SilentPreflightPlugin"


class NoProducesPlugin(E2ERecordPlugin):
    """Its record declares no outputs, so a run proves nothing about them."""

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            axes=(_number_cells_axis(),),
            workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker"),
                                         consumes=("constant/mesh.json",)),),
        )}


class SilentPreflightPlugin(E2ERecordPlugin):
    """A preflight that ignores its ``env`` and never reports anything."""

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None) -> tuple:
        del workflow_dag, env, environment_source, driver_context
        return ()


AUXILIARY_ONLY_PREFLIGHT_PLUGIN = "plugins.conformance_toy:AuxiliaryOnlyPreflightPlugin"


class AuxiliaryOnlyPreflightPlugin(E2ERecordPlugin):
    """With the solver off PATH, reports only an auxiliary command missing, and echoes the PATH it searched -- as openCARP's preflight does for every missing command."""

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None) -> tuple:
        import shutil

        from omnidriver.core.planning_types import StrictDiagnostic

        del workflow_dag, environment_source, driver_context
        path = (env if env is not None else os.environ).get("PATH", "")
        if shutil.which("touch", path=path) is not None:
            return ()
        return (StrictDiagnostic(level="error", code="toy_command_not_found",
                                 message=f"'toy-mesher' is not on PATH={path!r}"),)


SILENT_SURFACE_PLUGIN = "plugins.conformance_toy:SilentSurfacePlugin"
UNLISTED_KEY_PLUGIN = "plugins.conformance_toy:UnlistedKeyPlugin"
INDEXED_KEY_PLUGIN = "plugins.conformance_toy:IndexedKeyPlugin"
DOCUMENTED_PLUGIN = "plugins.conformance_toy:DocumentedCasePlugin"


class SilentSurfacePlugin(E2ERecordPlugin):
    """Implements neither record-surface hook, as a plugin that predates C10 would: an agent reading describe learns nothing it may address."""

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


NAMED_KEY_PLUGIN = "plugins.conformance_toy:NamedKeyPlugin"
OPEN_DOCUMENT_PLUGIN = "plugins.conformance_toy:OpenDocumentPlugin"
OTHER_OPEN_DOCUMENT_PLUGIN = "plugins.conformance_toy:OtherOpenDocumentPlugin"
VALIDATED_KINDLESS_PLUGIN = "plugins.conformance_toy:ValidatedKindlessPlugin"


class NamedKeyPlugin(E2ERecordPlugin):
    """Lists a key with a named segment, `<region_name>`, in template form only."""

    def get_record_key_catalog(self, case_root):
        del case_root
        return ({"document": "constant/mesh.json", "key": "regions.<region_name>.count", "value_kind": "integer"},)


class OpenDocumentPlugin(E2ERecordPlugin):
    """Lists ``constant/mesh.json`` as an open document: its keys are written as asked, with no catalogue behind them (``validated: False``)."""

    def get_record_key_catalog(self, case_root):
        del case_root
        return ({"document": "constant/mesh.json", "key": "<any>", "validated": False},)


class OtherOpenDocumentPlugin(E2ERecordPlugin):
    """An open document, but not the one the target's patch names."""

    def get_record_key_catalog(self, case_root):
        del case_root
        return ({"document": "constant/other.json", "key": "<any>", "validated": False},)


class ValidatedKindlessPlugin(E2ERecordPlugin):
    """An open-document entry that does not say it is unvalidated."""

    def get_record_key_catalog(self, case_root):
        del case_root
        return ({"document": "constant/mesh.json", "key": "<any>"},)


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
    """Its solve step prints a fake credential URL to stdout, the way openCARP's build header embeds a CI token in every real run."""

    def __init__(self) -> None:
        super().__init__()
        # "sh" joins "touch" in the authorized command surface -- the step
        # below execs "sh" directly; "touch" inside its "-c" script is never
        # checked against command_authorization on its own.
        self._solver_commands = frozenset({"touch", "sh"})

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            axes=(_number_cells_axis(),),
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
    """Its renderer refuses a value the key validator accepted, the way openCARP's refuses an index beyond its count (F2) only at render."""

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        raise ToyFormatError(TOY_REFUSAL)


class RefusingResolverPlugin(E2ERecordPlugin):
    """Its resolver refuses, as ``resolve_case_mutation``'s contract allows."""

    def resolve_case_mutation(self, request, *, driver_context):
        raise ToyFormatError(TOY_REFUSAL)


REFUSING_READER_PLUGIN = "plugins.conformance_toy:RefusingReaderPlugin"


class RefusingReaderPlugin(E2ERecordPlugin):
    """Its config-value reader refuses the native value it finds, the way openCARP's refuses a non-0/1 Flag (F1) or an unquoted ``a=b`` (F10)."""

    def get_config_value_reader(self):
        def _read(document_path, key_path):
            raise ToyFormatError(TOY_REFUSAL)

        return _read


UNDECLARED_OUTPUT_PLUGIN = "plugins.conformance_toy:UndeclaredOutputPlugin"


class UndeclaredOutputPlugin(E2ERecordPlugin):
    """Its solve step writes a file it does not declare in ``produces``, so staging cannot know the file is generated."""

    def __init__(self) -> None:
        super().__init__()
        self._solver_commands = frozenset({"touch", "sh"})

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            axes=(_number_cells_axis(),),
            workflow_steps=(WorkflowStep(
                step_id="solve", command=("sh", "-c", "touch solved.marker undeclared.out"),
                consumes=("constant/mesh.json",), produces=("solved.marker",),
            ),),
        )}


OVER_GENERATED_CONVENTIONS_PLUGIN = "plugins.conformance_toy:OverGeneratedConventionsPlugin"


class OverGeneratedConventionsPlugin(E2ERecordPlugin):
    """Wrongly declares the native case's own authored input (``constant/mesh.json``) as a generated file name, so staging drops it even from the untouched native case's own restage."""

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(generated_file_names=("mesh.json",))


DEFAULT_ROUTE_PLUGIN = "plugins.conformance_toy:DefaultRoutePlugin"
#: What each route of DefaultRoutePlugin's record writes. C6 finds the
#: default route's marker only if the default route is the one that ran.
DEFAULT_ROUTE_MARKER = "native-route.marker"
OTHER_ROUTE_MARKER = "other-route.marker"


class DefaultRoutePlugin(E2ERecordPlugin):
    """Its record has two routes and names the native one its default (``default_variant``, owner Q2, 2026-09-26)."""

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            axes=(_number_cells_axis(),),
            workflow_steps=(
                WorkflowStep(step_id="solveNative", command=("touch", DEFAULT_ROUTE_MARKER),
                             consumes=("constant/mesh.json",), produces=(DEFAULT_ROUTE_MARKER,)),
                WorkflowStep(step_id="solveOther", command=("touch", OTHER_ROUTE_MARKER),
                             consumes=("constant/mesh.json",), produces=(OTHER_ROUTE_MARKER,)),
            ),
            workflow_variants={"native": ("solveNative",), "other": ("solveOther",)},
            variant_selector="route",
            default_variant="native",
        )}


WITH_INPUT_PLUGIN = "plugins.conformance_toy:WithInputPlugin"
#: The one file the toy bundle carries, and the destination its record's
#: ``anatomy`` input writes it to.
INPUT_BUNDLE_FILE = "bundle.json"
INPUT_DESTINATION = "0/bundle.json"


class WithInputPlugin(E2ERecordPlugin):
    """Declares one input with no native location, a toy stand-in for cardiacCore's anatomy bundle; covers conformance C8/C11."""

    def get_tutorial_records(self):
        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            axes=(_number_cells_axis(),),
            inputs=(RecordInput(name="anatomy", files=((INPUT_BUNDLE_FILE, INPUT_DESTINATION),)),),
            workflow_steps=(WorkflowStep(
                step_id="solve", command=("touch", "solved.marker"),
                consumes=("constant/mesh.json", INPUT_DESTINATION), produces=("solved.marker",),
            ),),
        )}


def write_toy_input_bundle(root: Path) -> Path:
    """A directory holding step S's one supplied file, for ``--input anatomy=<this>`` / ``ConformanceTarget.inputs``."""
    root.mkdir(parents=True, exist_ok=True)
    (root / INPUT_BUNDLE_FILE).write_text(json.dumps({"from": "the supplied bundle"}))
    return root


def toy_conformance_target_with_input(tmp_path: Path) -> ConformanceTarget:
    """Step S's own proof (design table, S2): a toy record with a supplied bundle, passing C1-C14 in core -- no native tree, no solver, needed."""
    from dataclasses import replace

    bundle = write_toy_input_bundle(tmp_path / "bundle")
    target = toy_conformance_target(tmp_path, plugin=WITH_INPUT_PLUGIN)
    return replace(target, inputs={"anatomy": str(bundle)})


DEFAULT_ARGUMENT_PLUGIN = "plugins.conformance_toy:DefaultArgumentPlugin"
#: The file DefaultArgumentPlugin's solve step writes through its default
#: argument, and only through it: C6 finds it only if the default reached
#: the real command line.
DEFAULT_ARGUMENT_MARKER = "default-argument.marker"


def _marker_axis():
    from omnidriver.core.tutorial_records import AxisContract, AxisResult

    def resolve(value, staged_case_root):
        del staged_case_root
        return AxisResult(command_arguments={"solve": ("--marker", f"{value}.marker")})

    return AxisContract(name="marker", value_kind="word", resolve=resolve)


class DefaultArgumentPlugin(E2ERecordPlugin):
    """Its solve step's file name is a replaceable default argument (``DefaultArgument``, owner Q3/Q7, 2026-09-26): ``sh -c 'touch "$2"' sh --marker default-argument.marker``."""

    def __init__(self) -> None:
        super().__init__()
        self._solver_commands = frozenset({"touch", "sh"})

    def get_tutorial_records(self):
        from omnidriver.core.tutorial_records import DefaultArgument

        return {"toyTutorial": TutorialRecord(
            name="toyTutorial", native_case_relpath="toyTutorial",
            axes=(_number_cells_axis(), _marker_axis()),
            workflow_steps=(WorkflowStep(
                step_id="solve", command=("sh", "-c", 'touch "$2"', "sh"),
                default_arguments=(DefaultArgument(key=("--marker",), values=(DEFAULT_ARGUMENT_MARKER,)),),
                consumes=("constant/mesh.json",), produces=(DEFAULT_ARGUMENT_MARKER,),
            ),),
        )}


PARALLEL_QUANTITY_PLUGIN = "plugins.conformance_toy:ParallelQuantityToyPlugin"
REORDERING_PARALLEL_PLUGIN = "plugins.conformance_toy:ReorderingParallelPlugin"
SERIAL_PARALLEL_PLUGIN = "plugins.conformance_toy:SerialParallelPlugin"


class ParallelQuantityToyPlugin(QuantityToyPlugin):
    """A toy whose record yields declared quantities and whose parallel form adds a split step and leaves the solve alone."""

    def get_solve_step_commands(self):
        return frozenset({"cp"})

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        count = mpi.agree(mpi.requested(request), allocation)
        split = {"id": f"{step['id']}.split", "command": "cp", "args": ["constant/mesh.json", f"split.{count}"],
                 "depends_on": list(step["depends_on"])}
        return (split, {**step, "depends_on": [split["id"]]})


class ReorderingParallelPlugin(ParallelQuantityToyPlugin):
    """A parallel solve that writes different values from the serial one."""

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        split, solve = super().get_parallel_steps(step, request=request, read_value=read_value, allocation=allocation)
        return split, {**solve, "args": ["seed/other.txt", "values.txt"]}


class SerialParallelPlugin(ParallelQuantityToyPlugin):
    """A parallel form that returns the serial step unchanged."""

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        return (step,)


def quantity_toy_conformance_target(tmp_path: Path, *, plugin: str = PARALLEL_QUANTITY_PLUGIN) -> ConformanceTarget:
    """``toyQuantities`` with two quantities, A read in seconds and B never reached."""
    cases_root = tmp_path / "native"
    native = write_quantity_toy_case(cases_root, "A 0.0015 0 0 0.007\nB -1 0.02 0.003 0\n")
    (native / "seed" / "other.txt").write_text("A 0.0020 0 0 0.007\nB -1 0.02 0.003 0\n")
    return ConformanceTarget(
        plugin=plugin,
        record="toyQuantities",
        cases_root=cases_root,
        scratch_root=tmp_path / "scratch",
        base_study={},
        patch=("constant/mesh.json:cells", 7),
        untouched=("constant/mesh.json", ("label",)),
        sweep_name="number_cells",
        sweep_values=(2, 3),
        unknown_name="cell_count",
        quantity=QuantityTarget(
            artifact_format=VALUES_FORMAT,
            reference=write_toy_reference(tmp_path / "reference.json"),
            pairs={"A": "A", "B": "B"},
            at={"A": (0.0, 0.0, 0.007), "B": (0.02, 0.003, 0.0)},
            at_unit="m", max_sampling_offset=0.0,
            study={"number_cells": 2}, sweep_values=(2, 3),
            tolerance=5.0, tolerance_unit="ms", parallel_tolerance=1e-9,
        ),
    )
