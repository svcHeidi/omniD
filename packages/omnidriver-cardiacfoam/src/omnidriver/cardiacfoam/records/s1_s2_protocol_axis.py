"""The S1-S2 protocol axis: one mapping value that sets the stimulus keys and derives ``endTime`` and ``writeAfterTime``."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult

# The protocol is one mapping, not four axes: `endTime` and `writeAfterTime`
# derive from all four numbers together, and the axis must not read one back
# off the staged case. A sweep over `s2_interval_ms` varies the whole mapping.
_REQUIRED_KEYS = ("s1_interval_ms", "n_s1", "s2_interval_ms", "n_s2")

#: Start writing 2 s before the end of the S1 phase; end 2 s after the last S2.
_WRITE_AFTER_TIME_OFFSET_S = -2.0
_END_TIME_BUFFER_S = 2.0

_CONTROL_DICT_DOCUMENT = "system/controlDict"


def _require_protocol_keys(axis_name: str, protocol: Mapping[str, Any]) -> None:
    missing = [key for key in _REQUIRED_KEYS if key not in protocol]
    if missing:
        raise ValueError(
            f"S1-S2 protocol axis {axis_name!r}: the protocol mapping is "
            f"missing required key(s) {missing} (required: "
            f"{list(_REQUIRED_KEYS)}); got keys {sorted(protocol)}"
        )


def s1_s2_protocol_axis(
    name: str, *, electro_document: str, scope: tuple[str, ...],
) -> AxisContract:
    """Build a named axis mapping an S1-S2 protocol (a mapping of
    ``s1_interval_ms``/``n_s1``/``s2_interval_ms``/``n_s2``) to the
    ``singleCellStimulus`` keys it sets plus the derived
    ``system/controlDict:endTime`` and ``<scope>.writeAfterTime``.

    ``electro_document`` is the case-relative document the ``<solver>Coeffs``
    ``scope`` lives in. ``endTime`` is always written to
    ``system/controlDict``.

    Refuses by name a protocol mapping missing one of its four required keys.
    """

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        del staged_case_root  # this axis reads nothing from the staged case
        protocol = value
        _require_protocol_keys(name, protocol)
        s1_interval_ms = protocol["s1_interval_ms"]
        n_s1 = protocol["n_s1"]
        s2_interval_ms = protocol["s2_interval_ms"]
        n_s2 = protocol["n_s2"]

        write_after_time_s = (
            (s1_interval_ms * (n_s1 - 1)) / 1000.0 + _WRITE_AFTER_TIME_OFFSET_S
        )
        end_time_s = (
            (s1_interval_ms * (n_s1 - 1) + s2_interval_ms * n_s2) / 1000.0
            + _END_TIME_BUFFER_S
        )

        stimulus_scope = scope + ("singleCellStimulus",)
        patches = (
            AxisPatch(
                document=electro_document,
                key_path=stimulus_scope + ("stim_period_S1",),
                value=s1_interval_ms, value_kind="integer",
            ),
            AxisPatch(
                document=electro_document,
                key_path=stimulus_scope + ("nstim1",),
                value=n_s1, value_kind="integer",
            ),
            AxisPatch(
                document=electro_document,
                key_path=stimulus_scope + ("stim_period_S2",),
                value=s2_interval_ms, value_kind="integer",
            ),
            AxisPatch(
                document=electro_document,
                key_path=stimulus_scope + ("nstim2",),
                value=n_s2, value_kind="integer",
            ),
            AxisPatch(
                document=electro_document,
                key_path=scope + ("writeAfterTime",),
                value=write_after_time_s, value_kind="scalar",
            ),
            AxisPatch(
                document=_CONTROL_DICT_DOCUMENT,
                key_path=("endTime",),
                value=end_time_s, value_kind="scalar",
            ),
        )
        return AxisResult(patches=patches)

    return AxisContract(name=name, value_kind="mapping", resolve=resolve)
