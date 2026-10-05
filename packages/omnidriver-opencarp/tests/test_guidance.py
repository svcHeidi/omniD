"""openCARP's guidance names the sampling rule its LAT reader declares."""
from __future__ import annotations

from omnidriver.opencarp.lat_reader import LAT_FORMAT, LatPerNodeReader
from omnidriver.opencarp.plugin import OpenCARPPlugin


def test_the_guidance_names_the_lat_readers_sampling_rule():
    text = "\n".join(item["text"] for item in OpenCARPPlugin().get_agent_guidance())
    assert LAT_FORMAT in text
    assert f"`{LatPerNodeReader.sampling_rule}`" in text
