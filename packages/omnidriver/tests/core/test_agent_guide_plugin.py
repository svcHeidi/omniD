"""The plugin AGENT_GUIDE.md shows as the smallest one loads, describes, plans, reports its environment and passes C1."""

from __future__ import annotations

import json
import re
from contextlib import redirect_stdout
from io import StringIO

from conftest import NO_REPO_ROOT, repo_root, skip_without_repo

from omnidriver.cli import main
from omnidriver.conformance import ConformanceTarget
from omnidriver.conformance.checks import check_load
from omnidriver.core.plugin_interface import load_plugin_context

pytestmark = [skip_without_repo]

_GUIDE = (repo_root or NO_REPO_ROOT) / "AGENT_GUIDE.md"

_SURROUND = '''
from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

DEMO_RECORD = TutorialRecord(
    name="demo", native_case_relpath="demo",
    workflow_steps=(WorkflowStep(step_id="solve", command=("mysolver",), consumes=(), produces=()),),
)


def validate_key(document, key_path, value):
    return ("string", value)


def read_value(path, key_path):
    return None

'''


def _guide_plugin_source() -> str:
    text = _GUIDE.read_text()
    after = text.split("The smallest provider that runs a record serially:", 1)[1]
    return _SURROUND + re.search(r"```python\n(.*?)```", after, re.S).group(1)


def _cli(*argv: str) -> tuple[int, dict]:
    out = StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, json.loads(out.getvalue())


def test_the_guides_minimal_plugin_loads_describes_and_plans(tmp_path, monkeypatch) -> None:
    (tmp_path / "guide_plugin.py").write_text(_guide_plugin_source())
    monkeypatch.syspath_prepend(str(tmp_path))
    selector = "guide_plugin:MySolver"
    assert load_plugin_context(selector).identity.providers[0].id == "org.example.mysolver"

    cases = tmp_path / "cases"
    (cases / "demo").mkdir(parents=True)
    code, described = _cli("describe", "--plugin", selector, "--cases-root", str(cases), "--entry", "demo")
    assert code == 0, described
    code, environment = _cli("env", "--plugin", selector)
    assert code == 0, environment
    code, planned = _cli(
        "plan", "--strict", "--plugin", selector, "--cases-root", str(cases),
        "--scratch-dir", str(tmp_path / "scratch"), "--entry", "demo",
    )
    assert code == 0, planned
    target = ConformanceTarget(
        plugin=selector, record="demo", cases_root=cases, scratch_root=tmp_path / "scratch", base_study={},
        patch=("x.json:a", 1), untouched=("x.json", ()), sweep_name="a", sweep_values=(1,), unknown_name="b",
    )
    assert check_load(target).status == "passed"
