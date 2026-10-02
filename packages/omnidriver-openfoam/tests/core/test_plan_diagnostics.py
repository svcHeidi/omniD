"""What the OpenFOAM layer adds to a strict plan through ``get_plan_diagnostics``."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.core.plugin_profile import CxxMapping
from omnidriver.openfoam.case_dict_keys import case_dict_key_diagnostics
from omnidriver.openfoam.dict_keys_scanner import cached_scan, locate, reads_at
from omnidriver.core.plugin_profile import CaseFileRule
from omnidriver.openfoam.plan_diagnostics import _owned_dict_relpaths, plan_diagnostics

SLAB = '''int main(int argc, char *argv[])
{
    IOdictionary slabDict
    (
        IOobject("setPurkinjeSlabDict", runTime.system(), mesh, IOobject::MUST_READ, IOobject::NO_WRITE)
    );
    const scalar thickness = slabDict.getOrDefault<scalar>("thickness", 0.1);
    const scalar multiplier = slabDict.getOrDefault<scalar>("multiplier", 3.0);
}
'''


def _context(mapping, *, report=None):
    scans = []

    def scan(root, *, allowlist_path, entries, cache_root=None, force=False):
        scans.append(root)
        return SimpleNamespace(to_json=lambda: report)

    capabilities = SimpleNamespace(
        cxx_mapping=SimpleNamespace(profile=lambda: SimpleNamespace(cxx_mapping=mapping)),
        dict_key_scanner=SimpleNamespace(scan=scan),
        dictionaries=SimpleNamespace(
            entries=lambda: (), catalog=lambda: SimpleNamespace(entries_for=lambda name: ()),
            documents=lambda: {},
        ),
        manifest=SimpleNamespace(manifest=lambda: {}),
        case_files=SimpleNamespace(all_rules=lambda: ()),
        run_semantic_validator=SimpleNamespace(validate=lambda request: ()),
    )
    return SimpleNamespace(
        capabilities=capabilities, identity=SimpleNamespace(resolutions={"cxx_mapping": "toy"}),
    ), scans


def _mapping(tmp_path: Path) -> CxxMapping:
    return CxxMapping(
        source_root_variable="TOY_NATIVE_TREE", source_root_relative="src",
        allowlist_path=tmp_path / "allowlist.json",
    )


def _diagnose(context, tmp_path, env):
    return plan_diagnostics(
        tmp_path / "case", workflow_dag=None, env=env, scratch_root=None, driver_context=context,
    )


def test_an_unsupplied_source_root_is_one_info_diagnostic_and_no_scan(tmp_path):
    context, scans = _context(_mapping(tmp_path))
    (diagnostic,) = _diagnose(context, tmp_path, {})
    assert (diagnostic.level, diagnostic.code) == ("info", "plugin_cxx_source_not_supplied")
    assert "TOY_NATIVE_TREE" in diagnostic.message
    assert scans == []


def test_a_supplied_root_that_is_not_a_directory_is_refused(tmp_path):
    context, scans = _context(_mapping(tmp_path))
    (diagnostic,) = _diagnose(context, tmp_path, {"TOY_NATIVE_TREE": str(tmp_path / "absent")})
    assert (diagnostic.level, diagnostic.code) == ("error", "plugin_cxx_source_unavailable")
    assert scans == []


def test_what_the_cxx_disagrees_with_never_fails_the_plan(tmp_path):
    (tmp_path / "tree" / "src").mkdir(parents=True)
    report = {
        "disagreements": ["a.c: catalogue value_kind 'word'; the C++ reads scalar (x.C:3)"],
        "unread": [{"driver_path": "$S.a.b", "note": "catalogued; the supplied C++ no longer reads it"}],
        "uncatalogued": [{"kind": "key", "key": "c"}], "unresolved": [{"key": "d"}],
    }
    context, scans = _context(_mapping(tmp_path), report=report)
    diagnostics = _diagnose(context, tmp_path, {"TOY_NATIVE_TREE": str(tmp_path / "tree")})
    assert scans == [(tmp_path / "tree" / "src").resolve()]
    assert [(d.level, d.code) for d in diagnostics] == [
        ("warning", "plugin_catalog_disagreement"), ("info", "plugin_catalog_unread"),
        ("info", "plugin_catalog_uncatalogued"),
    ]
    assert "no longer reads it" in diagnostics[1].message and "has no effect" in diagnostics[1].message


def test_a_stack_without_a_cxx_mapping_adds_no_catalogue_diagnostics(tmp_path):
    context, scans = _context(None)
    assert _diagnose(context, tmp_path, {}) == ()
    assert scans == []


def test_a_case_key_the_cxx_reads_is_reported_once_by_the_plan_not_by_the_key_check(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "setPurkinjeSlab.C").write_text(SLAB)
    scan = cached_scan(source, cache_root=None)
    entries = (DictEntry(
        driver_path="$SLAB.thickness", description="", value_kind="scalar",
        source_refs=("src/setPurkinjeSlab.C",),
    ),)
    placed = locate(scan, entries, document="setPurkinjeSlabDict")
    assert reads_at(scan, placed, ("multiplier",))
    assert not reads_at(scan, placed, ("mulitplier",))
    assert not reads_at(scan, placed, ("outer", "multiplier"))

    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    (case / "system" / "setPurkinjeSlabDict").write_text(
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n"
        "    object setPurkinjeSlabDict;\n}\nthickness 0.2;\nmultiplier 4;\nmulitplier 5;\n"
    )
    scanned = lambda relpath, trail: reads_at(scan, placed, trail)  # noqa: E731
    keys = [
        d.field for d in case_dict_key_diagnostics(
            case, catalogued_paths=["thickness"], dict_relpaths=["system/setPurkinjeSlabDict"], scanned=scanned,
        )
    ]
    assert keys == ["mulitplier"]
    unfiltered = [
        d.field for d in case_dict_key_diagnostics(
            case, catalogued_paths=["thickness"], dict_relpaths=["system/setPurkinjeSlabDict"],
        )
    ]
    assert unfiltered == ["multiplier", "mulitplier"]


def test_a_case_that_sets_a_key_the_cxx_no_longer_reads_is_warned_that_it_has_no_effect(tmp_path):
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    (case / "system" / "setPurkinjeSlabDict").write_text(
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n"
        "    object setPurkinjeSlabDict;\n}\nthickness 0.2;\nsmoothing 4;\nblock { retired 1; }\n"
    )
    found = case_dict_key_diagnostics(
        case, catalogued_paths=["thickness", "smoothing", "block.retired"],
        dict_relpaths=["system/setPurkinjeSlabDict"], unread=["smoothing", "block.retired"],
    )
    assert [(d.level, d.code, d.field) for d in found] == [
        ("warning", "unread_case_dict_key", "smoothing"), ("warning", "unread_case_dict_key", "retired"),
    ]
    assert "'smoothing' is catalogued, but the supplied C++ no longer reads it" in found[0].message
    assert case_dict_key_diagnostics(
        case, catalogued_paths=["thickness", "smoothing", "block.retired"],
        dict_relpaths=["system/setPurkinjeSlabDict"],
    ) == ()


def test_the_dictionaries_checked_follow_the_adapters_case_file_rules_not_a_directory_name(tmp_path):
    case_root = tmp_path / "case"
    (case_root / "config").mkdir(parents=True)
    (case_root / "config" / "solver.yaml").write_text("solver: demo\n")
    rules = (CaseFileRule(
        path="config/solver.yaml", kind="configuration", role="x-neutral.configuration", required="always",
    ),)
    context = SimpleNamespace(capabilities=SimpleNamespace(
        case_files=SimpleNamespace(all_rules=lambda: rules),
        dictionaries=SimpleNamespace(documents=lambda: {"solver.yaml": ()}),
    ))
    assert _owned_dict_relpaths(case_root, context) == ("config/solver.yaml",)
