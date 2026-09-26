"""cardiacFOAM's agent guidance (what ``describe``'s ``record_surface.guidance``
carries, conformance C10) states the owner's pre-processing rule.

Added 2026-09-26 (review 54b M11). The owner decided how every record gets
its starting state, "and the agent guidance says so" (plan §5g answered,
"The pre-processing stage"); the first three variant records landed with the
guidance unchanged, so an agent reading ``describe`` learnt nothing of the
``mesh`` selector, the default route, or how a study replaces a default
argument.
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
