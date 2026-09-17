from __future__ import annotations

import json
import stat
from pathlib import Path

from omnidriver.cli import main
from omnidriver.core.plugin_interface import driver_context
from omnidriver.cardiaccore import CardiacCorePlugin


def test_plugin_has_a_valid_context() -> None:
    context = driver_context(CardiacCorePlugin(), source="test")

    assert context.identity.id == "org.omnidriver.cardiaccore"
    assert len(context.capabilities.dictionaries.entries()) == 87
    assert context.capabilities.dictionaries.phases() == ("preprocessing",)
    assert context.capabilities.tutorials.catalog()["registered_tutorials"] == (
        "cardiaccore-human-purkinje-slab",
        "cardiaccore-human-purkinje-endocardial",
        "cardiaccore-pig-morphometric-purkinje",
        "cardiaccore-pig-transmural-purkinje",
    )
    assert context.capabilities.case_runtime_conventions.conventions().case_entrypoints == ("Allrun",)


def test_plugin_exposes_agent_guidance_catalogs() -> None:
    catalogs = CardiacCorePlugin().get_named_catalogs()
    assert catalogs["cardiaccore_field_conventions"]["cobiveco_raw"]["tm"] == "0=epicardium, 1=endocardium"
    assert catalogs["cardiaccore_python_utilities"]["purkinje_seed_proposal"]["status"] == "supported_optional"
    assert catalogs["cardiaccore_operations"]["cardiaccore.purkinje.seed_proposal.v1"]["status"]["array_api"] == "available"
    conventions = catalogs["cardiaccore_field_conventions"]
    assert "coordinatesConventionDict" in conventions["authority"]
    assert set(conventions["coordinate_system_effects"]) == {"uvc", "cobiveco"}
    guidance = catalogs["cardiaccore_agent_guidance"]
    assert guidance["discovery"] == "plugin_named_catalogs"
    assert guidance["runner"].endswith("agent_guidance/runner.md")


def test_controlled_allrun_executes_without_domain_claims(tmp_path: Path, capsys) -> None:
    case_root = tmp_path / "controlled-case"
    case_root.mkdir()
    allrun = case_root / "Allrun"
    allrun.write_text("#!/bin/sh\nprintf generic-proof > generic-proof.txt\n")
    allrun.chmod(allrun.stat().st_mode | stat.S_IXUSR)

    result = main([
        "run", "--strict",
        "--plugin", "omnidriver.cardiaccore.plugin:CardiacCorePlugin",
        "--entry", "controlled-case",
        "--cases-root", str(tmp_path),
    ])

    assert result == 0
    assert (case_root / "generic-proof.txt").read_text() == "generic-proof"
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_declared_vocabulary_names_the_current_coordinates_dictionary() -> None:
    """No declared path may name the retired uvcConventionDict.

    Native cardiacCore renamed system/uvcConventionDict to
    system/coordinatesConventionDict; generatePurkinjeTree.C reads the new
    name. A declared consumes list still naming the old one sends an agent to
    a file no case has. Historical notes in source comments are exempt: this
    checks declared paths, not prose.
    """
    plugin = CardiacCorePlugin()
    catalogs = plugin.get_named_catalogs()
    declared = json.dumps(catalogs)

    assert "uvcConventionDict" not in declared
    assert "system/coordinatesConventionDict" in declared

    factories = driver_context(plugin, source="test").capabilities.tutorials.catalog()[
        "spec_factories"
    ]
    specs = {name: json.dumps(build(), default=str) for name, build in factories.items()}
    for name, spec in specs.items():
        assert "uvcConventionDict" not in spec, name
    # Only the tutorials that run generatePurkinjeTree consume the convention
    # dictionary; the slab tutorial reaches the endocardium another way. At
    # least one must name it, or this gate would pass on a typo.
    assert any("system/coordinatesConventionDict" in spec for spec in specs.values())


def test_declared_tree_extension_targets_are_wall_thickness_depths() -> None:
    """generatePurkinjeTree takes depthMin/depthMax, bounded to [0, 1].

    cardiacCore 1ea6d23 replaced extension.dMin/dMax, which were raw
    transmural values and so named a different physical place under each
    coordinate system, with a depth fraction measured from the endocardium.
    """
    entries = {
        e.driver_path: e
        for e in driver_context(CardiacCorePlugin(), source="test")
        .capabilities.dictionaries.entries()
    }
    assert "$PURKINJE_TREE.<ventKey>.extension.dMin" not in entries
    assert "$PURKINJE_TREE.<ventKey>.extension.dMax" not in entries

    for bound in ("depthMin", "depthMax"):
        entry = entries[f"$PURKINJE_TREE.<ventKey>.extension.{bound}"]
        joined = " ".join(entry.constraints) + " " + (entry.notes or "")
        assert "transmuralLowerValue" not in joined, bound
        assert "0 <= depthMin <= depthMax <= 1" in joined, bound
