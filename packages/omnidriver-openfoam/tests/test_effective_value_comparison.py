"""A requested value and its native resolution are compared as values.

`1e-3` written into a dictionary resolves through `foamDictionary` as `0.001`.
Compared as text those differ, so the post-write check reported a mismatch for a
correct edit. Compared as numbers they agree.

This must not become a tolerance. `0.001` and `0.0010000001` are different
configurations and a check that hides that is worse than no check. Equality of
the parsed value, exactly -- nothing looser.
"""

import pytest

from omnidriver.openfoam.apply_overrides import effective_values_agree


@pytest.mark.parametrize("requested,resolved", [
    (1e-3, "0.001"),
    (0.001, "1e-3"),
    (1, "1"),
    (1, "1.0"),
    (-2.5e-4, "-0.00025"),
    ("TT06", "TT06"),
    (True, "true"),
    (False, "false"),
    ([1, 2, 3], "(1 2 3)"),
    ("(1 2 3)", "(1 2 3)"),
    # 2026-09-25: the blockMeshDict hex-cell-counts convention spells its
    # triple WITHOUT parentheses (`case_planning.read_hex_cell_counts`/
    # `plan_block_mesh_resolution`) -- a requested tuple must still agree
    # with that unparenthesised text.
    ((40, 6, 14), "40 6 14"),
    ("40 6 14", "40 6 14"),
])
def test_equal_values_agree(requested, resolved):
    assert effective_values_agree(requested, resolved)


@pytest.mark.parametrize("requested,resolved", [
    (0.001, "0.0010000001"),
    (1e-3, "0.002"),
    ("TT06", "TT04"),
    (1, "2"),
    ([1, 2, 3], "(1 2 4)"),
    (1e-3, "uniform 0.001"),
    ((40, 6, 14), "40 6 15"),
])
def test_different_values_do_not_agree(requested, resolved):
    assert not effective_values_agree(requested, resolved)


def test_an_unparseable_resolution_does_not_agree_silently():
    """Unknown is not agreement. A resolution the comparison cannot read must
    be reported as a non-match, so the caller sees an unverified edit rather
    than a passed check."""
    assert not effective_values_agree(1e-3, None)
    assert not effective_values_agree(1e-3, "")
