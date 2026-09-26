"""The Niederer 2011 N-version benchmark, as openCARP ships it.

Native case: 02_EP_tissue/03E_study_resolution (nversion.par, singlecell.sv).
Its run.py builds the rest in Python. What this record takes from run.py,
each fact verified with the real binary (docs/solver-learning/opencarp.md):
- the slab: ``mesh.Block(size=(20, 7, 3), resolution=dx/1000,
  centre=(10, 3.5, 1.5))`` is ``mesher -size 2.0 0.7 0.3 -center 1.0 0.35
  0.15`` in cm, with resolution in µm (F3: extents 0-20000 x 0-7000 x
  0-3000 µm, fibres along x);
- ``-imp_region[0].im_sv_init singlecell.sv``, case-relative, because
  relative paths resolve against the working directory (F5), and every step
  runs in the staged case root;
- no physics-region options: outputs are byte-identical without them (F4).
``tend``, ``dt`` and ``mass_lumping`` are ordinary .par keys, so a study
names them as ``nversion.par:<key>`` (G5).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import (
    AxisContract, AxisResult, TutorialRecord, TutorialRecordError, WorkflowStep,
)


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

RECORD = TutorialRecord(
    name="niedererNVersion",
    native_case_relpath="02_EP_tissue/03E_study_resolution",
    allowed_axes=frozenset({"dx"}),
    workflow_steps=(
        WorkflowStep(
            step_id="mesh",
            command=("mesher", "-size[0]", "2.0", "-size[1]", "0.7", "-size[2]", "0.3",
                     "-center[0]", "1.0", "-center[1]", "0.35", "-center[2]", "0.15", "-mesh", "slab"),
            produces=("slab.pts", "slab.elem", "slab.lon", "slab.vec", "slab.vpts"),   # F15
        ),
        WorkflowStep(
            step_id="solve",
            command=("openCARP", "+F", "nversion.par", "-meshname", "slab", "-simID", "out",
                     "-imp_region[0].im_sv_init", "singlecell.sv"),
            consumes=("nversion.par", "singlecell.sv"),
            produces=("out", "out/vm.igb", "out/init_acts_vm_act-thresh.dat"),   # F6; the whole -simID directory: F15
        ),
    ),
)
