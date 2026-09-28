"""The Niederer 2011 N-version benchmark, as openCARP ships it.

Native case: 02_EP_tissue/03E_study_resolution (nversion.par, singlecell.sv), whose run.py builds the mesh and stimulus in Python; what this record takes from run.py is verified against the real binary -- see docs/solver-learning/opencarp.md."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import (
    AxisContract, AxisResult, ProducedPath, TutorialRecord, TutorialRecordError, WorkflowStep,
)

from ..lat_reader import LAT_FORMAT


def _dx_resolution(value: Any, staged_case_root: Path) -> AxisResult:
    del staged_case_root
    dx = float(value)
    if not math.isfinite(dx) or dx <= 0:
        raise TutorialRecordError(f"dx must be a positive length in µm, got {value!r}")
    text = repr(dx)
    return AxisResult(command_arguments={
        "mesh": ("-resolution[0]", text, "-resolution[1]", text, "-resolution[2]", text),
    })


DX_AXIS = AxisContract(name="dx", value_kind="scalar", resolve=_dx_resolution)

# tend, dt and mass_lumping are ordinary nversion.par keys, so a study names
# them directly as nversion.par:<key> rather than through an axis.
RECORD = TutorialRecord(
    name="niedererNVersion",
    native_case_relpath="02_EP_tissue/03E_study_resolution",
    axes=(DX_AXIS,),
    workflow_steps=(
        WorkflowStep(
            step_id="mesh",
            # run.py's mesh.Block(size=(20, 7, 3), centre=(10, 3.5, 1.5)), in
            # cm here: slab extents 0-20000 x 0-7000 x 0-3000 um, fibres along x.
            command=("mesher", "-size[0]", "2.0", "-size[1]", "0.7", "-size[2]", "0.3",
                     "-center[0]", "1.0", "-center[1]", "0.35", "-center[2]", "0.15", "-mesh", "slab"),
            produces=("slab.pts", "slab.elem", "slab.lon", "slab.vec", "slab.vpts"),
        ),
        WorkflowStep(
            step_id="solve",
            # No physics-region options: outputs are byte-identical without
            # them. singlecell.sv resolves against the staged case root,
            # every step's working directory.
            command=("openCARP", "+F", "nversion.par", "-meshname", "slab", "-simID", "out",
                     "-imp_region[0].im_sv_init", "singlecell.sv"),
            consumes=("nversion.par", "singlecell.sv"),
            produces=("out", "out/vm.igb", ProducedPath("out/init_acts_vm_act-thresh.dat", format=LAT_FORMAT)),   # "out" is the whole -simID directory; the LAT file feeds LatPerNodeReader
        ),
    ),
)
