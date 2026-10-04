"""The toy stack core's tests drive, and its fixtures.

``ToyStack`` is a solver in miniature over JSON case files. Its record
``toyTutorial`` runs one step that touches ``solved.marker``, and its axis
``number_cells`` patches ``constant/mesh.json:cells``. It has a key
validator, a comparator, a reader, a renderer, an environment preflight and
a record surface. ``ToyProvider`` is the bare provider it builds on, which a
test configures with only what it needs. Every other class is a fixture: the
toy with one thing changed, for a test or a conformance check to catch.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import shutil
from pathlib import Path
from typing import Mapping

from omnidriver.conformance import ConformanceTarget, QuantityTarget, RankEvidence
from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.conformance_study import ConformanceStudy
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic
from omnidriver.core.plugin_interface import CaseRuntimeConventions
from omnidriver.core.plugin_profile import CaseFileRule, EnvironmentConnection, PluginProfile, SuppliedVariable
from omnidriver.core.quantities import RawSample
from omnidriver.core.runtime import mpi
from omnidriver.core.runtime.models import DataArtifact
from omnidriver.core.runtime.sweep_manifest import CaseManifestEntry, SweepManifest, write_manifest
from omnidriver.core.tutorial_records import (
    AxisContract, AxisPatch, AxisResult, DefaultArgument, ProducedPath, RecordInput, TutorialRecord, WorkflowStep,
)

_FORMAT = "e2e_json_dictionary"


# -- the bare provider ----------------------------------------------------------


class ToyProvider:
    """Identity, plus whatever a test configures: an entrypoint, solver
    commands, records, a key validator, a comparator."""

    # Class defaults, so a test subclass that overrides __init__ without
    # super() still resolves every attribute below.
    _entrypoint: str | None = None
    _solver_commands: frozenset[str] = frozenset()
    _tutorial_records: dict = {}
    _record_key_validator = None
    _case_value_comparator = None

    plugin_name = "toy"
    plugin_id = "org.omnidriver.test-minimal"
    plugin_version = "1.0.0"
    plugin_api_version = "3"

    def __init__(
        self, *, entrypoint: str | None = None, solver_commands=None, tutorial_records: dict | None = None,
        record_key_validator=None, case_value_comparator=None,
    ) -> None:
        self._entrypoint = entrypoint
        if solver_commands is not None:
            self._solver_commands = frozenset(solver_commands)
        if tutorial_records is not None:
            self._tutorial_records = dict(tutorial_records)
        if record_key_validator is not None:
            self._record_key_validator = record_key_validator
        if case_value_comparator is not None:
            self._case_value_comparator = case_value_comparator

    def get_profile(self) -> PluginProfile:
        rules = () if self._entrypoint is None else (
            CaseFileRule(path=self._entrypoint, kind="case_script", role="test.case_script", required="conditional"),
        )
        return _profile(self, rules)

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        entrypoints = () if self._entrypoint is None else (self._entrypoint,)
        return CaseRuntimeConventions(case_entrypoints=entrypoints, case_script_commands=entrypoints)

    def get_solver_commands(self) -> frozenset[str]:
        return self._solver_commands

    def get_tutorial_records(self) -> dict:
        return dict(self._tutorial_records)

    def get_record_key_validator(self):
        return self._record_key_validator

    def get_case_value_comparator(self):
        return self._case_value_comparator


def _profile(provider, rules, environment=None) -> PluginProfile:
    return PluginProfile(
        path=Path(__file__), plugin_id=provider.plugin_id, api_version=provider.plugin_api_version,
        case_files=tuple(rules), cxx_mapping=None, environment=environment,
        payload={
            "schema_version": 1,
            "plugin": {"id": provider.plugin_id, "api_version": provider.plugin_api_version},
            "case_profile": {"dictionaries": [
                {"path": r.path, "kind": r.kind, "role": r.role, "required": r.required} for r in rules
            ]},
        },
    )


# -- the toy stack ----------------------------------------------------------------


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


def _read_json_value(document_path: Path, key_path: tuple):
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


def _number_cells_axis() -> AxisContract:
    def resolve(value, staged_case_root: Path) -> AxisResult:
        return AxisResult(patches=(AxisPatch(
            document="constant/mesh.json", key_path=("cells",), value=int(value), value_kind="integer",
        ),))

    return AxisContract(name="number_cells", value_kind="integer", resolve=resolve)


def _solve(command, *, consumes=("constant/mesh.json",), produces=("solved.marker",), **fields) -> WorkflowStep:
    return WorkflowStep(step_id="solve", command=command, consumes=consumes, produces=produces, **fields)


def _toy_record(*steps: WorkflowStep, **fields) -> TutorialRecord:
    """``toyTutorial`` with the given steps and fields."""
    fields.setdefault("axes", (_number_cells_axis(),))
    return TutorialRecord(name="toyTutorial", native_case_relpath="toyTutorial", workflow_steps=steps, **fields)


_TOY_RECORD = _toy_record(
    _solve(("touch", "solved.marker")),
    conformance=ConformanceStudy(
        requires=("touch",), base_study={}, patch=("constant/mesh.json:cells", 7),
        untouched=("constant/mesh.json", ("label",)), sweep_name="number_cells", sweep_values=(2, 3),
        unknown_name="cell_count",
    ),
)


class ToyStack(ToyProvider):
    RECORDS: Mapping[str, TutorialRecord] = {"toyTutorial": _TOY_RECORD}
    SOLVER_COMMANDS = frozenset({"touch"})

    def __init__(self) -> None:
        super().__init__(
            solver_commands=self.SOLVER_COMMANDS, tutorial_records=self.RECORDS,
            record_key_validator=_known_catalog_validator, case_value_comparator=_typed_agree,
        )

    def get_supported_mutation_modes(self):
        return frozenset({"clone_and_patch"})

    def get_record_key_catalog(self, case_root):
        return ({"document": "constant/mesh.json", "key": "cells", "value_kind": "integer",
                 "description": "the toy's cell count"},)

    def get_agent_guidance(self):
        return ({"title": "toy record", "text": "toyTutorial writes solved.marker; number_cells patches constant/mesh.json:cells."},)

    def resolve_case_mutation(self, request, *, driver_context):
        targets = tuple(
            {"qualified_id": p.qualified_id, "document": p.document,
             "expanded_key_path": list(p.expanded_key_path()), "value": p.value, "format": _FORMAT}
            for p in request.parameters
        )
        return ResolvedMutation(
            request=request, targets=targets,
            expected_effects=tuple(f"set {p.qualified_id} in {p.document}" for p in request.parameters),
            semantic_owner_id=self.plugin_id,
        )

    def get_rendered_formats(self):
        return frozenset({_FORMAT})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        """Patches each document core seeded into ``snapshot_root``: the
        keys not touched stay."""
        by_document: dict[str, list] = {}
        for target in resolved.targets:
            by_document.setdefault(target["document"], []).append(target)
        rendered = []
        for document, targets in by_document.items():
            path = Path(snapshot_root) / document
            exists_before = path.exists()
            content_obj = json.loads(path.read_text()) if exists_before else {}
            for target in targets:
                _deep_set(content_obj, target["expanded_key_path"], str(target["value"]))
            rendered.append(RenderedFile(
                path=document, content=(json.dumps(content_obj, sort_keys=True) + "\n").encode(), mode=None,
                exists_before=exists_before, before_digest=_digest_bytes(path.read_bytes()) if exists_before else None,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)

    def get_config_value_reader(self):
        return _read_json_value

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None) -> tuple:
        """The toy's one real check: its solver commands resolve on the supplied PATH."""
        path = (env or os.environ).get("PATH", "")
        return tuple(
            StrictDiagnostic(level="error", code="e2e_command_not_found", message=f"{command!r} is not on PATH={path!r}")
            for command in sorted(self._solver_commands)
            if shutil.which(command, path=path) is None
        )


def write_toy_native_case(cases_root: Path) -> Path:
    native = cases_root / "toyTutorial"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1", "label": "toy"}))
    return native


TOY_PLUGIN = "plugins.toy:ToyStack"


def toy_conformance_target(tmp_path: Path, *, plugin: str = TOY_PLUGIN) -> ConformanceTarget:
    cases_root = tmp_path / "native"
    write_toy_native_case(cases_root)
    return ConformanceTarget(
        plugin=plugin, record="toyTutorial", cases_root=cases_root, scratch_root=tmp_path / "scratch",
        base_study={}, patch=("constant/mesh.json:cells", 7), untouched=("constant/mesh.json", ("label",)),
        sweep_name="number_cells", sweep_values=(2, 3), unknown_name="cell_count",
    )


# -- fixtures: the shell a CLI test runs in --------------------------------------


class ScriptStepToy(ToyStack):
    """``toyTutorial`` runs the repository script ``solve.py`` as its one step."""

    SOLVER_COMMANDS = frozenset()
    RECORDS = {"toyTutorial": _toy_record(
        _solve(("solve.py",)),
        conformance=dataclasses.replace(_TOY_RECORD.conformance, requires=()),
    )}


class E2EFolderPlugin(ToyStack):
    """Declares a case entrypoint, so ``--case`` can run a folder."""

    def get_case_runtime_conventions(self):
        return CaseRuntimeConventions(case_entrypoints=("run-test-case",), case_script_commands=("run-test-case",))


class DeclaredCasePlugin(ToyProvider):
    """A bare provider with a case script, an explicit empty manifest and a preflight that passes."""

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(case_entrypoints=("run-test-case",), case_script_commands=("run-test-case",))

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None) -> tuple:
        return ()


#: The one variable ResumeTestPlugin's connection supplies.
RESUME_SUPPLIED_VARIABLE = "NUMERICAL_MODE"


class ResumeTestPlugin(DeclaredCasePlugin):
    """Declares one authored input, ``system/settings``, and one supplied variable, for the resume tests."""

    def get_profile(self) -> PluginProfile:
        return _profile(self, (CaseFileRule(
            path="system/settings", kind="test_configuration", role="test.configuration", required="always",
        ),), environment=EnvironmentConnection(supplied=(
            SuppliedVariable(RESUME_SUPPLIED_VARIABLE, False, "changes what the toy computes"),
        )))


class NeutralEnvironmentPlugin(ToyProvider):
    plugin_id = "org.omnidriver.test-neutral-environment"


# -- fixtures: a record changed ------------------------------------------------------


class NoConsumesPlugin(ToyStack):
    RECORDS = {"toyTutorial": _toy_record(_solve(("touch", "solved.marker"), consumes=()))}


class GhostConsumesPlugin(ToyStack):
    """Declares it consumes a file the native case does not have."""

    RECORDS = {"toyTutorial": _toy_record(_solve(
        ("touch", "solved.marker"), consumes=("constant/mesh.json", "does/not/exist.json"),
    ))}


class NoProducesPlugin(ToyStack):
    """Its record declares no outputs, so a run proves nothing about them."""

    RECORDS = {"toyTutorial": _toy_record(_solve(("touch", "solved.marker"), produces=()))}


#: Where NativeWritingPlugin's axis writes its stray file. Supplied through
#: the environment so it reaches the sweep's child processes.
STRAY_ROOT_VARIABLE = "CONFORMANCE_TOY_STRAY_ROOT"
STRAY_NAME = "stray-from-axis.txt"


def _stray_writing_axis() -> AxisContract:
    axis = _number_cells_axis()

    def resolve(value, staged_case_root):
        root = os.environ.get(STRAY_ROOT_VARIABLE)
        if root:
            (Path(root) / STRAY_NAME).write_text("written by an axis\n")
        return axis.resolve(value, staged_case_root)

    return dataclasses.replace(axis, resolve=resolve)


class NativeWritingPlugin(ToyStack):
    """Its axis also writes a file into the directory ``STRAY_ROOT_VARIABLE``
    names (the native cases root, in the bite test), outside the record's own
    subtree, where C7's digest never looks."""

    RECORDS = {"toyTutorial": dataclasses.replace(_TOY_RECORD, axes=(_stray_writing_axis(),))}


#: The fake credential LogRedactingPlugin's solve step prints, standing in
#: for the CI token openCARP's build header embeds in every run.
FAKE_CREDENTIAL_URL = "https://user:SECRET@host/x.git"


class LogRedactingPlugin(ToyStack):
    """Its solve step prints a credential URL to stdout, as openCARP's build header does."""

    SOLVER_COMMANDS = frozenset({"touch", "sh"})
    RECORDS = {"toyTutorial": _toy_record(_solve(("sh", "-c", f"echo {FAKE_CREDENTIAL_URL}; touch solved.marker")))}

    def get_log_redaction_patterns(self):
        return (r"(?<=://)[^/\s@]+(?=@)",)


class UndeclaredOutputPlugin(ToyStack):
    """Its solve step writes a file it does not declare in ``produces``."""

    SOLVER_COMMANDS = frozenset({"touch", "sh"})
    RECORDS = {"toyTutorial": _toy_record(_solve(("sh", "-c", "touch solved.marker undeclared.out")))}


#: What each route of DefaultRoutePlugin's record writes; C6 finds the
#: default route's marker only if the default route is the one that ran.
DEFAULT_ROUTE_MARKER = "native-route.marker"
OTHER_ROUTE_MARKER = "other-route.marker"


class DefaultRoutePlugin(ToyStack):
    """Two routes, the native one the default."""

    RECORDS = {"toyTutorial": _toy_record(
        dataclasses.replace(_solve(("touch", DEFAULT_ROUTE_MARKER), produces=(DEFAULT_ROUTE_MARKER,)), step_id="solveNative"),
        dataclasses.replace(_solve(("touch", OTHER_ROUTE_MARKER), produces=(OTHER_ROUTE_MARKER,)), step_id="solveOther"),
        workflow_variants={"native": ("solveNative",), "other": ("solveOther",)},
        variant_selector="route", default_variant="native",
    )}


#: The one file the toy bundle carries, and where the record's ``anatomy`` input writes it.
INPUT_BUNDLE_FILE = "bundle.json"
INPUT_DESTINATION = "0/bundle.json"


class WithInputPlugin(ToyStack):
    """One input with no native location, a toy stand-in for cardiacCore's anatomy bundle."""

    RECORDS = {"toyTutorial": _toy_record(
        _solve(("touch", "solved.marker"), consumes=("constant/mesh.json", INPUT_DESTINATION)),
        inputs=(RecordInput(name="anatomy", files=((INPUT_BUNDLE_FILE, INPUT_DESTINATION),)),),
    )}


def write_toy_input_bundle(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / INPUT_BUNDLE_FILE).write_text(json.dumps({"from": "the supplied bundle"}))
    return root


def toy_conformance_target_with_input(tmp_path: Path) -> ConformanceTarget:
    """A toy record with a supplied bundle, passing C1-C14 with no native tree."""
    bundle = write_toy_input_bundle(tmp_path / "bundle")
    target = toy_conformance_target(tmp_path, plugin=WITH_INPUT_PLUGIN)
    return dataclasses.replace(target, inputs={"anatomy": str(bundle)})


#: The file DefaultArgumentPlugin's step writes through its default argument,
#: and only through it: C6 finds it only if the default reached the command line.
DEFAULT_ARGUMENT_MARKER = "default-argument.marker"


def _marker_axis() -> AxisContract:
    def resolve(value, staged_case_root):
        return AxisResult(command_arguments={"solve": ("--marker", f"{value}.marker")})

    return AxisContract(name="marker", value_kind="word", resolve=resolve)


class DefaultArgumentPlugin(ToyStack):
    """``sh -c 'touch "$2"' sh --marker default-argument.marker``, the file name a replaceable default."""

    SOLVER_COMMANDS = frozenset({"touch", "sh"})
    RECORDS = {"toyTutorial": _toy_record(
        _solve(("sh", "-c", 'touch "$2"', "sh"), produces=(DEFAULT_ARGUMENT_MARKER,),
               default_arguments=(DefaultArgument(key=("--marker",), values=(DEFAULT_ARGUMENT_MARKER,)),)),
        axes=(_number_cells_axis(), _marker_axis()),
    )}


class ExplainingFailurePlugin(ToyStack):
    """Its solve step stops saying what it could not find; its hook names the key from the log."""

    SOLVER_COMMANDS = frozenset({"touch", "sh"})
    RECORDS = {"toyTutorial": _toy_record(_solve(("sh", "-c", "echo 'cannot find widget' >&2; exit 3")))}

    def explain_step_failure(self, log_text, case_root, *, driver_context):
        if "cannot find widget" not in log_text:
            return ()
        return (diagnostic("error", "widget_missing", f"widget is missing from {case_root.name}", field="widget"),)


def _catalogue_matches(env):
    return True, "3 models match"


def _catalogue_drifted(env):
    return False, "model A has a constant the solver lacks"


def _catalogue_unreadable(env):
    raise OSError("the utility is not built")


class ProbingPlugin(ToyStack):
    """Its record declares three probes of its catalogue: one matching, one drifted, one that cannot run."""

    RECORDS = {"toyTutorial": dataclasses.replace(_TOY_RECORD, conformance=dataclasses.replace(
        _TOY_RECORD.conformance,
        probes={"matches": _catalogue_matches, "drifted": _catalogue_drifted, "unreadable": _catalogue_unreadable},
    ))}


# -- fixtures: a member changed ---------------------------------------------------


class ReplacingRendererPlugin(ToyStack):
    """Truthful about exists_before, but writes a document holding only the patched keys."""

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        rendered = []
        for target in resolved.targets:
            path = Path(snapshot_root) / target["document"]
            exists_before = path.exists()
            content_obj: dict = {}
            _deep_set(content_obj, target["expanded_key_path"], str(target["value"]))
            rendered.append(RenderedFile(
                path=target["document"], content=(json.dumps(content_obj) + "\n").encode(),
                mode=None, exists_before=exists_before,
                before_digest=_digest_bytes(path.read_bytes()) if exists_before else None,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)


class SilentPreflightPlugin(ToyStack):
    """A preflight that ignores its ``env`` and never reports anything."""

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None) -> tuple:
        return ()


class FailingPreflightPlugin(ToyStack):
    """A preflight that finds the solver's environment broken."""

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None) -> tuple:
        return (StrictDiagnostic(level="error", code="toy_environment_missing", message="the toy's environment is not sourced"),)


class AuxiliaryOnlyPreflightPlugin(ToyStack):
    """With the solver off PATH, names only an auxiliary command and echoes
    the PATH it searched, as openCARP's preflight does."""

    def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None) -> tuple:
        path = (env if env is not None else os.environ).get("PATH", "")
        if shutil.which("touch", path=path) is not None:
            return ()
        return (StrictDiagnostic(level="error", code="toy_command_not_found", message=f"'toy-mesher' is not on PATH={path!r}"),)


class SilentSurfacePlugin(ToyStack):
    """No record surface: an agent reading describe learns nothing it may address."""

    get_record_key_catalog = None
    get_agent_guidance = None


def _catalogue_of(*entries):
    return lambda self, case_root: tuple(entries)


class UnlistedKeyPlugin(ToyStack):
    """A catalogue that omits the one key the target's own patch names."""

    get_record_key_catalog = _catalogue_of({"document": "constant/mesh.json", "key": "label", "value_kind": "string"})


class IndexedKeyPlugin(ToyStack):
    """Lists an indexed key in template form only, with ``[Int]``."""

    get_record_key_catalog = _catalogue_of({"document": "constant/mesh.json", "key": "cells[Int].count", "value_kind": "integer"})


class NamedKeyPlugin(ToyStack):
    """Lists a key with a named segment, ``<region_name>``, in template form only."""

    get_record_key_catalog = _catalogue_of(
        {"document": "constant/mesh.json", "key": "regions.<region_name>.count", "value_kind": "integer"},
    )


class OpenDocumentPlugin(ToyStack):
    """``constant/mesh.json`` as an open document: keys written as asked, unvalidated."""

    get_record_key_catalog = _catalogue_of({"document": "constant/mesh.json", "key": "<any>", "validated": False})


class OtherOpenDocumentPlugin(ToyStack):
    """An open document, but not the one the target's patch names."""

    get_record_key_catalog = _catalogue_of({"document": "constant/other.json", "key": "<any>", "validated": False})


class ValidatedKindlessPlugin(ToyStack):
    """An open-document entry that does not say it is unvalidated."""

    get_record_key_catalog = _catalogue_of({"document": "constant/mesh.json", "key": "<any>"})


class KindlessKeyPlugin(ToyStack):
    """Lists the target's key, but a second entry has no value kind."""

    def get_record_key_catalog(self, case_root):
        return (*super().get_record_key_catalog(case_root), {"document": "constant/mesh.json", "key": "label"})


class DocumentedCasePlugin(ToyStack):
    """Gives the native case's README.md the core role ``case.documentation``."""

    def get_profile(self):
        profile = super().get_profile()
        rule = CaseFileRule(path="README.md", kind="documentation", role="case.documentation", required="conditional")
        return dataclasses.replace(profile, case_files=(*profile.case_files, rule))


#: The refusal text the refusing fixtures raise, so a test can find it verbatim.
TOY_REFUSAL = "cells = 7 is refused by the toy's own format rule"


class ToyFormatError(ValueError):
    """A plugin's own refusal type, as openCARP's ``ParFormatError`` is."""


class RefusingRendererPlugin(ToyStack):
    """Its renderer refuses a value the key validator accepted, as openCARP's
    refuses an index beyond its count only at render."""

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        raise ToyFormatError(TOY_REFUSAL)


class RefusingResolverPlugin(ToyStack):
    def resolve_case_mutation(self, request, *, driver_context):
        raise ToyFormatError(TOY_REFUSAL)


class RefusingReaderPlugin(ToyStack):
    """Its reader refuses the native value it finds, as openCARP's refuses a non-0/1 Flag."""

    def get_config_value_reader(self):
        def _read(document_path, key_path):
            raise ToyFormatError(TOY_REFUSAL)

        return _read


class OverGeneratedConventionsPlugin(ToyStack):
    """Declares the native case's own authored input as a generated file name,
    so staging drops it even from the untouched native case's restage."""

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        return CaseRuntimeConventions(generated_file_names=("mesh.json",))


TOY_CELL_LIMIT = 10


class RuleCheckingPlugin(ToyStack):
    """Its one rule says a case holds at most ``TOY_CELL_LIMIT`` cells."""

    def validate_run_semantics(self, case_root):
        cells = int(json.loads((Path(case_root) / "constant" / "mesh.json").read_text())["cells"])
        if cells <= TOY_CELL_LIMIT:
            return ()
        return (diagnostic("error", "too_many_cells", f"{cells} cells exceed {TOY_CELL_LIMIT}", field="cells"),)


class AcceptingAnyKeyPlugin(ToyStack):
    """Its key validator accepts a key nobody declared, so a typo in a study reaches the case."""

    def get_record_key_validator(self):
        return lambda document, key_path, value: ("integer", False)


class AlwaysBrokenCasePlugin(ToyStack):
    """Its rule finds an error in every case, so no plan of it can run."""

    def validate_run_semantics(self, case_root):
        return (diagnostic("error", "always_broken", "this toy's rule refuses every case", field="cells"),)


# -- fixtures: parallel ----------------------------------------------------------------


def toy_parallel_steps(step, *, request, read_value, allocation):
    """Split, the solve with its rank count, join; the count is the case's cells."""
    if request is not True:
        raise ValueError(f"the toy reads its count from constant/mesh.json:cells; got request {request!r}")
    count = int(read_value("constant/mesh.json", ("cells",)))
    if allocation is not None and allocation.ranks != count:
        raise ValueError(f"{allocation.variable}={allocation.ranks} disagrees with constant/mesh.json:cells={count}")
    step_id = step["id"]
    return (
        {"id": f"{step_id}.split", "command": "touch", "args": [f"split.{count}"], "depends_on": list(step["depends_on"])},
        {**step, "args": [*step["args"], f"ranks.{count}"], "depends_on": [f"{step_id}.split"]},
        {"id": f"{step_id}.join", "command": "touch", "args": ["joined.marker"], "depends_on": [step_id]},
    )


class ParallelToyPlugin(ToyStack):
    def get_solve_step_commands(self):
        return frozenset({"touch"})

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        return toy_parallel_steps(step, request=request, read_value=read_value, allocation=allocation)


# -- fixtures: quantities ------------------------------------------------------------------

_CITE = {"source_id": "toy", "where": "this file"}
VALUES_FORMAT = "toy_named_values"
GRID_FORMAT = "toy_grid_values"


class ToyRowReader:
    """``<name> <value> <x> <y> <z>`` rows: seconds, ``-1`` never reached, metres."""

    value_unit = "s"
    sentinels = frozenset({-1.0})
    sampling_rule = "toy-row"
    coordinate_unit = "m"
    takes_points = False

    def read(self, case_root, artifact, request):
        rows = {}
        for line in (Path(case_root) / artifact.path_pattern).read_text().splitlines():
            if line.strip():
                name, value, x, y, z = line.split()
                rows[name] = RawSample(name=name, value=float(value), sampled_at=(float(x), float(y), float(z)))
        return tuple(rows[name] for name in request.names if name in rows)


class ToyNearestRowReader:
    """``<x> <y> <z> <value>`` rows in mm and ms; samples the row nearest each supplied point."""

    value_unit = "ms"
    sentinels = frozenset({-1.0})
    sampling_rule = "toy-nearest-row"
    coordinate_unit = "mm"
    takes_points = True

    def read(self, case_root, artifact, request):
        rows = []
        for line in (Path(case_root) / artifact.path_pattern).read_text().splitlines():
            if line.strip():
                x, y, z, value = (float(v) for v in line.split())
                rows.append(((x, y, z), value))
        samples = []
        for name in request.names:
            point, value = min(rows, key=lambda row: math.dist(row[0], request.points[name]))
            samples.append(RawSample(name=name, value=value, sampled_at=point))
        return tuple(samples)


class _FurlongReader(ToyRowReader):
    value_unit = "furlong"


class _NoWhereRowReader(ToyRowReader):
    """Its samples never report ``sampled_at``."""

    def read(self, case_root, artifact, request):
        return tuple(RawSample(name=s.name, value=s.value) for s in ToyRowReader.read(self, case_root, artifact, request))


class _RaisingReader(ToyRowReader):
    """``read`` always raises an exception that is not a ``ValueError``."""

    def read(self, case_root, artifact, request):
        raise OSError("disk fell over")


def write_toy_values(path: Path, rows: Mapping[str, tuple[str, tuple[float, float, float]]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{name} {value} {x} {y} {z}\n" for name, (value, (x, y, z)) in rows.items()))
    return path


TOY_QUANTITY_RECORD = TutorialRecord(
    name="toyQuantities", native_case_relpath="toyQuantities", axes=(_number_cells_axis(),),
    workflow_steps=(_solve(
        ("cp", "seed/values.txt", "values.txt"), consumes=("constant/mesh.json", "seed/values.txt"),
        produces=(ProducedPath("values.txt", format=VALUES_FORMAT),),
    ),),
)


def write_quantity_toy_case(cases_root: Path, values_text: str) -> Path:
    native = cases_root / "toyQuantities"
    (native / "constant").mkdir(parents=True)
    (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1", "label": "toy"}))
    (native / "seed").mkdir()
    (native / "seed" / "values.txt").write_text(values_text)
    return native


class QuantityToyPlugin(ToyStack):
    """``toyQuantities`` copies a values file the toy's readers read."""

    SOLVER_COMMANDS = frozenset({"cp"})
    RECORDS = {"toyQuantities": TOY_QUANTITY_RECORD}
    _READERS = {VALUES_FORMAT: ToyRowReader(), GRID_FORMAT: ToyNearestRowReader()}

    def get_artifact_value_reader(self, artifact_format: str):
        return self._READERS.get(artifact_format)


class RaisingReaderPlugin(QuantityToyPlugin):
    _READERS = {VALUES_FORMAT: _RaisingReader()}


class NoWhereReaderPlugin(QuantityToyPlugin):
    _READERS = {VALUES_FORMAT: _NoWhereRowReader()}


class DifferentVersionQuantityToyPlugin(QuantityToyPlugin):
    """A different declared version, so it changes ``capability_digest``."""

    plugin_version = "9.9.9"


class UnreadableFormatPlugin(ToyStack):
    """Declares a format on toyTutorial's output and has no reader for it."""

    RECORDS = {"toyTutorial": dataclasses.replace(_TOY_RECORD, workflow_steps=(
        _solve(("touch", "solved.marker"), produces=(ProducedPath("solved.marker", format="toy_unreadable"),)),
    ))}


class BadDeclarationPlugin(UnreadableFormatPlugin):
    """Has a reader for the format, whose value unit is not in core's table."""

    def get_artifact_value_reader(self, artifact_format: str):
        return _FurlongReader() if artifact_format == "toy_unreadable" else None


class ParallelQuantityToyPlugin(QuantityToyPlugin):
    """Its parallel form adds a split step, which prints the rank count, and leaves the solve alone."""

    SOLVER_COMMANDS = frozenset({"cp", "sh"})

    def get_solve_step_commands(self):
        return frozenset({"cp"})

    def _reported_ranks(self, count):
        return count

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        count = mpi.agree(mpi.requested(request), allocation)
        split = {"id": f"{step['id']}.split", "command": "sh",
                 "args": ["-c", 'echo "nRanks=$0"; cp constant/mesh.json "split.$1"', str(self._reported_ranks(count)), str(count)],
                 "depends_on": list(step["depends_on"])}
        return (split, {**step, "depends_on": [split["id"]]})


class ReorderingParallelPlugin(ParallelQuantityToyPlugin):
    """A parallel solve that writes different values from the serial one."""

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        split, solve = super().get_parallel_steps(step, request=request, read_value=read_value, allocation=allocation)
        return split, {**solve, "args": ["seed/other.txt", "values.txt"]}


class SingleRankPlugin(ParallelQuantityToyPlugin):
    """A parallel form that plans the parallel steps but whose solver reports one rank."""

    def _reported_ranks(self, count):
        return 1


class SerialParallelPlugin(ParallelQuantityToyPlugin):
    """A parallel form that returns the serial step unchanged."""

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        return (step,)


def write_toy_reference(path: Path, *, quantity_unit: str = "ms") -> Path:
    path.write_text(json.dumps({
        "schema_version": 1, "id": "toy-reference", "version": "1",
        "sources": [{"id": "toy", "citation": "the toy's own definition", "accessed": True}],
        "quantity": {"name": "first crossing", "definition": "the toy's value", "unit": quantity_unit, "source": _CITE},
        "frame": {"length_unit": "m", "definition": "the toy's frame", "stated_by_source": True, "source": _CITE},
        "points": [
            {"label": "A", "definition": "row a", "coordinates": [0, 0, 0.007], "source": _CITE},
            {"label": "B", "definition": "row b", "coordinates": [0.02, 0.003, 0], "source": _CITE},
            {"label": "Q", "definition": "not settled", "coordinates": None, "unresolved": "the toy never says", "source": _CITE},
        ],
    }))
    return path


def write_toy_sweep(output_dir: Path, cases: Mapping[str, str | None], *, plugin: str | None = None,
                    status: str = "completed", artifact_format: str = VALUES_FORMAT) -> Path:
    """A sweep output in the shape sweep_run leaves: manifest, run documents
    carrying the planning stack's identity, workflow states with digests, and
    each case's ``values.txt`` (``None``: the run wrote none)."""
    from omnidriver.core.plugin_interface import load_plugin_context

    identity = load_plugin_context(plugin or QUANTITY_TOY_PLUGIN).identity.to_json()
    artifact = DataArtifact(artifact_id="record.solve.0", path_pattern="values.txt",
                            format=artifact_format, produced_by="solve")
    entries = []
    for case_id, text in cases.items():
        case_root = output_dir / "cases" / case_id
        case_root.mkdir(parents=True)
        if text is not None:
            (case_root / "values.txt").write_text(text)
        (case_root / "run_document.json").write_text(json.dumps({
            "plugin": identity, "launch": {"caseRoot": str(case_root)},
            "expectedArtifacts": [dataclasses.asdict(artifact)],
        }))
        (case_root / "workflow_state.json").write_text(json.dumps({
            "status": status, "workflow_digest": f"sha256:plan-{case_id}",
            "resume_snapshot": {"aggregate_digest": f"sha256:inputs-{case_id}"},
        }))
        entries.append(CaseManifestEntry(
            case_id=case_id, resolved_axis_values={}, override_hash="sha256:none",
            run_document_path=f"cases/{case_id}/run_document.json",
            workflow_state_path=f"cases/{case_id}/workflow_state.json",
            status=status, outcome="fresh", started_at=None, updated_at="2026-09-26T00:00:00+00:00",
        ))
    write_manifest(output_dir / "sweep_manifest.json", SweepManifest(
        schema_version="1.0", sweep_spec_hash="sha256:toy", created_at="2026-09-26T00:00:00+00:00",
        updated_at="2026-09-26T00:00:00+00:00", cases=entries,
    ))
    return output_dir


def quantity_toy_conformance_target(tmp_path: Path, *, plugin: str | None = None) -> ConformanceTarget:
    """``toyQuantities`` with two quantities, A read in seconds and B never reached."""
    cases_root = tmp_path / "native"
    native = write_quantity_toy_case(cases_root, "A 0.0015 0 0 0.007\nB -1 0.02 0.003 0\n")
    (native / "seed" / "other.txt").write_text("A 0.0020 0 0 0.007\nB -1 0.02 0.003 0\n")
    return ConformanceTarget(
        plugin=plugin or PARALLEL_QUANTITY_PLUGIN, record="toyQuantities", cases_root=cases_root,
        scratch_root=tmp_path / "scratch", base_study={}, patch=("constant/mesh.json:cells", 7),
        untouched=("constant/mesh.json", ("label",)), sweep_name="number_cells", sweep_values=(2, 3),
        unknown_name="cell_count",
        quantity=QuantityTarget(
            artifact_format=VALUES_FORMAT, reference=write_toy_reference(tmp_path / "reference.json"),
            pairs={"A": "A", "B": "B"}, at={"A": (0.0, 0.0, 0.007), "B": (0.02, 0.003, 0.0)},
            at_unit="m", max_sampling_offset=0.0, study={"number_cells": 2}, sweep_values=(2, 3),
            tolerance=5.0, tolerance_unit="ms", parallel_tolerance=1e-9,
            rank_evidence=RankEvidence(log_pattern=r"nRanks=(\d+)"),
        ),
    )


def _selector(name: str) -> str:
    return f"plugins.toy:{name}"


PROBING_PLUGIN = _selector("ProbingPlugin")
REPLACING_PLUGIN = _selector("ReplacingRendererPlugin")
NO_CONSUMES_PLUGIN = _selector("NoConsumesPlugin")
GHOST_CONSUMES_PLUGIN = _selector("GhostConsumesPlugin")
NATIVE_WRITING_PLUGIN = _selector("NativeWritingPlugin")
NO_PRODUCES_PLUGIN = _selector("NoProducesPlugin")
SILENT_PREFLIGHT_PLUGIN = _selector("SilentPreflightPlugin")
FAILING_PREFLIGHT_PLUGIN = _selector("FailingPreflightPlugin")
AUXILIARY_ONLY_PREFLIGHT_PLUGIN = _selector("AuxiliaryOnlyPreflightPlugin")
SILENT_SURFACE_PLUGIN = _selector("SilentSurfacePlugin")
UNLISTED_KEY_PLUGIN = _selector("UnlistedKeyPlugin")
INDEXED_KEY_PLUGIN = _selector("IndexedKeyPlugin")
NAMED_KEY_PLUGIN = _selector("NamedKeyPlugin")
OPEN_DOCUMENT_PLUGIN = _selector("OpenDocumentPlugin")
OTHER_OPEN_DOCUMENT_PLUGIN = _selector("OtherOpenDocumentPlugin")
VALIDATED_KINDLESS_PLUGIN = _selector("ValidatedKindlessPlugin")
KINDLESS_KEY_PLUGIN = _selector("KindlessKeyPlugin")
DOCUMENTED_PLUGIN = _selector("DocumentedCasePlugin")
LOG_REDACTION_PLUGIN = _selector("LogRedactingPlugin")
REFUSING_RENDERER_PLUGIN = _selector("RefusingRendererPlugin")
REFUSING_RESOLVER_PLUGIN = _selector("RefusingResolverPlugin")
REFUSING_READER_PLUGIN = _selector("RefusingReaderPlugin")
UNDECLARED_OUTPUT_PLUGIN = _selector("UndeclaredOutputPlugin")
OVER_GENERATED_CONVENTIONS_PLUGIN = _selector("OverGeneratedConventionsPlugin")
DEFAULT_ROUTE_PLUGIN = _selector("DefaultRoutePlugin")
WITH_INPUT_PLUGIN = _selector("WithInputPlugin")
DEFAULT_ARGUMENT_PLUGIN = _selector("DefaultArgumentPlugin")
RULE_CHECKING_PLUGIN = _selector("RuleCheckingPlugin")
EXPLAINING_PLUGIN = _selector("ExplainingFailurePlugin")
ACCEPTING_PLUGIN = _selector("AcceptingAnyKeyPlugin")
BROKEN_RULE_PLUGIN = _selector("AlwaysBrokenCasePlugin")
PARALLEL_TOY_PLUGIN = _selector("ParallelToyPlugin")
QUANTITY_TOY_PLUGIN = _selector("QuantityToyPlugin")
DIFFERENT_VERSION_QUANTITY_TOY_PLUGIN = _selector("DifferentVersionQuantityToyPlugin")
RAISING_READER_PLUGIN = _selector("RaisingReaderPlugin")
UNREADABLE_PLUGIN = _selector("UnreadableFormatPlugin")
BAD_DECLARATION_PLUGIN = _selector("BadDeclarationPlugin")
NO_WHERE_READER_PLUGIN = _selector("NoWhereReaderPlugin")
PARALLEL_QUANTITY_PLUGIN = _selector("ParallelQuantityToyPlugin")
REORDERING_PARALLEL_PLUGIN = _selector("ReorderingParallelPlugin")
SERIAL_PARALLEL_PLUGIN = _selector("SerialParallelPlugin")
SINGLE_RANK_PLUGIN = _selector("SingleRankPlugin")
