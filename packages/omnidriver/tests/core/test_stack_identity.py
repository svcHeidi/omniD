"""The digest must distinguish stacks, not just plugins.

Two different stacks producing the same provenance record would make a run
irreproducible in exactly the way the digest exists to prevent.
"""

from omnidriver.core import provider_identity


def _pid(plugin_id, version="1.0", digest="d"):
    return provider_identity.ProviderIdentity(
        id=plugin_id, version=version, api_version="2",
        source="test", provider_digest=digest,
    )


def test_order_changes_the_digest():
    a, b = _pid("org.a"), _pid("org.b")
    first = provider_identity.build_stack_identity(
        providers=(a, b), resolutions={"x": ("org.b", "v")},
    )
    second = provider_identity.build_stack_identity(
        providers=(b, a), resolutions={"x": ("org.a", "v")},
    )
    assert first.capability_digest != second.capability_digest


def test_a_provider_that_wins_nothing_still_changes_the_digest():
    a = _pid("org.a")
    lone = provider_identity.build_stack_identity(
        providers=(a,), resolutions={"x": ("org.a", "v")},
    )
    with_loser = provider_identity.build_stack_identity(
        providers=(a, _pid("org.loser")), resolutions={"x": ("org.a", "v")},
    )
    assert lone.capability_digest != with_loser.capability_digest


def test_the_rule_version_changes_the_digest():
    a = _pid("org.a")
    args = dict(providers=(a,), resolutions={"x": ("org.a", "v")})
    assert (
        provider_identity.build_stack_identity(**args, composition_rule_version="1")
        .capability_digest
        != provider_identity.build_stack_identity(**args, composition_rule_version="2")
        .capability_digest
    )


def test_the_same_stack_is_stable():
    a, b = _pid("org.a"), _pid("org.b")
    args = dict(providers=(a, b), resolutions={"x": ("org.b", "v")})
    assert (
        provider_identity.build_stack_identity(**args).capability_digest
        == provider_identity.build_stack_identity(**args).capability_digest
    )


def test_to_json_names_who_answered_each_capability():
    a = _pid("org.a")
    identity = provider_identity.build_stack_identity(
        providers=(a,), resolutions={"dictionaries": ("org.a", "v")},
    )
    payload = identity.to_json()
    assert payload["resolutions"]["dictionaries"] == "org.a"
    assert [p["id"] for p in payload["providers"]] == ["org.a"]
