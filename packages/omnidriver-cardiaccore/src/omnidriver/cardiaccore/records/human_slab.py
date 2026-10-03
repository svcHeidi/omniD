"""``humanSlab``, mirroring ``cases/bivCase/Allrun``: the four utilities in the native order, on a supplied anatomy bundle."""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .anatomy import ANATOMY, CONDUCTIVITY, CONV, ANATOMY_STEP, MORPHOMETRY, step

# `1DgraphToFoam` is not a step: its edge-length scaling is unresolved.
RECORD = TutorialRecord(
    name="humanSlab",
    native_case_relpath="cases/bivCase",
    inputs=(ANATOMY,),
    workflow_steps=(
        CONDUCTIVITY,
        ANATOMY_STEP,
        # `0/Conductivity` is CONDUCTIVITY's own `produces`, not an authored
        # input, so it is not re-declared as consumed: it does not exist at
        # plan time and is excluded from the native-case copy.
        step(
            "purkinje_slab", "setPurkinjeSlab",
            consumes=(CONV, "0/uvc_transmural"),
            produces=("0/PurkinjeLayer", "0/Conductivity"),
        ),
        MORPHOMETRY,
    ),
)
