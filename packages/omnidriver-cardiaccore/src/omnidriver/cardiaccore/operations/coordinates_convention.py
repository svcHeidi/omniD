"""The case-owned ventricular coordinates convention.

cardiacCore does not have *a* coordinate convention. A case declares which
ventricular coordinate system it uses, what its coordinate fields are called,
and where its transmural and chamber values sit; every native utility then
reads whatever that case declared. This module reads the same dictionary the
same way, so the adapter chooses dictionary entries and field paths from the
selected case rather than from a name frozen into the workflow.

Mirrors ``src/coordinatesConvention/coordinatesConvention.H`` in native
cardiacCore. Where the two could drift, native is the authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from omnidriver.openfoam.mutators import read_foam_entry

#: Field names used for any entry a case's ``coordinates`` block leaves out,
#: in transmural / intraventricular / longitudinal order. A case whose fields
#: already carry these names needs no ``coordinates`` block at all.
CANONICAL_FIELD_NAMES = ("transmural", "intraventricular", "apicobasal")

#: The coordinate systems native accepts for ``coordinateSystem``.
COORDINATE_SYSTEMS = ("uvc", "cobiveco")

_DICTIONARY_NAME = "coordinatesConventionDict"


@dataclass(frozen=True)
class CoordinatesConvention:
    """One case's declared coordinate convention."""

    coordinate_system: str
    transmural_field: str
    intraventricular_field: str
    longitudinal_field: str
    endocardium_value: float
    epicardium_value: float
    lv_value: float
    rv_value: float

    @property
    def transmural_lower(self) -> float:
        """The smaller transmural bound, whichever surface carries it."""
        return min(self.endocardium_value, self.epicardium_value)

    @property
    def transmural_upper(self) -> float:
        """The larger transmural bound, whichever surface carries it."""
        return max(self.endocardium_value, self.epicardium_value)

    @property
    def transmural_range(self) -> float:
        return abs(self.epicardium_value - self.endocardium_value)

    @property
    def chamber_seam(self) -> float:
        """The value midway between the declared chambers."""
        return 0.5 * (self.lv_value + self.rv_value)

    def is_left_ventricle(self, intraventricular: float) -> bool:
        """Classify by nearest declared chamber value, not by sign."""
        return abs(intraventricular - self.lv_value) <= abs(
            intraventricular - self.rv_value
        )

    def field_path(self, field: str, *, time_dir: str = "0") -> str:
        """The case-relative path of one declared coordinate field."""
        names = {
            "transmural": self.transmural_field,
            "intraventricular": self.intraventricular_field,
            "longitudinal": self.longitudinal_field,
        }
        if field not in names:
            raise ValueError(
                f"unknown coordinate field {field!r}; expected one of "
                f"{', '.join(sorted(names))}"
            )
        return f"{time_dir}/{names[field]}"


def read_coordinates_convention(case_root: Path) -> CoordinatesConvention:
    """Read a case's ``system/coordinatesConventionDict``.

    Reads the dictionary without evaluating it: no directive is expanded and
    nothing is written. ``coordinateSystem``, the ``transmural`` bounds and
    the ``intraventricularChambers`` values are required, matching native's
    ``get``; the ``coordinates`` block is optional and each field name within
    it falls back to its canonical default, matching native's
    ``subOrEmptyDict`` plus ``getOrDefault``.
    """
    dictionary = Path(case_root) / "system" / _DICTIONARY_NAME
    if not dictionary.is_file():
        raise ValueError(f"{dictionary}: no {_DICTIONARY_NAME} in the selected case")

    system = _required_word(dictionary, "coordinateSystem", scope=None)
    if system not in COORDINATE_SYSTEMS:
        raise ValueError(
            f"{dictionary}: coordinateSystem must be one of "
            f"{' or '.join(COORDINATE_SYSTEMS)}; got {system!r}"
        )

    transmural_default, intraventricular_default, longitudinal_default = (
        CANONICAL_FIELD_NAMES
    )
    return CoordinatesConvention(
        coordinate_system=system,
        transmural_field=_optional_word(
            dictionary, "transmuralField", transmural_default,
        ),
        intraventricular_field=_optional_word(
            dictionary, "intraventricularField", intraventricular_default,
        ),
        longitudinal_field=_optional_word(
            dictionary, "longitudinalField", longitudinal_default,
        ),
        endocardium_value=_required_scalar(dictionary, "endocardium", "transmural"),
        epicardium_value=_required_scalar(dictionary, "epicardium", "transmural"),
        lv_value=_required_scalar(dictionary, "LV", "intraventricularChambers"),
        rv_value=_required_scalar(dictionary, "RV", "intraventricularChambers"),
    )


def _label(key: str, scope: str | None) -> str:
    return key if scope is None else f"{scope}.{key}"


def _required_word(dictionary: Path, key: str, *, scope: str | None) -> str:
    value = read_foam_entry(dictionary, key, scope=scope)
    if value is None:
        raise ValueError(f"{dictionary}: missing {_label(key, scope)}")
    return str(value).strip()


def _required_scalar(dictionary: Path, key: str, scope: str) -> float:
    value = read_foam_entry(dictionary, key, scope=scope)
    if value is None:
        raise ValueError(f"{dictionary}: missing {_label(key, scope)}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{dictionary}: {_label(key, scope)} must be a scalar"
        ) from exc


def _optional_word(dictionary: Path, key: str, default: str) -> str:
    value = read_foam_entry(dictionary, key, scope="coordinates")
    return default if value is None else str(value).strip()


def coordinate_field_paths(
    convention: CoordinatesConvention | None = None, *, time_dir: str = "0",
) -> dict[str, str]:
    """Case-relative paths of the three coordinate fields, by role.

    Supply a convention read from the selected case to get that case's names.
    With none supplied the canonical defaults are used -- the same names
    native falls back to when a case declares no ``coordinates`` block. This
    never reads the filesystem looking for a convention the caller did not
    hand over: a coordinate field name is supplied, not discovered.
    """
    if convention is None:
        transmural, intraventricular, longitudinal = CANONICAL_FIELD_NAMES
        return {
            "transmural": f"{time_dir}/{transmural}",
            "intraventricular": f"{time_dir}/{intraventricular}",
            "longitudinal": f"{time_dir}/{longitudinal}",
        }
    return {
        role: convention.field_path(role, time_dir=time_dir)
        for role in ("transmural", "intraventricular", "longitudinal")
    }
