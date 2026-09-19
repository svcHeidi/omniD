"""Small, explicit conformance probes against the local OpenFOAM v2412 runtime.

The Python mutators intentionally perform lexical inspection (and preserve
source text), whereas ``foamDictionary`` parses and resolves an effective
dictionary.  These tests keep those contracts distinct and are marked native
so a missing installation cannot silently count as a passing runtime check.
"""

from __future__ import annotations

import subprocess
import os
from pathlib import Path

import pytest

from omnidriver.openfoam.mutators import read_foam_entry
from omnidriver.openfoam.openfoam_environment import discover_openfoam_bashrc


FOAM_BASHRC = discover_openfoam_bashrc()
native = pytest.mark.skipif(
    FOAM_BASHRC is None,
    reason="no OpenFOAM installation discoverable; native conformance is not verified",
)


def _native_value(path: Path, entry: str) -> str:
    # Source the verified runtime explicitly; no installation files are
    # modified, and the fixture lives under pytest's temporary directory.
    proc = subprocess.run(
        ["bash", "-lc", f"source \"{FOAM_BASHRC}\" >/dev/null && foamDictionary \"$OMNI_PROBE_PATH\" -entry \"$OMNI_PROBE_ENTRY\" -value"],
        env={**os.environ, "OMNI_PROBE_PATH": str(path), "OMNI_PROBE_ENTRY": entry},
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


HEADER = "FoamFile { version 2.0; format ascii; class dictionary; object d; }\n"


def test_lexical_adapter_preserves_quotes_comments_nested_and_lists(tmp_path: Path):
    path = tmp_path / "d"
    path.write_text(
        HEADER
        + "// ignored = 99;\n"
        + 'quoted "hello // world"; /* block comment */\n'
        + "nested {\n  dimensions [0 1 -1 0 0 0 0];\n  values (1 2 3);\n}\n"
    )
    assert read_foam_entry(path, "quoted") == '"hello // world"'
    assert read_foam_entry(path, "ignored") is None
    assert read_foam_entry(path, "dimensions", scope="nested") == "[0 1 -1 0 0 0 0]"
    assert read_foam_entry(path, "values", scope="nested") == "(1 2 3)"


@native
def test_v2412_effective_resolution_includes_substitutions_and_duplicates(tmp_path: Path):
    (tmp_path / "inc").write_text("incVal 9;\n")
    path = tmp_path / "d"
    path.write_text(
        HEADER
        + '#include "inc"\n'
        + "base 7;\n"
        + "dup 1;\n"
        + "dup 2;\n"
        + "baseRef $base;\n"
    )
    assert _native_value(path, "incVal") == "9"
    assert _native_value(path, "baseRef") == "7"
    assert _native_value(path, "dup") == "2"


@native
def test_v2412_include_precedence_follows_declaration_order(tmp_path: Path):
    (tmp_path / "inc").write_text("shared fromInclude;\n")
    path = tmp_path / "d"
    path.write_text(HEADER + '#include "inc"\n' + "shared fromRoot;\n")
    assert _native_value(path, "shared") == "fromRoot"


@native
def test_v2412_serializes_nested_dimensions_and_lists(tmp_path: Path):
    path = tmp_path / "d"
    path.write_text(
        HEADER
        + "nested {\n"
        + "  dimensions [0 1 -1 0 0 0 0];\n"
        + "  values (1 2 3);\n"
        + "}\n"
    )
    nested = _native_value(path, "nested")
    assert "dimensions" in nested and "[ 0 1 -1 0 0 0 0 ]" in nested
    assert "values" in nested and "( 1 2 3 )" in nested


@native
def test_v2412_handles_comments_quoted_strings_and_multiline_values(tmp_path: Path):
    path = tmp_path / "d"
    path.write_text(
        HEADER
        + "// ignored 99;\n"
        + "/* another ignored entry 4; */\n"
        + 'quoted "text containing // is not a comment";\n'
        + "multiline\n(\n  1\n  2\n  3\n);\n"
    )
    assert _native_value(path, "quoted") == '"text containing // is not a comment"'
    assert _native_value(path, "multiline") == "( 1 2 3 )"
