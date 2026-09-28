"""A resolution record must name the provider whose value was used, not merely the one that declared the hook.

Under the `single` rule, the composed value comes from the most specific
provider that returned something other than `None`.
"""

from omnidriver.core import provider_stack


class _Profile:
    def __init__(self, requires=()):
        self.requires = tuple(requires)
        self.case_files = ()


class _Base:
    plugin_id = "org.base"

    def get_profile(self):
        return _Profile()

    def get_config_value_reader(self, *args, **kwargs):
        return "0"

    def get_capabilities(self):
        return {"origin": "org.base"}


class _Declines(_Base):
    plugin_id = "org.declines"

    def get_profile(self):
        return _Profile(requires=("org.base",))

    def get_config_value_reader(self, *args, **kwargs):
        return None

    def get_capabilities(self):
        return None


def test_the_provider_that_returned_none_is_not_recorded_as_the_winner():
    ordered = provider_stack.order_providers([_Base(), _Declines()])
    value, provider_id = provider_stack.resolve_with_provenance(
        ordered, "get_config_value_reader",
    )
    assert value == "0"
    assert provider_id == "org.base"


def test_no_implementer_answering_reports_no_provider():
    """Two independent providers, both declining to answer, with no `requires:` between them."""

    class _DeclinesA(_Base):
        plugin_id = "org.declines_a"

        def get_profile(self):
            return _Profile()

        def get_config_value_reader(self, *args, **kwargs):
            return None

    class _DeclinesB(_Base):
        plugin_id = "org.declines_b"

        def get_profile(self):
            return _Profile()

        def get_config_value_reader(self, *args, **kwargs):
            return None

    ordered = provider_stack.order_providers([_DeclinesA(), _DeclinesB()])
    value, provider_id = provider_stack.resolve_with_provenance(
        ordered, "get_config_value_reader",
    )
    assert value is None
    assert provider_id is None


def test_resolutions_records_the_answering_provider_for_a_digested_single_member():
    """`manifest` is the one digested capability whose member is `single`-shaped, so it is the one where `resolutions()` actually calls the hook and can report who truly answered, rather than who merely declared it."""
    ordered = provider_stack.order_providers([_Base(), _Declines()])
    recorded = provider_stack.resolutions(ordered)
    winner, _digest = recorded["manifest"]
    assert winner == "org.base"


def test_a_capability_no_provider_implements_is_recorded_as_unclaimed():
    """Recording the most specific provider as the winner of a capability nobody implements asserts an ownership that does not exist."""
    ordered = provider_stack.order_providers([_Base()])
    recorded = provider_stack.resolutions(ordered)
    for capability, (winner, _digest) in recorded.items():
        implementers = [
            provider for provider in ordered
            if any(
                callable(getattr(provider, member, None))
                for member in provider_stack.capability_members()[capability]
            )
        ]
        if not implementers:
            assert winner == provider_stack.UNCLAIMED, capability
