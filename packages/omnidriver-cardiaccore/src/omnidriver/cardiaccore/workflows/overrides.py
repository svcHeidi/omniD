"""cardiacCore's one semantic owner of a case mutation.

A tutorial record addresses a document/key directly
(``tutorial_records.patches_to_parameters``, ``record_key_validation.py``),
never through a declared ``$SCOPE`` path; ``resolve_patch_mutation`` is the
one piece every case mutation goes through underneath that addressing.
"""

from __future__ import annotations

from omnidriver.core.case_write import CaseMutationRequest, ResolvedMutation

#: This adapter's identity on every request and resolution it produces.
PLUGIN_ID = "org.omnidriver.cardiaccore"


def resolve_patch_mutation(request: CaseMutationRequest) -> ResolvedMutation:
    """The semantic owner's answer for a `clone_and_patch` request.

    Pure: every parameter was already addressed (document, key_path, typed
    value) by the request's builder -- a tutorial record's own
    `patches_to_parameters`. This just repackages that addressing into a
    `ResolvedMutation`; it reads and writes nothing.

    `parameter.operation` is carried through so this resolver's target shape
    stays identical to `cardiacfoam.overrides.resolve_patch_mutation`'s: both
    feed the same shared renderer (`case_rendering.render_patch_case_files`).
    A `remove` target carries no `"value"` (`parameter.value` is `None`).
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
