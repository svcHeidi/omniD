import json

from omnidriver_agents.summary import summarize


def _record(folder, **over):
    folder.mkdir(parents=True)
    record = {"task": "t", "adapter": "fake", "condition": "omnid", "success": True, "seconds": 10, "turns": 2,
              "cost_usd": 0.5, "launches": 1, "refusals": 0, "tree_before": "a", "tree_after": "a",
              "timed_out": False, "oracle": {"status": "passed"}, "harness_error": None}
    (folder / "task_record.json").write_text(json.dumps({**record, **over}))


def test_one_row_per_task_adapter_condition(tmp_path):
    for i, (ok, s) in enumerate([(True, 10), (False, 30), (True, 20)]):
        _record(tmp_path / f"opaque{i}", success=ok, seconds=s)
    [row] = summarize(tmp_path)
    assert (row["trials"], row["successes"], row["median_seconds"], row["cost_usd"]) == (3, 2, 20, 1.5)
    assert row["tree_changed"] == 0


def test_unknown_costs_timeouts_and_errors_are_counted(tmp_path):
    _record(tmp_path / "a")
    _record(tmp_path / "b", cost_usd=None, timed_out=True)
    _record(tmp_path / "c", oracle={"oracle_error": "x"}, success=False)
    _record(tmp_path / "d", harness_error="boom", success=False)
    [row] = summarize(tmp_path)
    assert (row["cost_usd"], row["cost_unknown"]) == (1.5, 1)
    assert (row["timeouts"], row["oracle_errors"], row["harness_errors"]) == (1, 1, 1)
