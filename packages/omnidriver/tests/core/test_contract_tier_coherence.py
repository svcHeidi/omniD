"""The contract must state each member's enforcement tier exactly once."""

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


def test_no_required_member_has_a_fallback():
    """A `required` member cannot be absent, so a fallback for it is dead code."""
    from omnidriver.core import compatibility

    required = capability_seams.members_by_tier()["required"]
    offenders = sorted(
        name for name in required
        if hasattr(compatibility, f"absent_{name.removeprefix('get_')}")
    )
    assert offenders == [], (
        "these members are required, so their fallbacks are unreachable: "
        f"{offenders}"
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
