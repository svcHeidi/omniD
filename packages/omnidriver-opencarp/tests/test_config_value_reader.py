"""OpenCARPPlugin's get_config_value_reader: refusals beyond what
par_format.read_raw alone reports -- e.g. an unquoted string value
containing `=` is silently truncated by openCARP, so it is refused by name."""
from __future__ import annotations

import pytest

from omnidriver.opencarp.par_format import ParFormatError
from omnidriver.opencarp.plugin import OpenCARPPlugin


@pytest.fixture()
def reader():
    return OpenCARPPlugin().get_config_value_reader()


def test_unquoted_string_with_equals_is_refused_F10(tmp_path, reader):
    document = tmp_path / "nversion.par"
    document.write_text("imp_region[0].im_param = flags=EPI\n")
    with pytest.raises(ParFormatError) as excinfo:
        reader(document, ("imp_region[0]", "im_param"))
    message = str(excinfo.value)
    assert "imp_region[0].im_param" in message
    assert str(document) in message
    assert "F10" in message


def test_quoted_string_with_equals_reads_fine(tmp_path, reader):
    document = tmp_path / "nversion.par"
    document.write_text('imp_region[0].im_param = "flags=EPI"\n')
    assert reader(document, ("imp_region[0]", "im_param")) == "flags=EPI"


def test_a_string_without_equals_is_unaffected(tmp_path, reader):
    document = tmp_path / "nversion.par"
    document.write_text("imp_region[0].im = tenTusscherPanfilov\n")
    assert reader(document, ("imp_region[0]", "im")) == "tenTusscherPanfilov"


def test_boolean_spelling_other_than_0_1_is_refused_F1(tmp_path, reader):
    document = tmp_path / "nversion.par"
    document.write_text("compute_APD = no\n")
    with pytest.raises(ParFormatError) as excinfo:
        reader(document, ("compute_APD",))
    assert "F1" in str(excinfo.value)


def test_absent_document_reads_as_none(tmp_path, reader):
    assert reader(tmp_path / "missing.par", ("tend",)) is None


def test_absent_key_reads_as_none(tmp_path, reader):
    document = tmp_path / "nversion.par"
    document.write_text("tend = 10.0\n")
    assert reader(document, ("dt",)) is None
