from __future__ import annotations

from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.torchcor.activation_reader import ACTIVATION_FORMAT


def test_torchcor_stack_is_one_provider_C1():
    ctx = load_discovered_plugin("torchcor")
    assert [p.plugin_id for p in ctx.providers] == ["org.omnidriver.torchcor"]


def test_the_nversion_record_runs_the_repository_runner_serially():
    record = load_discovered_plugin("torchcor").stack.call("get_tutorial_records")["nversion"]
    assert record.serial_only
    (step,) = record.workflow_steps
    assert step.command == ("run_case.py", "case.json")
    assert step.produced_format("out/activation_times.dat") == ACTIVATION_FORMAT
    assert record.conformance is not None and record.conformance.quantity.artifact_format == ACTIVATION_FORMAT


def test_the_solver_command_is_python3_and_guidance_is_given():
    stack = load_discovered_plugin("torchcor").stack
    assert stack.call("get_solver_commands") == frozenset({"python3"})
    (guidance,) = stack.call("get_agent_guidance")
    assert "mass_lumping" in guidance["text"]
