from omnidriver.cardiacfoam.records.manufactured_monodomain_1d3d import RECORD


def test_the_solve_steps_consume_only_the_numbered_graph_files():
    graph_paths = {
        path
        for step in RECORD.workflow_steps
        for path in step.consumes
        if path.startswith("constant/purkinjeGraph")
    }
    assert graph_paths == {
        f"constant/purkinjeGraph.nodes{k:03d}" for k in (3, 11, 21, 41, 81, 161)
    }
