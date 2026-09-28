"""OpenFOAM's ``probes`` output layout, read from files a real OpenFOAM
v2412 run wrote (fixtures under ``fixtures/probes/``; see
docs/solver-learning/cardiacfoam.md).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.openfoam.probes import ProbeSeries, interpolation_scheme, parse_probe_series

FIXTURES = Path(__file__).parent / "fixtures" / "probes"
# Cx/C: `postProcess -func 'Niedererpoints(Cx,Cy,Cz)' -latestTime` on
# NiedererEtAl2011verification (dx 0.5 mm). Cx_not_found: same, with
# probeLocations replaced so the first probe lies outside the mesh.


def _text(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_a_real_scalar_probe_file_is_read_as_locations_times_and_rows():
    series = parse_probe_series(_text("Cx"), source="Cx")
    assert isinstance(series, ProbeSeries)
    assert [index for index, _ in series.locations] == list(range(9))
    assert series.locations[0] == (0, (0.0, 0.0, 0.007))
    assert series.locations[8] == (8, (0.01, 0.0015, 0.0035))
    assert series.times == (0.015,)
    assert series.rows == ((0.00025, 0.00025, 0.01975, 0.01975, 0.00025, 0.00025, 0.01975, 0.01975, 0.00975),)
    assert series.not_found == frozenset()


def test_a_probe_openfoam_did_not_find_is_marked_not_found():
    """OpenFOAM writes -VGREAT (``-1e+300``) in the column; the ``# Not
    Found`` flag, not the number, is what's checked."""
    series = parse_probe_series(_text("Cx_not_found"), source="Cx_not_found")
    assert series.locations == ((0, (1.0, 1.0, 1.0)), (1, (0.0, 0.0, 0.0)))
    assert series.not_found == frozenset({0})
    assert series.rows == ((-1e300, 0.00025),)


def test_a_vector_field_is_refused_by_name():
    with pytest.raises(ValueError, match=r"C.*vector or tensor"):
        parse_probe_series(_text("C"), source="C")


def test_no_probe_lines_is_refused():
    text = "".join(line for line in _text("Cx").splitlines(keepends=True) if not line.startswith("# Probe"))
    with pytest.raises(ValueError, match="no '# Probe"):
        parse_probe_series(text, source="Cx")


def test_a_repeated_probe_index_is_refused():
    text = _text("Cx").replace("# Probe 1 (0 0 0)", "# Probe 0 (0 0 0)")
    with pytest.raises(ValueError, match="probe 0 twice"):
        parse_probe_series(text, source="Cx")


def test_a_row_with_the_wrong_column_count_is_refused():
    lines = _text("Cx").splitlines()
    lines[-1] = lines[-1].rsplit(None, 1)[0]
    with pytest.raises(ValueError, match="9 columns, expected 10"):
        parse_probe_series("\n".join(lines) + "\n", source="Cx")


def test_no_data_rows_is_refused():
    text = "".join(line for line in _text("Cx").splitlines(keepends=True) if line.startswith("#"))
    with pytest.raises(ValueError, match="no data rows"):
        parse_probe_series(text, source="Cx")


def test_a_time_header_naming_other_probes_is_refused():
    """``includeOutOfBounds false`` drops a not-found probe's column; the
    header then no longer lists every probe, and columns would shift."""
    lines = _text("Cx_not_found").splitlines()
    lines[2] = "# Time        1"
    lines[3] = "0.015         0.00025"
    with pytest.raises(ValueError, match=r"'# Time' header names probes \[1\]"):
        parse_probe_series("\n".join(lines) + "\n", source="Cx_not_found")


def test_interpolation_scheme_reads_the_cases_own_dict(tmp_path):
    """``interpolationScheme`` defaults to ``cell`` (OpenFOAM's ``probes.C``)
    when the function's own dict has none."""
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "Niedererpoints").write_text("interpolationScheme cellPoint;\n")
    assert interpolation_scheme(tmp_path, "postProcessing/Niedererpoints/0/activationTime") == "cellPoint"
    (tmp_path / "system" / "NoScheme").write_text("fields (activationTime);\n")
    assert interpolation_scheme(tmp_path, "postProcessing/NoScheme/0/activationTime") == "cell"


def test_a_path_outside_the_probes_layout_is_refused(tmp_path):
    with pytest.raises(ValueError, match="postProcessing/<function>/<instance>/<field>"):
        interpolation_scheme(tmp_path, "0.015/activationTime")
