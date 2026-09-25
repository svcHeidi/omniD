"""The S1-S2 protocol axis (design doc
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``,
step 4b -- the pilot, ``restitutionCurves``).

The owner's own instruction for this axis: "a mapping value (the protocol's
parameters) gives the singleCellStimulus keys it sets plus the derived
``system/controlDict:endTime`` and ``writeAfterTime``, using the old
module's arithmetic, not new formulas. An axis must not silently read case
values that the same study could also patch directly; take the protocol as
the axis value."

**Why the whole protocol is ONE mapping value, not four separate axes/keys.**
``stim_period_S2``/``nstim2`` (the two S2 keys) could each be named directly
by a study, the same way ``tissue`` is (design's own direct-key exception) --
but ``endTime``/``writeAfterTime`` are DERIVED from all four numbers
together (``s1_interval_ms``, ``n_s1``, ``s2_interval_ms``, ``n_s2``), and an
axis is not allowed to read ``s2_interval_ms`` back off the staged case if a
study set it as a separate direct key (design's own "must not silently read
case values the same study could also patch directly") -- the ONLY way this
axis can compute ``endTime``/``writeAfterTime`` without that back door is to
require every number it needs as part of its own single study value. A
sweep that varies ``s2_interval_ms`` per case therefore varies the WHOLE
protocol mapping per case (each of a sweep's ``independent`` values is one
complete protocol dict) -- more verbose per case than a bare
``s2_interval_ms`` list, but it is the one honest way to keep this axis pure
and self-contained.

**The old module's arithmetic, reproduced exactly, not re-derived**
(``cardiacfoam.tutorials.restitution_curves`` -- deleted alongside this
pilot once parity against the real native case was proven; see this
package's parity evidence for that proof)::

    write_after_time_s = (s1_interval_ms * (n_s1 - 1)) / 1000.0 - 2.0
    end_time = (
        (s1_interval_ms * (n_s1 - 1) + s2_interval_ms * n_s2) / 1000.0
        + 2.0  # end_time_buffer_s -- a `make_spec` parameter in the old
               # module, but never varied by any real study (native
               # driver_config.json included), so kept a literal here per
               # the owner's "old module's arithmetic, not new formulas"
    )

Both magic constants (``-2.0``, the "start writing 2s before the end of the
S1 phase" offset; ``+2.0``, ``end_time_buffer_s``) are the old module's own
literals, not something this axis makes newly configurable -- doing that
would be a new formula, which the owner's instruction explicitly excludes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.tutorial_records import AxisContract, AxisPatch, AxisResult

_REQUIRED_KEYS = ("s1_interval_ms", "n_s1", "s2_interval_ms", "n_s2")

#: The old module's own literals (module docstring has the full reasoning);
#: kept exactly, not exposed as new axis parameters.
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
    ``scope`` lives in (``restitutionCurves`` uses
    ``"constant/electroProperties"``/``("singleCellSolverCoeffs",)``, the
    same as :func:`omnidriver.cardiacfoam.records.ionic_model_axis
    .ionic_model_axis`'s own parameters for the same tutorial).
    ``endTime`` is always written to ``system/controlDict`` -- OpenFOAM's
    own document, not this tutorial's -- so it is not parameterised by
    ``electro_document``.

    The axis declares ``value_kind="mapping"`` -- checked by
    ``tutorial_records.resolve_case_patches`` before ``resolve`` ever runs,
    so a non-mapping study value (a list, a bare number) is refused by
    core's own generic shape check before reaching this module's code.

    Refuses by name: the protocol mapping is missing one of its four
    required keys (module-level ``_REQUIRED_KEYS``).
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
