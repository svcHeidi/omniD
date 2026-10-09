"""Activation times from the runner's ``out/activation_times.dat``, at the node nearest each supplied point.

The file is a node count, then ``x y z t`` per node in mm and ms, ``-1`` for a
node that never activated (docs/solver-learning/torchcor.md G1)."""
from __future__ import annotations

import math
from pathlib import Path

from omnidriver.core.quantities import RawSample, ReadRequest

ACTIVATION_FORMAT = "torchcor_activation_times"


def _read_nodes(path: Path) -> list[tuple[tuple[float, float, float], float]]:
    try:
        lines = [line.split() for line in path.read_text().splitlines() if line.strip()]
    except OSError as exc:
        raise ValueError(f"cannot read the activation times {path}: {exc}") from exc
    if not lines or len(lines[0]) != 1 or not lines[0][0].isdigit():
        raise ValueError(f"{path} does not start with a node count")
    nodes = []
    for number, row in enumerate(lines[1:], start=2):
        if len(row) != 4:
            raise ValueError(f"{path} line {number} has {len(row)} fields, expected x y z t")
        x, y, z, t = map(float, row)
        nodes.append(((x, y, z), t))
    if len(nodes) != int(lines[0][0]):
        raise ValueError(f"{path} declares {lines[0][0]} nodes but lists {len(nodes)}")
    return nodes


class NearestNodeReader:
    value_unit = "ms"
    sentinels = frozenset({-1.0})     # the runner's "never activated"
    sampling_rule = "nearest"         # the nearest node, the lowest index on a tie; core judges its distance
    coordinate_unit = "mm"
    takes_points = True

    def read(self, case_root: Path, artifact, request: ReadRequest) -> tuple[RawSample, ...]:
        nodes = _read_nodes(Path(case_root) / artifact.path_pattern)
        samples = []
        for name in request.names:
            point, value = min(nodes, key=lambda node: math.dist(node[0], request.points[name]))
            samples.append(RawSample(name=name, value=value, sampled_at=point))
        return tuple(samples)
