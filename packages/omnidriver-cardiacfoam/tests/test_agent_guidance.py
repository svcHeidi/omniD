"""cardiacFOAM's agent guidance (``describe``'s ``record_surface.guidance``,
conformance C10) states the pre-processing rule: the ``mesh`` selector, the
default route, and how a study replaces a default argument.
"""
from __future__ import annotations

from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.records import TUTORIAL_RECORDS


def _guidance_text() -> str:
    return "\n".join(item["text"] for item in CardiacFoamPlugin().get_agent_guidance())


def test_the_guidance_states_the_pre_processing_rule():
    text = _guidance_text()
    for phrase in (
        "pre-processing stage", "generated", "supplied", "blockMesh", "gmsh",
        "DefineConstant", "default route", "workflow_variant", "workflow_commands",
        "regression/regressionTest.sh", "replaces the default", "refused by name",
    ):
        assert phrase in text, phrase


def test_the_guidance_names_every_records_route_selector():
    text = _guidance_text()
    for record in TUTORIAL_RECORDS.values():
        if record.variant_selector is not None:
            assert f'"{record.variant_selector}"' in text, record.name
