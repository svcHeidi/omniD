from __future__ import annotations

from torchcor_testing import context_of, repository_with_runner

from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.scripts import find_script
from omnidriver.core.tutorial_records import ProducedPath


def test_the_installed_plugin_joins_a_stack_every_public_callable_naming_a_member():
    context = load_discovered_plugin("torchcor")
    assert context.stack.providers == context.providers


def test_each_record_step_runs_a_repository_script_and_its_formatted_outputs_are_readable(tmp_path):
    root = repository_with_runner(tmp_path)
    context = context_of(root)
    formats = []
    for record in context.stack.call("get_tutorial_records").values():
        for step in record.workflow_steps:
            assert find_script(step.command[0], context) == (root / "scripts" / step.command[0]).resolve()
            formats += [step.produced_format(path) for path in step.produces if isinstance(path, ProducedPath)]
    assert formats
    assert all(context.stack.call("get_artifact_value_reader", name) is not None for name in formats)
