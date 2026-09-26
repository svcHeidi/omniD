"""``compare`` takes exactly its own two flags: a comparison request names
its own plugin and sweep per run, so none of plan/run/sweep's flags apply,
and it is a one-shot report call, so --dry-run/--continue-on-error make no
sense either (N4, controller review 2026-09-26)."""
from __future__ import annotations

import pytest

from omnidriver.cli import main


def test_compare_requires_both_flags():
    with pytest.raises(SystemExit):
        main(["compare", "--comparison-request", "r.json"])
    with pytest.raises(SystemExit):
        main(["compare", "--report", "o.json"])
    with pytest.raises(SystemExit):
        main(["compare"])


@pytest.mark.parametrize("flag_and_value", [
    ("--entry", "x"), ("--run-document", "doc.json"), ("--config", "c.json"), ("--cases-root", "."),
    ("--spec", "s.json"), ("--output-dir", "out"), ("--plugin", "plugins.quantity_toy:QuantityToyPlugin"),
    ("--scratch-dir", "scratch"),
])
def test_compare_refuses_plan_run_sweep_flags(flag_and_value):
    flag, value = flag_and_value
    with pytest.raises(SystemExit):
        main(["compare", "--comparison-request", "r.json", "--report", "o.json", flag, value])


def test_compare_refuses_dry_run():
    with pytest.raises(SystemExit):
        main(["compare", "--comparison-request", "r.json", "--report", "o.json", "--dry-run"])


def test_compare_refuses_continue_on_error():
    with pytest.raises(SystemExit):
        main(["compare", "--comparison-request", "r.json", "--report", "o.json", "--continue-on-error"])


def test_comparison_request_and_report_flags_are_refused_outside_compare():
    with pytest.raises(SystemExit):
        main(["plan", "--entry", "x", "--comparison-request", "r.json"])
    with pytest.raises(SystemExit):
        main(["plan", "--entry", "x", "--report", "o.json"])
