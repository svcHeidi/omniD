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
    assert len(context.capabilities.dictionaries.entries()) == 88  # includes rvLocalBands
    assert context.capabilities.dictionaries.phases() == ("preprocessing",)
    assert set(context.capabilities.tutorial_records.catalog()) == {
        "humanSlab", "idealizedHeart", "idealizedHeartEndocardial", "idealizedHeartPigTransmural",
    }
    assert context.capabilities.case_runtime_conventions.conventions().case_entrypoints == ("Allrun",)


def test_plugin_exposes_agent_guidance_catalogs() -> None:
    catalogs = CardiacCorePlugin().get_named_catalogs()
    assert catalogs["cardiaccore_field_conventions"]["cobiveco_raw"]["tm"] == "0=epicardium, 1=endocardium"
    assert catalogs["cardiaccore_python_utilities"]["purkinje_coverage"]["status"] == "supported_array_method"
    assert catalogs["cardiaccore_operations"]["cardiaccore.purkinje.coverage_observation.v1"]["status"]["array_api"] == "available"
    conventions = catalogs["cardiaccore_field_conventions"]
    assert "coordinatesConventionDict" in conventions["authority"]
    assert set(conventions["coordinate_system_effects"]) == {"uvc", "cobiveco"}
    guidance = catalogs["cardiaccore_agent_guidance"]
    assert guidance["discovery"] == "plugin_named_catalogs"
    assert guidance["runner"].endswith("agent_guidance/runner.md")


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
    """Native cardiacCore renamed ``system/uvcConventionDict`` to
    ``system/coordinatesConventionDict``, which ``generatePurkinjeTree.C``
    reads; a declared ``consumes`` list still naming the old file sends an
    agent nowhere. Historical prose in source comments is exempt -- this
    checks declared paths only."""
    plugin = CardiacCorePlugin()
    catalogs = plugin.get_named_catalogs()
    declared = json.dumps(catalogs)

    assert "uvcConventionDict" not in declared
    assert "system/coordinatesConventionDict" in declared

    # Every record's own `consumes` is the source of truth here: tutorial
    # records are inert data, so no plugin code runs to inspect them.
    records = driver_context(
        OpenFOAMEnvironmentPlugin(), plugin, source="test",
    ).capabilities.tutorial_records.catalog()
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
        .capabilities.dictionaries.entries()
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
        .capabilities.dictionaries.entries()
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
        .capabilities.dictionaries.entries()
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


def test_the_region_id_domain_is_declared_open_on_evidence() -> None:
    """`<region_id>` is an *integer label*, not a case-author-chosen word:
    `setPurkinjeScar.C`'s `policyForRegion` looks the sub-block up by
    `Foam::name(region)`, where `region` is a `label` read from the
    `regionField` (`ScarRegionID`) volScalarField -- so the key is the
    decimal spelling of whatever integer that field carries, and the
    README shows `regions { 3 { ... } }`. That is an unbounded set, so the
    domain is declared open (`None`) rather than a closed tuple, and the
    evidence for it is cited in the entries' own constraints."""
    entries = {
        e.driver_path: e
        for e in driver_context(
            OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test",
        ).capabilities.dictionaries.entries()
    }
    region_entries = [
        entry for path, entry in entries.items()
        if path.startswith("$PURKINJE_SCAR.regions.<region_id>.")
    ]
    assert len(region_entries) == 4, sorted(e.driver_path for e in region_entries)
    for entry in region_entries:
        assert entry.allowed_bindings == {"<region_id>": None}, entry.driver_path
        joined = " ".join(entry.constraints) + " " + (entry.notes or "")
        assert "ScarRegionID" in joined, entry.driver_path
        # The evidence is not on main: `setPurkinjeScar/` and
        # `setCardiacScar/` exist only on `origin/scar`, and main's
        # `src/Allwmake` builds neither. A `source_refs` path that reads as
        # mainline but only resolves on an unmerged branch is a citation
        # that cannot be checked, so the branch must be named where the
        # claim is made.
        assert "scar" in joined and "branch" in joined, entry.driver_path


def test_every_scar_source_ref_names_the_branch_it_resolves_on() -> None:
    """A citation an agent cannot check is worse than no citation:
    `src/setCardiacScar/` and `src/setPurkinjeScar/` exist only on the
    `scar` branch, not on cardiacCore's main, and main's `src/Allwmake`
    builds neither. Written as bare paths these read as mainline -- the
    same shape as every other `source_refs` entry in this module -- so an
    agent following one finds nothing and cannot tell whether the catalog
    is wrong or its checkout is.

    The sibling package has a real drift guard for this class
    (`omnidriver-cardiacfoam/tests/test_source_refs_exist.py`, resolving
    every ref against the native tree); this is the narrower check: not
    "does the file exist" but "does the citation say where to look"."""
    entries = list(
        driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")
        .capabilities.dictionaries.entries()
    )
    scar_dirs = ("setCardiacScar/", "setPurkinjeScar/")
    cited = [
        (entry.driver_path, ref)
        for entry in entries
        for ref in entry.source_refs
        if any(directory in ref for directory in scar_dirs)
    ]
    assert cited, "no entry cites a scar source at all -- has the catalog changed?"
    unqualified = sorted(
        f"{driver_path} -> {ref}"
        for driver_path, ref in cited
        if not ref.startswith("scar-branch:")
    )
    assert unqualified == [], unqualified


def test_the_catalog_records_that_the_scar_utilities_are_off_main() -> None:
    """The module docstring explains scar being declared-only as a *workflow
    scheduling* fact ("no workflow below runs those utilities yet"), which
    reads as "wired up later". The stronger fact is that main cannot build
    them at all. Both are true; only one of them was written down."""
    from omnidriver.cardiaccore.catalogs import inputs

    doc = inputs.__doc__ or ""
    assert "c53a0d7" in doc, "the removal commit is not cited in the module docstring"
    assert "scar" in doc and "branch" in doc
