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
    assert len(context.capabilities.dictionaries.entries()) == 10
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
    operation = catalogs["cardiaccore_operations"]["cardiaccore.cobiveco.normalize.v1"]
    assert operation["status"]["native_file_reader"] == "pending"
    assert "target_convention" in operation["inputs"]
    guidance = catalogs["cardiaccore_agent_guidance"]
    assert guidance["discovery"] == "plugin_named_catalogs"
    assert guidance["runner"].endswith("agent_guidance/runner.md")

    from omnidriver.cardiaccore.operations.cobiveco import normalize_cobiveco_coordinates as implementation
    assert callable(implementation)


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
