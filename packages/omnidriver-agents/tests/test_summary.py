import json

from omnidriver_agents.summary import summarize


def test_one_row_per_task_adapter_condition(tmp_path):
    for i, (ok, s) in enumerate([(True, 10), (False, 30), (True, 20)]):
        folder = tmp_path / "t/fake/omnid" / str(i)
        folder.mkdir(parents=True)
        (folder / "task_record.json").write_text(json.dumps({
            "task": "t", "adapter": "fake", "condition": "omnid", "success": ok, "seconds": s, "turns": 2,
            "cost_usd": 0.5, "launches": 1, "refusals": 0, "tree_before": "a", "tree_after": "a"}))
    [row] = summarize(tmp_path)
    assert (row["trials"], row["successes"], row["median_seconds"], row["cost_usd"]) == (3, 2, 20, 1.5)
    assert row["tree_changed"] == 0
