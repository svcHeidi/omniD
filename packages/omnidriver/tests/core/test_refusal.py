"""Every refusal carries a stable code beside its text, and its structured refusals when it has them."""
from __future__ import annotations

import json

from omnidriver.core.refusal import CODES, Refusal, caught_code, failure, print_refusal
from omnidriver.core.specs.paths import ScratchRootNotSupplied
from omnidriver.core.tutorial_records import TutorialRecordError


def test_a_refusal_names_its_own_code_else_unclassified():
    assert failure(ScratchRootNotSupplied("no scratch"), action="plan") == {
        "status": "failed", "action": "plan", "code": "scratch_root_not_supplied", "error": "no scratch",
    }
    assert failure(TutorialRecordError("broken", code="case_rule"))["code"] == "case_rule"
    assert failure(None, code="workflow_state_failed", error="rerun with step")["code"] == "workflow_state_failed"
    assert failure(TutorialRecordError("broken"))["code"] == "unclassified"
    assert failure(SystemExit(3))["code"] == "unclassified"


def test_a_catch_all_reports_a_crash_as_internal_error_and_a_refusal_as_its_own():
    assert caught_code(KeyError("boom")) == "internal_error"
    assert caught_code(TutorialRecordError("k", code="unknown_key")) == "unknown_key"
    assert caught_code(ValueError("a plugin's refusal")) == "unclassified"


def test_every_code_the_source_names_is_in_the_vocabulary():
    """Each code literal a refusal is raised or printed with, in every package, is one :data:`CODES` lists."""
    import ast
    from pathlib import Path

    packages = Path(__file__).resolve().parents[3]
    named = set()
    for path in packages.glob("*/src/**/*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and _callee(node) in _REFUSING:
                named |= {
                    keyword.value.value for keyword in node.keywords
                    if keyword.arg == "code" and isinstance(keyword.value, ast.Constant)
                }
            if isinstance(node, ast.ClassDef):
                named |= {
                    item.value.value for item in node.body
                    if isinstance(item, ast.Assign) and [t.id for t in item.targets if isinstance(t, ast.Name)] == ["code"]
                    and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)
                }
    assert named and named <= set(CODES), sorted(named - set(CODES))


_REFUSING = {"failure", "TutorialRecordError", "Refusal", "update", "print_refusal"}


def _callee(node):
    import ast

    return node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None


def test_the_agent_guide_lists_every_code():
    from pathlib import Path

    guide = (Path(__file__).resolve().parents[4] / "AGENT_GUIDE.md").read_text()
    assert [code for code in CODES if f"`{code}`" not in guide] == []


def test_a_structured_refusal_keeps_its_diagnostics_beside_the_text():
    from omnidriver.core.planning_types import diagnostic

    broken = diagnostic("error", "catalog_rule", "m", source="d", field="k", detail={"rule": {"minimum": 0}})
    payload = failure(TutorialRecordError("k is -1", code="catalog_rule", diagnostics=(broken,)))
    assert payload["refusals"] == [{
        "level": "error", "code": "catalog_rule", "message": "m", "source": "d", "field": "k",
        "detail": {"rule": {"minimum": 0}},
    }]
    assert payload["error"] == "k is -1"


def test_print_refusal_prints_the_code(capsys):
    assert print_refusal(Refusal("bad flag")) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "code": "usage", "error": "bad flag"}
