from __future__ import annotations

import json
import stat
from pathlib import Path

from omnidriver.cli import main
from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiaccore import CardiacCorePlugin


def test_plugin_has_a_valid_context() -> None:
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")

    # `.identity` is a `StackIdentity`: the most-specific provider (last in
    # the ordered stack) is this plugin, per
    # `identity.to_json()["providers"][-1]["id"]`.
    assert context.identity.to_json()["providers"][-1]["id"] == "org.omnidriver.cardiaccore"
    assert len(context.stack.call("get_dict_entries")) == 52  # includes rvLocalBands
    assert set(context.stack.call("get_tutorial_records")) == {
        "humanSlab", "idealizedHeart", "idealizedHeartEndocardial", "idealizedHeartPigTransmural",
    }
    assert context.stack.call("get_case_runtime_conventions").case_entrypoints == ("Allrun",)


def test_a_case_gets_the_openfoam_layers_documentation_and_regression_rules() -> None:
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")

    roles = {rule.role: rule.path for rule in context.stack.call("get_profile").case_files}
    assert roles["case.documentation"] == "README.md"
    assert roles["case.regression_test"] == "regression/regressionTest.sh"


def test_plugin_exposes_named_catalogs() -> None:
    catalogs = CardiacCorePlugin().get_named_catalogs()
    assert catalogs["cardiaccore_field_conventions"]["cobiveco_raw"]["tm"] == "0=epicardium, 1=endocardium"
    conventions = catalogs["cardiaccore_field_conventions"]
    assert "coordinatesConventionDict" in conventions["authority"]
    assert set(conventions["coordinate_system_effects"]) == {"uvc", "cobiveco"}


def test_controlled_allrun_executes_without_domain_claims(tmp_path: Path, capsys) -> None:
    case_root = tmp_path / "cases" / "controlled-case"
    case_root.mkdir(parents=True)
    allrun = case_root / "Allrun"
    allrun.write_text("#!/bin/sh\nprintf generic-proof > generic-proof.txt\n")
    allrun.chmod(allrun.stat().st_mode | stat.S_IXUSR)

    result = main([
        "run", "--strict",
        "--plugin", "omnidriver.cardiaccore.plugin:CardiacCorePlugin",
        "--case", str(case_root),
        "--scratch-dir", str(tmp_path / "scratch"),
    ])

    assert result == 0
    staged = tmp_path / "scratch" / "records" / "controlled-case"
    assert (staged / "generic-proof.txt").read_text() == "generic-proof"
    assert not (case_root / "generic-proof.txt").exists()
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_declared_vocabulary_names_the_current_coordinates_dictionary() -> None:
    """``generatePurkinjeTree.C`` reads ``system/coordinatesConventionDict``; a
    declared ``consumes`` list naming ``system/uvcConventionDict`` sends an
    agent nowhere. Only declared paths are checked, not prose in comments."""
    plugin = CardiacCorePlugin()
    catalogs = plugin.get_named_catalogs()
    declared = json.dumps(catalogs)

    assert "uvcConventionDict" not in declared
    assert "system/coordinatesConventionDict" in declared

    # Every record's own `consumes` is the source of truth here: tutorial
    # records are inert data, so no plugin code runs to inspect them.
    records = driver_context(
        OpenFOAMEnvironmentPlugin(), plugin, source="test",
    ).stack.call("get_tutorial_records")
    consumed = {
        path
        for record in records.values()
        for step in record.workflow_steps
        for path in step.consumes
    }
    assert "uvcConventionDict" not in json.dumps(sorted(consumed))
    # Only a record that runs generatePurkinjeTree/setPurkinjeSlab/
    # setPurkinjeMorphometry consumes the convention dictionary; at least
    # one must name it, or this gate would pass on a typo.
    assert "system/coordinatesConventionDict" in consumed


def test_declared_tree_extension_targets_are_wall_thickness_depths() -> None:
    """generatePurkinjeTree takes depthMin/depthMax, bounded to [0, 1]: a
    depth fraction measured from the endocardium, replacing raw transmural
    values that named a different physical place under each coordinate
    system."""
    entries = {
        e.driver_path: e
        for e in driver_context(
            OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test",
        )
        .stack.call("get_dict_entries")
    }
    assert "$PURKINJE_TREE.<ventKey>.extension.dMin" not in entries
    assert "$PURKINJE_TREE.<ventKey>.extension.dMax" not in entries

    for bound in ("depthMin", "depthMax"):
        entry = entries[f"$PURKINJE_TREE.<ventKey>.extension.{bound}"]
        joined = " ".join(entry.constraints) + " " + (entry.notes or "")
        assert "transmuralLowerValue" not in joined, bound
        assert "0 <= depthMin <= depthMax <= 1" in joined, bound


def test_every_ventkey_entry_declares_its_allowed_bindings() -> None:
    """Every ``<ventKey>`` entry must declare `allowed_bindings` from
    `VENT_KEYS = ("lv", "rv")`, which sits immediately above `TREE_ENTRIES`
    with a comment marking the domain closed -- so a placeholder can never
    silently accept an arbitrary binding (e.g. "banana" as a ventricle)."""
    from omnidriver.cardiaccore.catalogs.inputs import VENT_KEYS

    entries = list(
        driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")
        .stack.call("get_dict_entries")
    )
    vent_key_entries = [e for e in entries if "<ventKey>" in e.driver_path]
    assert len(vent_key_entries) == 21, len(vent_key_entries)
    for entry in vent_key_entries:
        assert entry.allowed_bindings.get("<ventKey>") == tuple(VENT_KEYS), entry.driver_path


def test_every_dynamic_entry_declares_a_domain_for_every_placeholder() -> None:
    """Generalises `test_every_ventkey_entry_declares_its_allowed_bindings`
    to every placeholder of every `dynamic_path` entry, not just
    `<ventKey>`: `DictEntry.__post_init__` refuses a *partial* declaration
    but not a wholly absent one (an entry with no dynamic segment is
    legitimate), so this asserts the catalog-wide property that every
    placeholder names a domain, closed (a tuple) or explicitly open
    (`None`)."""
    import re

    placeholder_re = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>")
    entries = list(
        driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")
        .stack.call("get_dict_entries")
    )
    dynamic = [e for e in entries if e.dynamic_path]
    assert dynamic, "the catalog declares no dynamic_path entry at all"
    undeclared = sorted(
        f"{entry.driver_path} {placeholder}"
        for entry in dynamic
        for placeholder in placeholder_re.findall(entry.driver_path)
        if placeholder not in entry.allowed_bindings
    )
    assert undeclared == [], undeclared


def test_every_record_declares_how_omnidriver_check_exercises_it() -> None:
    from omnidriver.cardiaccore.records import TUTORIAL_RECORDS

    assert all(record.conformance is not None for record in TUTORIAL_RECORDS.values())
