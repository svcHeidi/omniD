"""The contract must state each member's enforcement tier exactly once.

Before 2026-09-20 three sources disagreed: `_REQUIRED_PLUGIN_MEMBERS` named
27 members, the `SolverPlugin` Protocol body declared 29, and the capability
adapters probed 15 of the required ones with `getattr` anyway -- which made
nine `legacy_*` fallbacks unreachable while the generated seam table still
advertised them.
"""

import pytest

from omnidriver.core import capability_seams
from omnidriver.core import plugin_interface


def test_every_member_sits_in_exactly_one_tier():
    by_tier = capability_seams.members_by_tier()
    seen: dict[str, list[str]] = {}
    for tier, members in by_tier.items():
        for member in members:
            seen.setdefault(member, []).append(tier)
    duplicated = {m: t for m, t in seen.items() if len(t) > 1}
    assert duplicated == {}, f"members declared at more than one tier: {duplicated}"


@pytest.mark.xfail(
    reason="fixed by Task 3 (delete unreachable fallbacks) and Task 4 "
           "(derive _REQUIRED_PLUGIN_MEMBERS from tiers); see "
           "docs/superpowers/plans/2026-09-20-phase0-contract-coherence.md",
    strict=True,
)
def test_no_required_member_has_a_fallback():
    """A `required` member cannot be absent, so a fallback for it is dead code.

    This is the assertion that keeps `test_fallback_census` honest: a census
    of fallbacks that can never fire measures nothing.
    """
    from omnidriver.core import compatibility

    required = capability_seams.members_by_tier()["required"]
    offenders = sorted(
        name for name in required
        if hasattr(compatibility, f"legacy_{name.removeprefix('get_')}")
    )
    assert offenders == [], (
        "these members are required, so their fallbacks are unreachable: "
        f"{offenders}"
    )


@pytest.mark.xfail(
    reason="fixed by Task 3 (delete unreachable fallbacks) and Task 4 "
           "(derive _REQUIRED_PLUGIN_MEMBERS from tiers); see "
           "docs/superpowers/plans/2026-09-20-phase0-contract-coherence.md",
    strict=True,
)
def test_required_tier_matches_the_validator():
    """`_REQUIRED_PLUGIN_MEMBERS` must be derived from the tiers, not parallel."""
    required = capability_seams.members_by_tier()["required"]
    declared = set(plugin_interface._REQUIRED_PLUGIN_MEMBERS)
    identity_members = {
        "plugin_name", "plugin_id", "plugin_version", "plugin_api_version",
    }
    assert declared - identity_members == set(required), (
        "the validator's required set and the seam tiers disagree; "
        f"validator-only={sorted(declared - identity_members - set(required))} "
        f"tier-only={sorted(set(required) - declared)}"
    )
