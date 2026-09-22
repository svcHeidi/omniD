"""Composition order must not depend on string hashing.

`order_providers` fed `set(requires)` to `TopologicalSorter`, which registers a
node first seen as a predecessor in set-iteration order. With two or more
dependencies that order is `PYTHONHASHSEED`-dependent, so the same installation
composed differently between processes -- and `build_stack_identity` hashes this
order, so a reviewed plan's stack digest was not reproducible either.

An in-process test cannot see this: one process has one hash seed. The only
honest test spawns interpreters with different seeds.
"""

import subprocess
import sys
import textwrap

import pytest

from omnidriver.core import provider_stack

_PROBE = textwrap.dedent(
    """
    from omnidriver.core.provider_stack import order_providers


    class _Profile:
        def __init__(self, requires):
            self.requires = requires


    class _Provider:
        def __init__(self, plugin_id, requires=()):
            self.plugin_id = plugin_id
            self._requires = tuple(requires)

        def get_profile(self):
            return _Profile(self._requires)


    providers = [
        _Provider("org.top", ("org.x", "org.y", "org.z")),
        _Provider("org.x"),
        _Provider("org.y"),
        _Provider("org.z"),
    ]
    print(",".join(p.plugin_id for p in order_providers(providers)))
    """
)


def _order_under_seed(seed: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, check=True,
        env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
    )
    return result.stdout.strip()


def test_order_is_identical_across_hash_seeds():
    orders = {_order_under_seed(str(seed)) for seed in range(8)}
    assert len(orders) == 1, f"composition order varies with PYTHONHASHSEED: {orders}"


def test_independent_providers_keep_sorted_by_id_order():
    """The docstring's own promise, now actually enforced."""
    order = _order_under_seed("3")
    assert order == "org.x,org.y,org.z,org.top"


class _Profile:
    def __init__(self, requires=()):
        self.requires = tuple(requires)


class _Provider:
    def __init__(self, plugin_id, requires=()):
        self.plugin_id = plugin_id
        self._requires = tuple(requires)

    def get_profile(self):
        return _Profile(self._requires)


def test_a_duplicate_plugin_id_is_refused():
    """`by_id = {p.plugin_id: p for p in providers}` silently kept the last one.

    Two distributions claiming one identity is a packaging error: which object
    answers a capability then depends on discovery order, and the stack digest
    records an identity that does not identify one implementation.
    """
    with pytest.raises(ValueError, match="org.dup"):
        provider_stack.order_providers([
            _Provider("org.dup"), _Provider("org.other"), _Provider("org.dup"),
        ])
