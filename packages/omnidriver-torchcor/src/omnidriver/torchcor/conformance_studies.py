"""How ``omnidriver check`` exercises the N-version record briefly against the real TorchCor, on the CPU.

The brief run is 5 ms; the quantity runs to 60 ms, past P8 (about 40 ms at dx 0.5, G1)."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.conformance_study import ConformanceStudy, QuantityTarget

from .activation_reader import ACTIVATION_FORMAT

STUDIES: dict[str, ConformanceStudy] = {
    "nversion": ConformanceStudy(
        requires=("python3",),
        base_study={"case.json:t_end_ms": 5.0},
        patch=("case.json:chi_per_mm", 150),
        untouched=("case.json", ("cm_uF_per_mm2",)),
        sweep_name="case.json:dx_mm",
        sweep_values=(1.0, 0.5),
        unknown_name="case.json:chi_per_m",
        quantity=QuantityTarget(
            artifact_format=ACTIVATION_FORMAT, reference=Path("niederer2011.json"),
            # The slab's corners are geometry points of the box, so nodes at any dx (D4), and the
            # nearest-node reader samples them exactly. P9 is not a node at dx 0.5 (D4), so it is not compared.
            pairs={label: label for label in ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8")},
            at_unit=None, max_sampling_offset=0.0,
            study={"case.json:t_end_ms": 60.0}, sweep_values=(0.5, 0.25), tolerance=5.0, tolerance_unit="ms",
        ),
    ),
}
