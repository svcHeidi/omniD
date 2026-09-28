"""cardiacCore's one semantic owner of a case mutation.

**S5 (2026-09-28):** this module used to also resolve the factory
workflows' own agent-requested ``input_overrides`` (a ``$SCOPE.leaf`` path
against ``catalogs/inputs.py``, dynamic ``<ventKey>``-style segments
included) into ``ParameterAssignment``s. That whole channel is gone with
the factory it served (``workflows/preprocessing.py``, deleted the same
step): a tutorial record addresses a document/key directly
(``tutorial_records.patches_to_parameters``, ``record_key_validation.py``),
never through a declared ``$SCOPE`` path. ``resolve_patch_mutation`` is the
one piece every case mutation -- factory or record alike -- always went
through underneath the addressing itself, so it is the only piece that
survives.
"""

from __future__ import annotations

from omnidriver.core.case_write import CaseMutationRequest, ResolvedMutation

#: This adapter's identity on every request and resolution it produces.
PLUGIN_ID = "org.omnidriver.cardiaccore"


def resolve_patch_mutation(request: CaseMutationRequest) -> ResolvedMutation:
    """The semantic owner's answer for a `clone_and_patch` request.

    Pure: every parameter this touches was already addressed (document,
    key_path, typed value) by whoever built the request -- a tutorial
    record's own ``patches_to_parameters``, since S5. This just repackages
    that addressing into a `ResolvedMutation`; it reads and writes nothing.

    `parameter.operation` is carried through (2026-09-23, "a parameter
    asserts a final state, not only a value") -- no cardiacCore caller
    builds an `ensure`/`remove` parameter today, so this is a
    correctness/symmetry change, not one any current caller exercises: it
    keeps this resolver's target shape identical to
    `cardiacfoam.overrides.resolve_patch_mutation`'s, which both feed the
    same shared renderer (`case_rendering.render_patch_case_files`). A
    `remove` target carries no `"value"` -- `parameter.value` is `None` for
    one, and there is nothing to write.
    """
    if request.mode != "clone_and_patch":
        raise ValueError(
            f"cardiacCore's overrides workflow resolves clone_and_patch "
            f"requests only, not {request.mode!r}"
        )
    targets = tuple(
        {
            "qualified_id": parameter.qualified_id,
            "document": parameter.document,
            "expanded_key_path": list(parameter.expanded_key_path()),
            "operation": parameter.operation,
            "format": "openfoam_dictionary",
            **({"value": parameter.value} if parameter.operation != "remove" else {}),
        }
        for parameter in request.parameters
    )
    expected_effects = tuple(
        f"{parameter.operation} {parameter.qualified_id!r} in {parameter.document}"
        for parameter in request.parameters
    )
    return ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=expected_effects, semantic_owner_id=PLUGIN_ID,
    )
