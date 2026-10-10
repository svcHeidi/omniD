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


def _source_trees():
    import ast
    from pathlib import Path

    packages = Path(__file__).resolve().parents[3]
    return [(path, ast.parse(path.read_text())) for path in packages.glob("*/src/**/*.py")]


def _callee(node):
    import ast

    return node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""


def _named_codes():
    """Every code a call passes as ``code=`` to any call but a diagnostic's, a refusal-shaped dict literal (``"status": "failed"``) holds under ``"code"``, or a class declares as ``code``."""
    import ast

    named = set()
    for _path, tree in _source_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and not _callee(node).endswith(("Diagnostic", "diagnostic")):
                named |= {
                    keyword.value.value for keyword in node.keywords
                    if keyword.arg == "code" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str)
                }
            elif isinstance(node, ast.Dict) and any(
                isinstance(key, ast.Constant) and key.value == "status"
                and isinstance(value, ast.Constant) and value.value in ("failed", "blocked")
                for key, value in zip(node.keys, node.values)
            ):
                named |= {
                    value.value for key, value in zip(node.keys, node.values)
                    if isinstance(key, ast.Constant) and key.value == "code"
                    and isinstance(value, ast.Constant) and isinstance(value.value, str)
                }
            elif isinstance(node, ast.ClassDef):
                named |= {
                    item.value.value for item in node.body
                    if isinstance(item, ast.Assign) and [t.id for t in item.targets if isinstance(t, ast.Name)] == ["code"]
                    and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str)
                }
    return named


def test_every_code_the_source_names_is_in_the_vocabulary():
    named = _named_codes()
    assert named and named <= set(CODES), sorted(named - set(CODES))


def test_every_code_in_the_vocabulary_is_emitted_somewhere_in_the_source():
    import ast

    literals = set()
    for _path, tree in _source_trees():
        vocabulary = {
            id(inner) for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "CODES"
            for inner in ast.walk(node)
        }
        literals |= {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in vocabulary
        }
    assert [code for code in CODES if code not in literals] == []


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


def test_an_unreadable_run_document_is_refused_in_the_one_shape(tmp_path, capsys):
    from omnidriver.cli import main

    assert main(["run", "--plugin", "plugins.toy:ToyStack", "--run-document", str(tmp_path / "absent.json")]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert (payload["status"], payload["code"]) == ("failed", "run_document_unreadable")
    assert [item["code"] for item in payload["diagnostics"]] == ["run_document_unreadable"]


def test_a_diagnostic_with_detail_hashes():
    from omnidriver.core.planning_types import diagnostic

    assert hash(diagnostic("error", "c", "m", detail={"rule": {"minimum": 0}})) == hash(diagnostic("error", "c", "m"))
