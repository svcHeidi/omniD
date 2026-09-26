"""Reproductions that need neither a solver nor a source checkout."""
import pytest

from omnidriver.openfoam.dict_keys_scanner import scan_dict_reads
from omnidriver.openfoam.mutators import read_foam_entry, update_foam_entry
from omnidriver.openfoam.openfoam_environment import load_openfoam_environment


def test_commented_value_is_neither_read_nor_modified(tmp_path):
    path = tmp_path / "controlDict"
    comment = "/*\ndeltaT 99;\n*/\n"
    path.write_text(comment + "deltaT 0.01;\n")
    assert read_foam_entry(path, "deltaT") == "0.01"
    update_foam_entry(path, "deltaT", "0.02")
    assert comment in path.read_text()
    assert read_foam_entry(path, "deltaT") == "0.02"


def test_commented_only_entry_cannot_be_written(tmp_path):
    path = tmp_path / "controlDict"
    original = "/*\ndeltaT 99;\n*/\nendTime 1;\n"
    path.write_text(original)
    assert read_foam_entry(path, "deltaT") is None
    with pytest.raises(KeyError):
        update_foam_entry(path, "deltaT", "0.02")
    assert path.read_text() == original


@pytest.mark.parametrize("body", ["deltaT\n0.01;\n", "deltaT /* note */ 0.01;\n"])
def test_multiline_and_commented_values_remain_single_entries(tmp_path, body):
    path = tmp_path / "controlDict"
    path.write_text(body + "endTime 2;\n")
    assert read_foam_entry(path, "deltaT") == "0.01"
    update_foam_entry(path, "deltaT", "0.02")
    assert read_foam_entry(path, "deltaT") == "0.02"
    assert "0.01" not in path.read_text()
    assert read_foam_entry(path, "endTime") == "2"


def test_quoted_comment_markers_are_values(tmp_path):
    path = tmp_path / "dict"
    path.write_text('url "https://example.test/*path*/"; // annotation\n')
    assert read_foam_entry(path, "url") == '"https://example.test/*path*/"'


def test_scoped_reader_ignores_commented_braces_and_scope(tmp_path):
    path = tmp_path / "dict"
    path.write_text("/* outer { deltaT 99; } */\nouter\n{\n/* } */\ndeltaT 0.01;\n}\n")
    assert read_foam_entry(path, "deltaT", scope="outer") == "0.01"


def test_quoted_delimiters_do_not_change_scopes_or_sibling_entries(tmp_path):
    path = tmp_path / "dict"
    path.write_text('note "{ unmatched ; // comment text";\nouter { deltaT 0.01; endTime 2; }\n')
    assert read_foam_entry(path, "deltaT", scope="outer") == "0.01"
    update_foam_entry(path, "deltaT", "0.02", scope="outer")
    assert read_foam_entry(path, "endTime", scope="outer") == "2"
    assert 'note "{ unmatched ; // comment text";' in path.read_text()


def test_multiple_entries_on_one_line_and_key_prefixes(tmp_path):
    path = tmp_path / "dict"
    path.write_text("deltaT-extra 99; deltaT 0.01; endTime 2;\n")
    assert read_foam_entry(path, "deltaT") == "0.01"
    update_foam_entry(path, "deltaT", "0.02")
    assert read_foam_entry(path, "deltaT-extra") == "99"
    assert read_foam_entry(path, "deltaT") == "0.02"
    assert read_foam_entry(path, "endTime") == "2"


def test_source_failure_is_not_masked_by_environment_export(tmp_path):
    bashrc = tmp_path / "bashrc"
    bashrc.write_text("export WM_PROJECT_DIR=/not/a/runtime\nreturn 7\n")
    loaded = load_openfoam_environment(bashrc_path=bashrc, base_env={})
    assert loaded.error is not None
    assert "7" in loaded.error
    assert "WM_PROJECT_DIR" not in loaded.env


def test_cpp_scanner_preserves_source_line_after_comments(tmp_path):
    source = tmp_path / "model.C"
    source.write_text('/*\ncomment\n*/\ndict.lookupOrDefault<scalar>("alpha", 2);\n')
    reads = scan_dict_reads(tmp_path)
    assert len(reads) == 1
    assert reads[0].line == 4
