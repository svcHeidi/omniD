"""The case-owned coordinates convention, read the way native reads it.

Mirrors src/coordinatesConvention/coordinatesConvention.H in cardiacCore:
`coordinateSystem` is required, the `coordinates` block is optional with
canonical field-name defaults, and the transmural bounds are named by
anatomy rather than by numeric order.
"""

import pytest

from omnidriver.cardiaccore.operations.coordinates_convention import (
    CANONICAL_FIELD_NAMES,
    read_coordinates_convention,
)


def _write(tmp_path, body):
    dictionary = tmp_path / "system" / "coordinatesConventionDict"
    dictionary.parent.mkdir(exist_ok=True)
    dictionary.write_text(body)
    return tmp_path


_CHAMBERS = "intraventricularChambers { LV -1; RV 1; }"


def test_reads_a_case_that_declares_its_own_field_names(tmp_path):
    root = _write(tmp_path, (
        "coordinateSystem uvc; "
        "coordinates { transmuralField uvc_transmural; "
        "intraventricularField uvc_intraventricular; "
        "longitudinalField uvc_longitudinal; } "
        "transmural { endocardium 0; epicardium 1; } " + _CHAMBERS
    ))
    convention = read_coordinates_convention(root)

    assert convention.coordinate_system == "uvc"
    assert convention.transmural_field == "uvc_transmural"
    assert convention.intraventricular_field == "uvc_intraventricular"
    assert convention.longitudinal_field == "uvc_longitudinal"
    assert (convention.endocardium_value, convention.epicardium_value) == (0.0, 1.0)
    assert (convention.lv_value, convention.rv_value) == (-1.0, 1.0)


def test_field_names_default_to_the_canonical_names_when_unstated(tmp_path):
    root = _write(tmp_path, (
        "coordinateSystem cobiveco; "
        "transmural { endocardium 1; epicardium 0; } " + _CHAMBERS
    ))
    convention = read_coordinates_convention(root)

    assert CANONICAL_FIELD_NAMES == ("transmural", "intraventricular", "apicobasal")
    assert convention.transmural_field == "transmural"
    assert convention.intraventricular_field == "intraventricular"
    assert convention.longitudinal_field == "apicobasal"


def test_a_case_names_only_the_field_that_differs(tmp_path):
    root = _write(tmp_path, (
        "coordinateSystem cobiveco; "
        "coordinates { transmuralField tm; } "
        "transmural { endocardium 1; epicardium 0; } " + _CHAMBERS
    ))
    convention = read_coordinates_convention(root)

    assert convention.transmural_field == "tm"
    assert convention.intraventricular_field == "intraventricular"
    assert convention.longitudinal_field == "apicobasal"


def test_transmural_bounds_are_named_not_ordered(tmp_path):
    """CObiveco reads 1=endocardium, 0=epicardium -- the reverse of UVC.

    The numeric bound must come from lower/upper, which do not assume that
    endocardium is the smaller value.
    """
    root = _write(tmp_path, (
        "coordinateSystem cobiveco; "
        "transmural { endocardium 1; epicardium 0; } " + _CHAMBERS
    ))
    convention = read_coordinates_convention(root)

    assert convention.endocardium_value == 1.0
    assert convention.epicardium_value == 0.0
    assert convention.transmural_lower == 0.0
    assert convention.transmural_upper == 1.0
    assert convention.transmural_range == 1.0


def test_chambers_are_classified_by_nearest_declared_value(tmp_path):
    root = _write(tmp_path, (
        "coordinateSystem uvc; "
        "transmural { endocardium 0; epicardium 1; } " + _CHAMBERS
    ))
    convention = read_coordinates_convention(root)

    assert convention.is_left_ventricle(-0.9)
    assert not convention.is_left_ventricle(0.9)
    assert convention.chamber_seam == 0.0


def test_an_unknown_coordinate_system_is_rejected(tmp_path):
    root = _write(tmp_path, (
        "coordinateSystem spherical; "
        "transmural { endocardium 0; epicardium 1; } " + _CHAMBERS
    ))
    with pytest.raises(ValueError, match="uvc.*cobiveco"):
        read_coordinates_convention(root)


@pytest.mark.parametrize("body, missing", [
    ("transmural { endocardium 0; epicardium 1; } " + _CHAMBERS, "coordinateSystem"),
    ("coordinateSystem uvc; " + _CHAMBERS, "transmural.endocardium"),
    ("coordinateSystem uvc; transmural { endocardium 0; epicardium 1; }",
     "intraventricularChambers.LV"),
])
def test_required_entries_are_reported_by_name(tmp_path, body, missing):
    root = _write(tmp_path, body)
    with pytest.raises(ValueError, match=missing.replace(".", r"\.")):
        read_coordinates_convention(root)


def test_a_missing_dictionary_names_the_file(tmp_path):
    with pytest.raises(ValueError, match="coordinatesConventionDict"):
        read_coordinates_convention(tmp_path)


def test_field_paths_default_to_canonical_when_no_convention_is_supplied():
    """No case supplied means native's own defaults, not a guess.

    The paths are declared, not discovered: nothing probes the filesystem
    for a convention the caller did not hand over.
    """
    from omnidriver.cardiaccore.operations.coordinates_convention import (
        coordinate_field_paths,
    )

    assert coordinate_field_paths() == {
        "transmural": "0/transmural",
        "intraventricular": "0/intraventricular",
        "longitudinal": "0/apicobasal",
    }


def test_field_paths_follow_a_supplied_convention(tmp_path):
    from omnidriver.cardiaccore.operations.coordinates_convention import (
        coordinate_field_paths,
    )

    root = _write(tmp_path, (
        "coordinateSystem uvc; "
        "coordinates { transmuralField uvc_transmural; "
        "longitudinalField uvc_longitudinal; } "
        "transmural { endocardium 0; epicardium 1; } " + _CHAMBERS
    ))
    paths = coordinate_field_paths(read_coordinates_convention(root))

    assert paths["transmural"] == "0/uvc_transmural"
    assert paths["longitudinal"] == "0/uvc_longitudinal"
    assert paths["intraventricular"] == "0/intraventricular"
