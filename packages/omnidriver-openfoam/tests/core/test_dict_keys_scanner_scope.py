"""Scope and default recovery for C++ dictionary reads.

The scanner reports bare key names; these tests pin the two things a builder
needs to turn that inventory into catalog paths: which sub-dictionary a read
happens in, and the default expression of an ``*OrDefault`` read. The shapes
are generic OpenFOAM reader idioms: a lambda over a runtime block name, a
chained ``subDict`` call split across lines, nested literal sub-dictionaries.
"""
from __future__ import annotations

from pathlib import Path

from omnidriver.openfoam.dict_keys_scanner import dict_read_default, scan_dict_reads


def _reads(tmp_path: Path, source: str) -> dict[tuple[str, str], tuple[str, ...]]:
    (tmp_path / "utility.C").write_text(source)
    return {(read.kind, read.name): read.scope for read in scan_dict_reads(tmp_path)}


def test_top_level_read_has_empty_scope(tmp_path: Path) -> None:
    reads = _reads(tmp_path, 'scalar t = dict.get<scalar>("tolerance");\n')
    assert reads[("key", "tolerance")] == ()


def test_bound_literal_subdicts_nest(tmp_path: Path) -> None:
    reads = _reads(
        tmp_path,
        'const dictionary& outer = dict.subDict("outer");\n'
        'const dictionary& inner(outer.subDict("inner"));\n'
        'word f = inner.get<word>("fieldName");\n',
    )
    assert reads[("subdict", "outer")] == ()
    assert reads[("subdict", "inner")] == ("outer",)
    assert reads[("key", "fieldName")] == ("outer", "inner")


def test_runtime_subdict_name_becomes_a_placeholder(tmp_path: Path) -> None:
    reads = _reads(
        tmp_path,
        "auto readBlock = [&](const word& blockName)\n"
        "{\n"
        "    const dictionary& bd = dict.subDict(blockName);\n"
        '    p.origin = bd.get<point>("origin");\n'
        '    const dictionary& sd = bd.subDict("limits");\n'
        '    p.lower = sd.get<scalar>("lower");\n'
        "};\n",
    )
    assert reads[("key", "origin")] == ("<blockName>",)
    assert reads[("key", "lower")] == ("<blockName>", "limits")


def test_chained_subdict_read_across_lines_is_found(tmp_path: Path) -> None:
    reads = _reads(
        tmp_path,
        "const vector scale = enabled\n"
        '    ? dict.subDict("options").getOrDefault<vector>\n'
        '        ("scale", defaultScale)\n'
        "    : defaultScale;\n",
    )
    assert reads[("key", "scale")] == ("options",)


def test_rebinding_a_name_uses_the_latest_binding(tmp_path: Path) -> None:
    reads = _reads(
        tmp_path,
        'const dictionary& d = dict.subDict("first");\n'
        'd.get<scalar>("a");\n'
        '{ const dictionary& d = dict.subDict("second");\n'
        'd.get<scalar>("b"); }\n',
    )
    assert reads[("key", "a")] == ("first",)
    assert reads[("key", "b")] == ("second",)


def test_inner_rebinding_expires_at_the_end_of_its_block(tmp_path: Path) -> None:
    reads = _reads(
        tmp_path,
        'const dictionary& d = dict.subDict("outer");\n'
        '{ const dictionary& d = dict.subDict("inner");\n'
        'd.get<scalar>("inside"); }\n'
        'd.get<scalar>("after");\n',
    )
    assert reads[("key", "inside")] == ("inner",)
    assert reads[("key", "after")] == ("outer",)


def test_default_expression_is_returned_verbatim(tmp_path: Path) -> None:
    (tmp_path / "utility.C").write_text(
        "const vector weights = dict.getOrDefault<vector>\n"
        '    ("weights", vector(0.30, 0.05, 0.05));\n'
        'const Switch on = dict.lookupOrDefault<Switch>("enabled", false);\n'
        'const scalar t = dict.get<scalar>("tolerance");\n'
    )
    defaults = {read.name: dict_read_default(read) for read in scan_dict_reads(tmp_path)}
    assert defaults == {
        "weights": "vector(0.30, 0.05, 0.05)",
        "enabled": "false",
        "tolerance": None,
    }


def test_same_name_defaults_on_one_line_keep_their_own_source_site(tmp_path: Path) -> None:
    (tmp_path / "utility.C").write_text(
        'scalar a = dict.getOrDefault<scalar>("value", 1); '
        'scalar b = dict.getOrDefault<scalar>("value", 2);\n'
    )
    reads = scan_dict_reads(tmp_path)
    assert [dict_read_default(read) for read in reads] == ["1", "2"]


def test_quoted_commas_and_escapes_stay_inside_the_default(tmp_path: Path) -> None:
    (tmp_path / "utility.C").write_text(
        r'word label = dict.getOrDefault<word>("label", "a,\"b");' "\n"
    )
    [read] = scan_dict_reads(tmp_path)
    assert dict_read_default(read) == r'"a,\"b"'
