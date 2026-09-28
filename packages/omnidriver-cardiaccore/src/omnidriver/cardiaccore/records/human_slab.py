"""``humanSlab``: mirrors ``cases/bivCase/Allrun``, using the native
tutorial's own name (no ``cardiaccore-*`` alias) and running the four
utilities in the native ``Allrun``'s own order. ``1DgraphToFoam`` is left
out: the factory workflow never ran it, and its edge-length scaling
remains unresolved.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .anatomy import ANATOMY, CONDUCTIVITY, CONV, ANATOMY_STEP, MORPHOMETRY, step

RECORD = TutorialRecord(
    name="humanSlab",
    native_case_relpath="cases/bivCase",
    inputs=(ANATOMY,),
    workflow_steps=(
        CONDUCTIVITY,
        ANATOMY_STEP,
        # `0/Conductivity` is CONDUCTIVITY's own `produces`, not an authored
        # input, so it is not re-declared as consumed: at plan time it does
        # not exist yet, and `record_execution.record_generated_relpaths`
        # excludes it from the native-case copy as a generated intermediate.
        step(
            "purkinje_slab", "setPurkinjeSlab",
            consumes=(CONV, "0/uvc_transmural"),
            produces=("0/PurkinjeLayer", "0/Conductivity"),
        ),
        MORPHOMETRY,
    ),
)
