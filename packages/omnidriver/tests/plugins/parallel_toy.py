"""A toy stack whose solver layer has a parallel form (PAR, 2026-09-26)."""
from __future__ import annotations

from plugins.e2e_record_plugin import E2ERecordPlugin

PARALLEL_TOY_PLUGIN = "plugins.parallel_toy:ParallelToyPlugin"


def toy_parallel_steps(step, *, request, read_value, allocation):
    if request is not True:
        raise ValueError(f"the toy reads its count from constant/mesh.json:cells; got request {request!r}")
    count = int(read_value("constant/mesh.json", ("cells",)))
    if allocation is not None and allocation.ranks != count:
        raise ValueError(
            f"{allocation.variable}={allocation.ranks} disagrees with constant/mesh.json:cells={count}"
        )
    step_id = step["id"]
    return (
        {"id": f"{step_id}.split", "command": "touch", "args": [f"split.{count}"],
         "depends_on": list(step["depends_on"])},
        {**step, "args": [*step["args"], f"ranks.{count}"], "depends_on": [f"{step_id}.split"]},
        {"id": f"{step_id}.join", "command": "touch", "args": ["joined.marker"], "depends_on": [step_id]},
    )


class ParallelToyPlugin(E2ERecordPlugin):
    def get_solve_step_commands(self):
        return frozenset({"touch"})

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        return toy_parallel_steps(step, request=request, read_value=read_value, allocation=allocation)
