"""The plugin declares its LAT reader and the record names the LAT format."""
from __future__ import annotations

from omnidriver.core.quantities import check_reader
from omnidriver.opencarp.lat_reader import LAT_FORMAT, LatPerNodeReader
from omnidriver.opencarp.plugin import OpenCARPPlugin
from omnidriver.opencarp.records.niederer_n_version import RECORD


def test_the_plugin_reads_its_lat_format_and_nothing_else():
    plugin = OpenCARPPlugin()
    assert isinstance(plugin.get_artifact_value_reader(LAT_FORMAT), LatPerNodeReader)
    assert plugin.get_artifact_value_reader("opencarp_par") is None
    check_reader(LatPerNodeReader(), artifact_format=LAT_FORMAT)


def test_the_record_names_the_lat_files_format():
    solve = {step.step_id: step for step in RECORD.workflow_steps}["solve"]
    assert solve.produced_format("out/init_acts_vm_act-thresh.dat") == LAT_FORMAT
    assert solve.produced_format("out/vm.igb") == "file"
