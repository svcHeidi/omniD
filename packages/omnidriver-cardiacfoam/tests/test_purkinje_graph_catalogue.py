"""The Purkinje graph document catalogues the keys ``conductionGraph::readFromDict`` reads (fixture: the native header, verbatim)."""

from __future__ import annotations

from pathlib import Path

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.openfoam.dict_keys_scanner import catalog_report, scan_source

_HEADER = Path(__file__).parent / "fixtures" / "cxx" / "conductionGraph.H"
_GRAPH_KEYS = {"conductionEdges", "pvjResistances"}


def test_every_key_the_graph_reader_reads_is_catalogued(tmp_path):
    source = tmp_path / "src" / "electroModels" / "electroDomains" / "conductionSystemDomain"
    source.mkdir(parents=True)
    (source / "conductionGraph.H").write_text(_HEADER.read_text())
    assert _GRAPH_KEYS <= {read.key for read in scan_source(tmp_path / "src").reads}
    report = catalog_report(
        tmp_path / "src", allowlist_path=CardiacFoamPlugin.get_profile().cxx_mapping.allowlist_path,
        catalogue=CardiacFoamPlugin.get_dictionary_catalog(),
    )
    assert [item for item in report.uncatalogued if item.get("key") in _GRAPH_KEYS] == []
    assert not [line for line in report.disagreements if line.split(":")[0] in _GRAPH_KEYS]
