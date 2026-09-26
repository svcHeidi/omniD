"""A resolution record must name the provider whose value was used.

`resolutions()` chose the most specific provider that *declared* a member.
Under the `single` rule the composed value comes from the most specific
provider that returned something other than `None`. A provider that declares a
hook and declines to answer was therefore recorded as the source of an answer
it did not give -- and that record is what `build_stack_identity` hashes and
what a reviewed plan cites as its responsible provider.

Corrected 2026-09-22: the plan this test file was written from
(`docs/superpowers/plans/2026-09-22-phase2-prerequisites.md`, Task 2 Step 2)
illustrated the resolutions()-level fix with `get_selected_start_time`, under
the assumed capability name `"selected_start_time"`. Neither holds: the real
capability name is `"case_introspection"` (`capability_members()`), and that
capability is not in `_DIGESTED_CAPABILITIES` -- so `resolutions()` never
actually calls `get_selected_start_time` to find out who answered; it still
records `implementers[-1]`, the declaring provider, exactly as before the fix.
`resolve_with_provenance` itself is unaffected (it does not care about
digestion), so the provenance-only tests below keep the plan's member choice.
The `resolutions()`-level test instead uses `"manifest"` / `get_capabilities`,
the one digested capability whose member is `single`-shaped
(`cxx_mapping` is `profile`-shaped, `dictionaries` is `sequence`-shaped).

Corrected 2026-09-26 (spec A2): the provenance-only tests used
`get_selected_start_time`, which left the contract; they use
`get_config_value_reader`, also `single`-shaped.
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
    """Two independent providers, both declining to answer.

    Corrected 2026-09-22: the plan's version of this fixture built
    `_AlsoDeclines` on top of `_Declines`, which inherits a `get_profile` that
    requires `org.base`. With only `_Declines` and `_AlsoDeclines` in the
    stack (no `org.base` provider present), `order_providers` raises
    "requires ['org.base'], which is not installed" before
    `resolve_with_provenance` is ever reached -- true of `order_providers`
    before Task 1's fix too, so this is a plan defect, not a consequence of
    C1's fix. Rebuilt here as two providers with no `requires:` of their own.
    """

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
    """`manifest` is the one digested capability whose member is `single`-shaped,
    so it is the one where `resolutions()` actually calls the hook and can
    report who truly answered, rather than who merely declared it."""
    ordered = provider_stack.order_providers([_Base(), _Declines()])
    recorded = provider_stack.resolutions(ordered)
    winner, _digest = recorded["manifest"]
    assert winner == "org.base"


def test_a_capability_no_provider_implements_is_recorded_as_unclaimed():
    """Recording the most specific provider as the winner of a capability
    nobody implements asserts an ownership that does not exist."""
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
