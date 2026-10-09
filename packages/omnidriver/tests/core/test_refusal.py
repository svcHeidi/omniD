"""Every refusal carries a stable code beside its text, and its structured refusals when it has them."""
from __future__ import annotations

import json

from omnidriver.core.refusal import Refusal, failure, print_refusal
from omnidriver.core.specs.paths import ScratchRootNotSupplied
from omnidriver.core.tutorial_records import TutorialRecordError


def test_a_refusal_names_its_own_code_else_its_class():
    assert failure(ScratchRootNotSupplied("no scratch"), action="plan") == {
        "status": "failed", "action": "plan", "code": "ScratchRootNotSupplied", "error": "no scratch",
    }
    assert failure(TutorialRecordError("broken", code="case_rule"))["code"] == "case_rule"
    assert failure(None, code="workflow_state_failed", error="rerun with step")["code"] == "workflow_state_failed"


def test_a_structured_refusal_keeps_its_refusals_beside_the_text():
    refusals = ({"code": "catalog_rule", "document": "d", "key": "k", "rule": {"minimum": 0}, "message": "m"},)
    payload = failure(TutorialRecordError("k is -1", code="catalog_rule", refusals=refusals))
    assert payload["refusals"] == list(refusals) and payload["error"] == "k is -1"


def test_print_refusal_prints_the_code(capsys):
    assert print_refusal(Refusal("bad flag")) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "code": "Refusal", "error": "bad flag"}
