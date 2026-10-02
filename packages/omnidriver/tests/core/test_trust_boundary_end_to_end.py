"""End-to-end regression gate for the trust-boundary claims in SECURITY.md."""
from __future__ import annotations

import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest

from conftest import NO_REPO_ROOT, repo_root, skip_without_repo

pytestmark = [skip_without_repo]

from omnidriver.cli import main
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.workflow_runner import (
    _resolve_case_cwd,
    _resolve_command,
    run_workflow_step,
)
from omnidriver.core.runtime.workflow_state import initial_workflow_state
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

REPO_ROOT = repo_root or NO_REPO_ROOT
# This omnidriver checkout's own SECURITY.md: the CLI/RunDocument/workflow
# code these tests drive against lives here.
SECURITY_MD = REPO_ROOT / "SECURITY.md"

PLUGIN = "plugins.e2e_record_plugin:E2EFolderPlugin"
SCRIPT = "run-test-case"
CASE_NAME = "trustBoundaryCase"
RAN = "ran.marker"

# A case script that leaves exactly one file, so a permitted run reaches
# "completed" and a blocked one is distinguishable by the file's absence.
CASE_SCRIPT_OK = f"#!/bin/sh\ntouch {RAN}\nexit 0\n"


def _write_case(root: Path, *, script: str = CASE_SCRIPT_OK) -> Path:
    """A case folder whose workflow is the stack's declared case script."""
    case_root = root / CASE_NAME
    (case_root / "system").mkdir(parents=True)
    (case_root / "system" / "input.txt").write_text("authored\n")
    script_path = case_root / SCRIPT
    script_path.write_text(script)
    os.chmod(script_path, 0o755)
    return case_root


def _cli(argv: list[str]) -> tuple[int, dict]:
    """Invoke the real CLI and return (exit_code, parsed JSON report)."""
    out = StringIO()
    with redirect_stdout(out):
        code = main(argv)
    return code, json.loads(out.getvalue())


def _plan_to_file(case_root: Path, doc_path: Path, scratch: Path) -> dict:
    """`plan --strict --case` and persist the emitted RunDocument, whose
    ``launch.caseRoot`` is the staged copy under ``scratch``."""
    code, report = _cli([
        "plan", "--strict", "--plugin", PLUGIN, "--case", str(case_root),
        "--scratch-dir", str(scratch),
    ])
    assert code == 0, report
    run_document = report["run_document"]
    assert run_document is not None, report
    doc_path.write_text(json.dumps(run_document))
    return run_document


def _staged(document: dict) -> Path:
    return Path(document["launch"]["caseRoot"])


def _tampered_document(
    case_root: Path, doc_path: Path, scratch: Path,
    *, steps: list[dict] | None = None, launch: dict | None = None,
) -> Path:
    """A real planned RunDocument with one field replaced by agent content."""
    document = _plan_to_file(case_root, doc_path, scratch)
    if steps is not None:
        document["workflowDag"]["steps"] = steps
        # The planned workflowState's digest describes the *original* DAG.
        # Swapping in different steps without clearing it makes every such
        # document look like a resume of a mismatched prior attempt --
        # rejected by validate_resume regardless of the field under test.
        document["workflowState"] = None
    if launch is not None:
        document["launch"] = {**document["launch"], **launch}
    doc_path.write_text(json.dumps(document))
    return doc_path


def _hand_authored_document(doc_path: Path, *, case_root: Path, steps: list[dict]) -> Path:
    """A RunDocument built by hand, never derived from `plan --strict`."""
    document = {
        "version": "3",
        "id": "hand-authored",
        "name": "hand-authored",
        "status": "planned",
        "launch": {"caseRoot": str(case_root), "outputDir": str(case_root / "omnidriver-output")},
        "workflowDag": {
            "schema_version": "1",
            "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
            "steps": steps,
        },
    }
    doc_path.write_text(json.dumps(document))
    return doc_path


def _step(command: str, **overrides) -> dict:
    step = {
        "id": "s", "command": command, "args": [], "cwd": ".",
        "depends_on": [], "produces": [], "consumes": [],
        "retry_policy": {}, "command_display": command,
    }
    step.update(overrides)
    return step


def _codes(payload: dict) -> set[str]:
    return {d.get("code") for d in payload.get("diagnostics", [])}


def _plan_codes(report: dict) -> set[str]:
    """Every diagnostic code in a `plan --strict` report, across its buckets."""
    codes: set[str] = set()
    for key, value in report.items():
        if key.endswith("_diagnostics") and isinstance(value, list):
            codes.update(d.get("code") for d in value if isinstance(d, dict))
    return codes


# --------------------------------------------------------------------------
# Documented-closed claim: "launch.caseRoot ... when OMNIDRIVER_ALLOWED_RUNS_ROOT
# is set, both must resolve under it" (Trust boundaries / Mitigations).
# --------------------------------------------------------------------------

def test_case_root_outside_allowed_runs_root_is_rejected_before_execution(tmp_path) -> None:
    """SECURITY.md: "opt-in OMNIDRIVER_ALLOWED_RUNS_ROOT containment"."""
    case_root = _write_case(tmp_path / "cases")
    doc_path = tmp_path / "run.json"
    staged = _staged(_plan_to_file(case_root, doc_path, tmp_path / "scratch"))

    elsewhere = tmp_path / "allowed-elsewhere"
    elsewhere.mkdir()
    with mock.patch.dict(os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(elsewhere)}):
        code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    assert code != 0, payload
    assert "case_root_outside_allowed_root" in _codes(payload), payload
    # Rejected at ingestion: the case script never ran.
    assert not (staged / RAN).exists()


def test_output_dir_outside_allowed_runs_root_is_rejected_before_execution(tmp_path) -> None:
    """SECURITY.md: containment applies to `outputDir`, not just `caseRoot`."""
    allowed = tmp_path / "allowed"
    case_root = _write_case(allowed / "cases")
    doc_path = allowed / "run.json"
    document = _plan_to_file(case_root, doc_path, allowed / "scratch")
    document["launch"]["outputDir"] = str(tmp_path / "outside-results")
    doc_path.write_text(json.dumps(document))

    with mock.patch.dict(os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(allowed)}):
        code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    assert code != 0, payload
    assert "output_dir_outside_allowed_root" in _codes(payload), payload
    assert not (_staged(document) / RAN).exists()


def test_symlinked_case_root_cannot_escape_allowed_runs_root(tmp_path) -> None:
    """SECURITY.md: paths are "resolved to canonical absolute paths", so containment "runs on resolved paths, so a symlink ..."."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    case_root = _write_case(outside / "cases")
    doc_path = tmp_path / "run.json"
    document = _plan_to_file(case_root, doc_path, outside / "scratch")
    real_staged = _staged(document)

    # A symlink that *lexically* sits inside the allowed root but points out.
    link = allowed / CASE_NAME
    link.symlink_to(real_staged)
    document["launch"]["caseRoot"] = str(link)
    document["launch"]["outputDir"] = str(link / "out")
    doc_path.write_text(json.dumps(document))

    with mock.patch.dict(os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(allowed)}):
        code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    assert code != 0, payload
    assert "case_root_outside_allowed_root" in _codes(payload), payload
    assert not (real_staged / RAN).exists()


def test_allowed_runs_root_permits_a_contained_case(tmp_path) -> None:
    """Containment is a boundary, not a blanket refusal: an in-root case runs."""
    case_root = _write_case(tmp_path / "cases")
    doc_path = tmp_path / "run.json"
    staged = _staged(_plan_to_file(case_root, doc_path, tmp_path / "scratch"))

    with mock.patch.dict(os.environ, {"OMNIDRIVER_ALLOWED_RUNS_ROOT": str(tmp_path)}):
        code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    assert code == 0, payload
    assert payload["status"] == "ok"
    assert (staged / RAN).exists()


# --------------------------------------------------------------------------
# Documented-closed claim: "launch.caseRoot must be an existing directory".
# --------------------------------------------------------------------------

def test_case_root_must_be_an_existing_directory(tmp_path) -> None:
    case_root = _write_case(tmp_path / "cases")
    scratch = tmp_path / "scratch"

    not_a_dir = tmp_path / "a-file"
    not_a_dir.write_text("")
    doc_path = _tampered_document(
        case_root, tmp_path / "run.json", scratch,
        launch={"caseRoot": str(not_a_dir), "outputDir": str(tmp_path / "out")},
    )
    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    assert code != 0, payload
    assert "case_root_not_a_directory" in _codes(payload), payload

    missing = tmp_path / "does-not-exist"
    doc_path = _tampered_document(
        case_root, tmp_path / "run2.json", scratch,
        launch={"caseRoot": str(missing), "outputDir": str(missing / "out")},
    )
    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    assert code != 0, payload
    assert "case_root_missing" in _codes(payload), payload


# --------------------------------------------------------------------------
# Documented-closed claim: the command allowlist (validate_workflow_commands).
# --------------------------------------------------------------------------

def test_command_authorization_rejects_an_unauthorized_bare_command(tmp_path) -> None:
    """SECURITY.md: only a command the stack declares, a case script it declares, a registered utility, or an installed environment application."""
    case_root = _write_case(tmp_path / "cases")
    sentinel = tmp_path / "PWNED"
    doc_path = _tampered_document(
        case_root, tmp_path / "run.json", tmp_path / "scratch",
        steps=[_step("sh", args=["-c", f"touch {sentinel}"])],
    )
    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    assert code != 0, payload
    assert "unknown_workflow_command" in _codes(payload), payload
    assert not sentinel.exists(), "unauthorized command must not execute"


def test_command_authorization_rejects_an_absolute_path_command(tmp_path) -> None:
    """SECURITY.md: "Absolute-path ... commands are rejected"."""
    case_root = _write_case(tmp_path / "cases")
    sentinel = tmp_path / "PWNED"
    doc_path = _tampered_document(
        case_root, tmp_path / "run.json", tmp_path / "scratch",
        steps=[_step("/usr/bin/touch", args=[str(sentinel)])],
    )
    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    assert code != 0, payload
    assert "unknown_workflow_command" in _codes(payload), payload
    message = " ".join(
        d["message"] for d in payload["diagnostics"]
        if d.get("code") == "unknown_workflow_command"
    )
    assert "explicit path" in message, payload
    assert not sentinel.exists()


def test_command_authorization_rejects_an_arbitrary_relative_script(tmp_path) -> None:
    """SECURITY.md: "arbitrary ./script commands are rejected" -- only the stack's declared case script may be given in path form."""
    case_root = _write_case(tmp_path / "cases")
    sentinel = tmp_path / "PWNED"
    # The step runs in the staged copy, so the script must be in the case the plan stages.
    pwn = case_root / "pwn.sh"
    pwn.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
    os.chmod(pwn, 0o755)
    scratch = tmp_path / "scratch"

    doc_path = _tampered_document(
        case_root, tmp_path / "run.json", scratch, steps=[_step("./pwn.sh")],
    )
    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    assert code != 0, payload
    assert "unknown_workflow_command" in _codes(payload), payload
    assert not sentinel.exists()

    # ...while the declared case script is accepted.
    doc_path = _tampered_document(
        case_root, tmp_path / "run_script.json", scratch,
        steps=[_step(f"./{SCRIPT}", id="run", produces=[])],
    )
    staged = _staged(json.loads(doc_path.read_text()))
    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    assert code == 0, payload
    assert (staged / RAN).exists()


def test_command_allowlist_has_one_owner_shared_by_both_producers(tmp_path) -> None:
    """SECURITY.md: "Single command allowlist owner (validate_workflow_commands), enforced once at ingestion" -- so the strict planner and the run-document adapter cannot drift apart."""
    ctx = load_plugin_context(PLUGIN)
    # Producer 1: strict planning of a record whose step is an unauthorized command.
    planner_root = tmp_path / "planner"
    _write_case(planner_root)
    record = TutorialRecord(
        name=CASE_NAME, native_case_relpath=CASE_NAME,
        workflow_steps=(WorkflowStep(step_id="run", command=("curl",)),),
    )
    plan_report = strict_plan(
        record, overrides={"cases_root": str(planner_root)},
        scratch_root=tmp_path / "planner-scratch", driver_context=ctx,
    ).to_json()
    assert "unknown_workflow_command" in _plan_codes(plan_report), plan_report

    # Producer 2: an agent-authored RunDocument carrying the same command,
    # ingested through the run path instead of the planner.
    adapter_root = tmp_path / "adapter"
    case_root = _write_case(adapter_root)
    doc_path = _tampered_document(
        case_root, tmp_path / "run.json", tmp_path / "adapter-scratch", steps=[_step("curl")],
    )
    run_code, run_payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    assert run_code != 0, run_payload
    assert "unknown_workflow_command" in _codes(run_payload), run_payload


# --------------------------------------------------------------------------
# Documented-closed claim: "No command shadowing: bare names resolve via PATH
# only; only the stack's declared case scripts resolve case-locally".
# --------------------------------------------------------------------------

def test_case_directory_cannot_shadow_a_trusted_path_binary(tmp_path) -> None:
    """SECURITY.md: "No command shadowing"."""
    case_root = _write_case(tmp_path / "cases")
    sentinel = tmp_path / "PWNED"
    shadow = case_root / "touch"
    shadow.write_text(f"#!/bin/sh\ncommand touch {sentinel}\n")
    os.chmod(shadow, 0o755)

    # The resolver is the enforcement point: a case-local `touch` is never
    # picked up, while the stack's declared case script deliberately is --
    # for the *active plugin's* declared entrypoints (Core itself declares no
    # case-script names; see workflow.case_script_commands's "with no
    # context the set is empty" and test_case_script_commands_entrypoint_seam.py).
    context = load_plugin_context(PLUGIN)
    assert _resolve_command("touch", case_root) == "touch"
    assert _resolve_command(SCRIPT, case_root, context) == str(case_root / SCRIPT)

    # End-to-end: running the step never executes the case-local shadow.
    doc_path = _hand_authored_document(
        tmp_path / "run.json", case_root=case_root, steps=[_step("touch", args=["marker"])],
    )
    _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    assert not sentinel.exists(), "case-local binary shadowed a PATH command"


def test_a_plugins_declared_entrypoint_resolves_case_locally_but_blockmesh_still_never_does(tmp_path) -> None:
    """SECURITY.md: "No command shadowing", extended to the Tier 4 entrypoint seam (future/CASE_SCRIPT_COMMANDS_ENTRYPOINT_THREAT_MODEL.md) -- a plugin naming its entrypoint anything gets the same case-local resolution, but a command the stack does not declare as a case script must never resolve case-locally, regardless of which plugin is active."""
    from plugins.minimal_plugin import MinimalTestPlugin

    from omnidriver.core.plugin_interface import CaseRuntimeConventions
    from omnidriver.core.plugin_interface import driver_context as _driver_context
    from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile

    class _ForeignEntrypointPlugin(MinimalTestPlugin):
        def get_profile(self) -> PluginProfile:
            return PluginProfile(
                path=Path(__file__),
                plugin_id=self.plugin_id,
                api_version=self.plugin_api_version,
                case_files=(
                    CaseFileRule(
                        path="run.sh", kind="case_script",
                        role="openfoam.entrypoint", required="conditional",
                    ),
                ),
                cxx_mapping=None,
                payload={
                    "schema_version": 1,
                    "plugin": {"id": self.plugin_id, "api_version": self.plugin_api_version},
                    "case_profile": {"dictionaries": []},
                },
            )

        def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
            # case_script_commands()/entrypoint_relpaths() read this capability,
            # not get_profile() -- see test_case_script_commands_entrypoint_seam.py's
            # identically-shaped _ForeignEntrypointPlugin, the un-gated sibling
            # of this exact seam.
            return CaseRuntimeConventions(
                case_entrypoints=("run.sh",),
                case_script_commands=("run.sh",),
            )

    case_root = tmp_path
    (case_root / "run.sh").write_text("#!/bin/sh\n")
    os.chmod(case_root / "run.sh", 0o755)
    (case_root / "blockMesh").write_text("#!/bin/sh\ntouch PWNED\n")
    os.chmod(case_root / "blockMesh", 0o755)

    ctx = _driver_context(_ForeignEntrypointPlugin(), source="test")

    assert _resolve_command("run.sh", case_root, ctx) == str(case_root / "run.sh")
    assert _resolve_command("blockMesh", case_root, ctx) == "blockMesh"
    # Without the plugin declaring it, the same name is not a case script.
    assert _resolve_command("run.sh", case_root) == "run.sh"


# --------------------------------------------------------------------------
# Documented-closed claim: "Workflow cwd cannot escape caseRoot".
# --------------------------------------------------------------------------

def test_workflow_cwd_cannot_escape_case_root(tmp_path) -> None:
    """SECURITY.md: "Workflow `cwd` cannot escape `caseRoot`"."""
    case_root = _write_case(tmp_path / "cases")

    # Layer 1 -- ingestion, via the real CLI run path.
    doc_path = _hand_authored_document(
        tmp_path / "run.json", case_root=case_root, steps=[_step(SCRIPT, cwd="../..")],
    )
    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    assert code != 0, payload
    assert "workflow_cwd_not_case_relative" in _codes(payload), payload

    # Layer 2 -- the runner's own resolved-path check.
    with pytest.raises(ValueError, match="escapes case root"):
        _resolve_case_cwd(case_root, "../..")

    outside = tmp_path / "outside"
    outside.mkdir()
    (case_root / "escape").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes case root"):
        _resolve_case_cwd(case_root, "escape")


# --------------------------------------------------------------------------
# Documented-closed claim: "Steps run argv-style (no shell)".
# --------------------------------------------------------------------------

def test_steps_run_argv_style_so_arguments_are_not_shell_interpreted(tmp_path) -> None:
    """SECURITY.md: "Steps run argv-style (no shell)"."""
    sentinel = tmp_path / "PWNED"
    recorded = "args.txt"
    case_root = _write_case(
        tmp_path / "cases",
        script=f"#!/bin/sh\nprintf '%s' \"$1\" > {recorded}\ntouch {RAN}\nexit 0\n",
    )
    doc_path = _hand_authored_document(
        tmp_path / "run.json", case_root=case_root,
        steps=[_step(SCRIPT, args=[f"; touch {sentinel}"])],
    )

    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])
    assert code == 0, payload
    assert not sentinel.exists(), "argument was interpreted by a shell"
    assert (case_root / recorded).read_text() == f"; touch {sentinel}"


# --------------------------------------------------------------------------
# Documented-OPEN claims. These assert that SECURITY.md's "Explicitly NOT
# mitigated" section is an accurate statement about today's code, so that
# closing one of these holes shows up here as a failure and forces the
# document to be updated instead of silently going stale.
# --------------------------------------------------------------------------

def test_case_script_caveat_is_still_documented_and_still_true(tmp_path) -> None:
    """SECURITY.md documents case scripts as "untrusted, unsandboxed by design" -- "running a case runs its code"."""
    text = SECURITY_MD.read_text()
    assert "unsandboxed by design" in text
    assert "Arbitrary code inside an invoked `Allrun`" in text

    # The case script writes *outside* its own case root: nothing confines it.
    escaped = tmp_path / "written-by-the-case-script.txt"
    case_root = _write_case(
        tmp_path / "cases",
        script=f"#!/bin/sh\nprintf 'case script ran unsandboxed' > {escaped}\ntouch {RAN}\nexit 0\n",
    )
    doc_path = tmp_path / "run.json"
    _plan_to_file(case_root, doc_path, tmp_path / "scratch")
    code, payload = _cli(["run", "--plugin", PLUGIN, "--run-document", str(doc_path)])

    assert code == 0, payload
    assert escaped.read_text() == "case script ran unsandboxed", (
        "SECURITY.md still claims case script contents are unsandboxed; if this "
        "assertion fails a sandbox was added -- update SECURITY.md."
    )


def test_run_workflow_step_is_still_a_trusted_unvalidating_primitive(tmp_path) -> None:
    """SECURITY.md: "run_workflow_step is a trusted low-level primitive: a Python caller that invokes it directly with an unvalidated case_root / ..."."""
    text = SECURITY_MD.read_text()
    assert "run_workflow_step` is a trusted low-level primitive" in text

    # Not a case at all, and a command no allowlist authorizes.
    bare_dir = tmp_path / "not-a-case"
    bare_dir.mkdir()
    sentinel = tmp_path / "written-by-unvalidated-runner.txt"
    dag = {
        "schema_version": "1",
        "step_status_values": ["pending", "running", "completed", "failed", "skipped"],
        "steps": [{
            "id": "s", "command": "touch", "args": [str(sentinel)],
            "cwd": ".", "depends_on": [], "produces": [], "consumes": [],
            "retry_policy": {}, "command_display": "touch",
        }],
    }
    result = run_workflow_step(
        dag, initial_workflow_state(dag), "s",
        case_root=bare_dir, log_dir=tmp_path / "logs",
    )
    assert result.state.steps[0].status == "completed"
    assert sentinel.exists(), (
        "SECURITY.md still claims run_workflow_step performs no path/command "
        "validation; if this fails, validation was added -- update SECURITY.md."
    )
