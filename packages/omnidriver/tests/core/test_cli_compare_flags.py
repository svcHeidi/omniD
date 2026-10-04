"""``compare`` takes exactly its own two flags: a request names its own plugin and sweep per run, and it is a one-shot report call."""
from __future__ import annotations

import pytest

from omnidriver.cli import main
from cli_refusal import refusal


def test_compare_requires_both_flags(capsys):
    for argv in (["compare", "--comparison-request", "r.json"], ["compare", "--report", "o.json"], ["compare"]):
        assert "requires --comparison-request and --report" in refusal(capsys, argv)


@pytest.mark.parametrize("flag_and_value", [
    ("--entry", "x"), ("--run-document", "doc.json"), ("--cases-root", "."),
    ("--spec", "s.json"), ("--output-dir", "out"), ("--plugin", "plugins.toy:QuantityToyPlugin"),
    ("--scratch-dir", "scratch"),
])
def test_compare_refuses_plan_run_sweep_flags(flag_and_value, capsys):
    flag, value = flag_and_value
    refusal(capsys, ["compare", "--comparison-request", "r.json", "--report", "o.json", flag, value])


def test_comparison_request_and_report_flags_are_refused_outside_compare(capsys):
    for flag, value in (("--comparison-request", "r.json"), ("--report", "o.json")):
        assert "only valid with action=compare" in refusal(capsys, ["plan", "--entry", "x", flag, value])
