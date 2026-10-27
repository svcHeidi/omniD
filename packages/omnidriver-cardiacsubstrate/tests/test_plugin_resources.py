"""The utility manifests and the guidance are package data, read without a source checkout."""

from pathlib import Path

from omnidriver.cardiacsubstrate import CardiacSubstratePlugin
from omnidriver.cardiacsubstrate import plugin as plugin_module
from omnidriver.core.plugin_interface import load_plugin_context


def test_utility_manifests_load_from_the_declared_root() -> None:
    plugin = CardiacSubstratePlugin()
    manifests = plugin.get_utility_manifests()
    root = Path(plugin_module.__file__).parent / "utilities"

    assert load_plugin_context("cardiacsubstrate").stack.call("get_auxiliary_commands") == frozenset(manifests)
    assert {"setCardiacConductivity", "generatePurkinjeTree", "refine1Dgraph"} <= set(manifests)
    assert all(manifest.source_path.is_relative_to(root) for manifest in manifests.values())


def test_a_caller_cannot_reach_the_shared_manifest_cache() -> None:
    plugin = CardiacSubstratePlugin()
    plugin.get_utility_manifests().clear()

    assert plugin.get_utility_manifests()


def test_generated_output_globs_come_from_the_manifests() -> None:
    globs = CardiacSubstratePlugin().get_generated_output_globs(None, {})

    assert "0/Conductivity" in globs
    assert "constant/polyMesh/sets/LVEndoFaces" in globs


def test_guidance_is_read_from_the_package() -> None:
    (item,) = CardiacSubstratePlugin().get_agent_guidance()

    assert item["title"]
    assert "idealizedHeart/mesh" in item["text"]
    assert "system/<utility>Dict:<dotted.key>" in item["text"]
