"""``humanSlab``: mirrors ``cases/bivCase/Allrun`` (design §1.3).

The native tutorial's own name (D6, no ``cardiaccore-*`` alias): four
utilities in series, exactly the order the native ``Allrun`` runs them.
``1DgraphToFoam`` is left out (D4, owner decision): the factory workflow
never ran it, and the edge-length scaling it needs is a separate open
question.
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
        # `0/Conductivity` is not re-declared as consumed here (only as
        # produced, rewritten in place): it is CONDUCTIVITY's own `produces`,
        # not an authored input -- the same convention cardiacFOAM's
        # restitutionCurves solve step already established ("the solve
        # step's mesh comes from the mesh step's produces, so it is not
        # re-declared as consumed"). Declaring it here made C8 (every
        # consumed file fingerprinted) fail: at plan time, before any step
        # has run, it genuinely does not exist yet, and staging excludes it
        # from the native-case copy as a generated intermediate
        # (`record_execution.record_generated_relpaths`) -- found running
        # this record for real (S3).
        step(
            "purkinje_slab", "setPurkinjeSlab",
            consumes=(CONV, "0/uvc_transmural"),
            produces=("0/PurkinjeLayer", "0/Conductivity"),
        ),
        MORPHOMETRY,
    ),
)
