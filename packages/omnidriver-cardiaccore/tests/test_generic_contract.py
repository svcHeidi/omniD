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

    # `.identity` is a `StackIdentity` (Task 7): the most-specific provider
    # (last in the ordered stack) is this plugin, per
    # `identity.to_json()["providers"][-1]["id"]` -- `.identity.id` was the
    # retired single-plugin shape.
    assert context.identity.to_json()["providers"][-1]["id"] == "org.omnidriver.cardiaccore"
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
    assert catalogs["cardiaccore_python_utilities"]["purkinje_coverage"]["status"] == "supported_array_method"
    assert catalogs["cardiaccore_operations"]["cardiaccore.purkinje.coverage_observation.v1"]["status"]["array_api"] == "available"
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

    factories = driver_context(
        OpenFOAMEnvironmentPlugin(), plugin, source="test",
    ).capabilities.tutorials.catalog()[
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
    """R2 finding 9: all 21 `<ventKey>` entries declared no allowed_bindings,
    including the ones audit finding S1 was about ("banana" as a ventricle).
    `VENT_KEYS = ("lv", "rv")` sits immediately above `TREE_ENTRIES` with a
    comment saying the domain is closed; every dynamic_path entry with a
    `<ventKey>` placeholder must declare it from that constant."""
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
    """Generalises `test_every_ventkey_entry_declares_its_allowed_bindings`.

    That test closed R2 finding 9 for `<ventKey>` only. The same hole stayed
    open for `$PURKINJE_SCAR.regions.<region_id>.*`, whose four entries
    declared no domain at all -- which is audit finding S1's shape exactly:
    a placeholder nothing states a fact about. `DictEntry.__post_init__`
    already refuses a *partial* declaration; it cannot refuse a wholly
    absent one, because an entry with no dynamic segment to constrain is
    legitimate. This asserts the catalog-wide property instead: every
    placeholder of every `dynamic_path` entry names a domain, closed
    (a tuple) or explicitly open (`None`).
    """
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
    """`<region_id>` is an *integer label*, not a case-author-chosen word.

    `setPurkinjeScar.C`'s `policyForRegion` looks the sub-block up by
    `Foam::name(region)` where `region` is a `label` read from the
    `regionField` (`ScarRegionID`) volScalarField -- so the key is the
    decimal spelling of whatever integer that field carries, and the README
    shows `regions { 3 { ... } }`. That is an unbounded set, so the domain
    is open (`None`) rather than a closed tuple -- but it is now *declared*
    open, which is a fact an agent can read, and the evidence for it is
    cited in the entries' own constraints.
    """
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
        # The evidence is not on main. `c53a0d7` (2026-09-18, "refactor(scar):
        # remove scar and scar-Purkinje-coupling code from main") deleted
        # `src/setPurkinjeScar/` and `src/setCardiacScar/`; `origin/scar`
        # preserves them, and main's `src/Allwmake` builds neither. A
        # `source_refs` path that reads as mainline but only resolves on an
        # unmerged branch is a citation that cannot be checked, so the
        # branch must be named where the claim is made.
        assert "scar" in joined and "branch" in joined, entry.driver_path


def test_every_scar_source_ref_names_the_branch_it_resolves_on() -> None:
    """A citation an agent cannot check is worse than no citation.

    `c53a0d7` (2026-09-18, "refactor(scar): remove scar and
    scar-Purkinje-coupling code from main") deleted `src/setCardiacScar/` and
    `src/setPurkinjeScar/` from cardiacCore's main; they survive only on the
    `scar` branch, and main's `src/Allwmake` builds neither. Written as bare
    `src/setCardiacScar/...` these read as mainline paths -- the same shape as
    every other `source_refs` entry in this module, none of which need a
    qualifier -- so an agent following one finds nothing and cannot tell
    whether the catalog is wrong or its checkout is.

    The sibling package has a real drift guard for this class
    (`omnidriver-cardiacfoam/tests/test_source_refs_exist.py`, which resolves
    every ref against the native tree); cardiacCore has none, which is why
    these went stale-by-relocation unnoticed. This is the narrower check:
    not "does the file exist" but "does the citation say where to look".
    """
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
