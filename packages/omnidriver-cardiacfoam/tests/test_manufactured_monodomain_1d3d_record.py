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


def _derive(name, stated, root):
    (derivation,) = [derivation for derivation in RECORD.derivations if derivation.name == name]
    return {patch.slot(): patch.value for patch in derivation.derive(stated, root)}


def test_numbercells_takes_the_graph_allrun_minus_n_takes(tmp_path):
    """``Allrun -N 10`` with no ``-graph`` runs ``purkinjeGraph.nodes011``, the graph whose edge length is 1/N."""
    import pytest
    from omnidriver.core.tutorial_records import TutorialRecordError

    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "purkinjeGraph.nodes011").write_text("")
    slot = (
        "constant/electroProperties::monodomainSolverCoeffs.conductionNetworkDomains.purkinjeNetwork"
        ".purkinjeGraphModelCoeffs.graphFile"
    )
    assert _derive("allrunGraph", {"numberCells": 10}, tmp_path) == {slot: "purkinjeGraph.nodes011"}
    assert _derive("allrunGraph", {"numberCells": 10, "graphFile": "purkinjeGraph.nodes021"}, tmp_path) == {}
    assert _derive("allrunGraph", {}, tmp_path) == {}
    with pytest.raises(TutorialRecordError, match="purkinjeGraph.nodes008"):
        _derive("allrunGraph", {"numberCells": 7}, tmp_path)
