"""Tests __LC__ rendering for tet-mesh sweeps. Never calls gmsh/gmshToFoam
-- those run later as workflow_dag steps, not during materialization.
"""

from pathlib import Path

import pytest

from omnidriver.openfoam.tet_mesh_provisioning import render_tet_geo, render_tet_geo_at_length


def _write_template(root: Path, *, relpath: str = "setup/studies/tetConvergence/box.geo.template", body: str = "lc = __LC__;\nBox(1) = {0, 0, 0, 1, 1, 1};\n") -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_renders_lc_from_n(tmp_path):
    _write_template(tmp_path)
    geo_path = render_tet_geo(tmp_path, 10)
    text = geo_path.read_text()
    assert "lc = 0.1;" in text
    assert "__LC__" not in text


def test_returns_the_written_geo_path(tmp_path):
    _write_template(tmp_path)
    geo_path = render_tet_geo(tmp_path, 20)
    assert geo_path == tmp_path / "setup/studies/tetConvergence/box.geo"
    assert geo_path.exists()


def test_rejects_non_positive_n(tmp_path):
    _write_template(tmp_path)
    with pytest.raises(ValueError, match="positive"):
        render_tet_geo(tmp_path, 0)
    with pytest.raises(ValueError, match="positive"):
        render_tet_geo(tmp_path, -5)


def test_rejects_non_integer_n(tmp_path):
    _write_template(tmp_path)
    with pytest.raises(TypeError, match="integer"):
        render_tet_geo(tmp_path, 10.5)


def test_missing_template_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_tet_geo(tmp_path, 10)


def test_rejects_template_with_no_lc_placeholder(tmp_path):
    _write_template(tmp_path, body="Box(1) = {0, 0, 0, 1, 1, 1};\n")
    with pytest.raises(ValueError, match="__LC__"):
        render_tet_geo(tmp_path, 10)


def test_rejects_template_with_multiple_lc_placeholders(tmp_path):
    _write_template(tmp_path, body="lc = __LC__;\nlc2 = __LC__;\n")
    with pytest.raises(ValueError, match="__LC__"):
        render_tet_geo(tmp_path, 10)


def test_comment_mentioning_the_placeholder_by_name_does_not_count(tmp_path):
    # The real box.geo.template files document the substitution mechanism in
    # a `//` comment that names the placeholder literally ("__LC__ is
    # substituted by run_corrector_study.sh") -- found via real, non-mocked
    # verification against an actual bidomain scratch copy. A naive
    # text.count("__LC__") treats that as a second occurrence and rejects a
    # perfectly valid template; only the real substitution site should count,
    # and the comment's own textual mention must survive untouched (a blind
    # str.replace would otherwise mangle it into nonsense with the number).
    _write_template(
        tmp_path,
        body="// The characteristic length placeholder __LC__ is substituted here.\nlc = __LC__;\n",
    )
    geo_path = render_tet_geo(tmp_path, 10)
    text = geo_path.read_text()
    assert "lc = 0.1;" in text
    assert "// The characteristic length placeholder __LC__ is substituted here." in text


# --- render_tet_geo_at_length (2026-09-24) ----------------------------------
# An explicit characteristic length, for a geometry whose sweep is a physical
# dx rather than a unit-cube cell count (niederer_2012's metre-sized slab).

def test_at_length_substitutes_lc_itself(tmp_path):
    _write_template(tmp_path)
    geo_path = render_tet_geo_at_length(tmp_path, 0.0002)
    assert geo_path.read_text() == "lc = 0.0002;\nBox(1) = {0, 0, 0, 1, 1, 1};\n"


def test_render_tet_geo_is_at_length_with_the_reciprocal(tmp_path):
    _write_template(tmp_path)
    by_n = render_tet_geo(tmp_path, 8).read_text()
    by_length = render_tet_geo_at_length(tmp_path, 1.0 / 8).read_text()
    assert by_n == by_length


def test_at_length_keeps_a_comment_naming_the_placeholder(tmp_path):
    _write_template(
        tmp_path,
        body="// The characteristic length placeholder __LC__ is substituted by\nlc = __LC__;\n",
    )
    text = render_tet_geo_at_length(tmp_path, 0.0005).read_text()
    assert text == "// The characteristic length placeholder __LC__ is substituted by\nlc = 0.0005;\n"


@pytest.mark.parametrize("lc", [0, 0.0, -1e-4, float("inf"), float("nan")])
def test_at_length_rejects_non_finite_or_non_positive_lc(tmp_path, lc):
    _write_template(tmp_path)
    with pytest.raises(ValueError, match="finite and positive"):
        render_tet_geo_at_length(tmp_path, lc)


@pytest.mark.parametrize("lc", [True, "0.1", None])
def test_at_length_rejects_a_non_number(tmp_path, lc):
    _write_template(tmp_path)
    with pytest.raises(TypeError, match="real number"):
        render_tet_geo_at_length(tmp_path, lc)


def test_at_length_still_refuses_a_template_with_two_placeholders(tmp_path):
    _write_template(tmp_path, body="lc = __LC__;\nlc2 = __LC__;\n")
    with pytest.raises(ValueError, match="__LC__"):
        render_tet_geo_at_length(tmp_path, 0.1)
