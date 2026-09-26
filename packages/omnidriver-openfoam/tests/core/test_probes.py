"""OpenFOAM's ``probes`` output layout, read from files OpenFOAM v2412 wrote.

Every fixture under ``fixtures/probes/`` is a verbatim copy of a real run's
output (docs/solver-learning/cardiacfoam.md, section Q), and
``packages/omnidriver-cardiacfoam/tests/test_activation_probes_native.py``
re-runs the solver and fails if any of them drifts from what it writes:

- ``Cx``: ``postProcess -func 'Niedererpoints(Cx,Cy,Cz)' -latestTime`` on
  the cell-centre components ``postProcess -func writeCellCentres`` wrote
  (Q3), the ``NiedererEtAl2011verification`` hex mesh at dx 0.5 mm;
- ``C``: the same function on the vector ``C`` (Q5);
- ``Cx_not_found``: the same function with ``probeLocations`` replaced by
  ``((1 1 1) (0 0 0))``, the first of which lies outside the mesh (Q6).

The refusals below mutate a real file one fact at a time, so each names a
single defect, never a layout invented from scratch.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.openfoam.probes import (
    CELL_CENTRE_FIELDS,
    ProbeSeries,
    parse_probe_series,
    probes_function_with_fields,
    sibling_probe_files,
)

FIXTURES = Path(__file__).parent / "fixtures" / "probes"


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
    """Q6: OpenFOAM writes ``# Not Found`` on the header and -VGREAT
    (``-1e+300``) in the column; the flag, not the number, says so."""
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


def test_a_function_with_fields_names_its_own_output_directory():
    """Q3: ``postProcess -func 'Niedererpoints(Cx,Cy,Cz)'`` writes under
    ``postProcessing/Niedererpoints(Cx,Cy,Cz)/`` (OpenFOAM names the
    function after the whole ``-func`` argument)."""
    assert CELL_CENTRE_FIELDS == ("Cx", "Cy", "Cz")
    assert probes_function_with_fields("Niedererpoints", CELL_CENTRE_FIELDS) == "Niedererpoints(Cx,Cy,Cz)"
    assert sibling_probe_files("postProcessing/Niedererpoints/0/activationTime", CELL_CENTRE_FIELDS) == (
        "postProcessing/Niedererpoints(Cx,Cy,Cz)/0/Cx",
        "postProcessing/Niedererpoints(Cx,Cy,Cz)/0/Cy",
        "postProcessing/Niedererpoints(Cx,Cy,Cz)/0/Cz",
    )


def test_a_path_outside_the_probes_layout_is_refused():
    with pytest.raises(ValueError, match="postProcessing/<function>/<instance>/<field>"):
        sibling_probe_files("0.015/activationTime", CELL_CENTRE_FIELDS)
