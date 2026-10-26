"""Where cardiacFoam's runtime evidence lives: the solver binary as a provenance input, and artifact readers."""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from omnidriver.core.plugin_interface import RuntimeDependency

from .command_authorization import solver_commands


def solver_dependencies(env: Mapping[str, str] | None = None) -> tuple[RuntimeDependency, ...]:
    """The solver binary on ``env``'s PATH (the process's by default), fingerprinted even when an ``Allrun`` step runs
    it; the libraries it links are its repository's build products (``get_solver_builds``)."""
    environment = os.environ if env is None else env
    found = {name: shutil.which(name, path=environment.get("PATH")) for name in sorted(solver_commands())}
    return tuple(
        RuntimeDependency(name=name, path=Path(path) if path else None, required=True) for name, path in found.items()
    )


def artifact_value_reader(artifact_format: str):
    """Reader for a solver-specific artifact format, or ``None``.

    Returning ``None`` must make that consumer report ``not_evaluated`` with
    a reason -- never an implicit pass.

    Returns :class:`~omnidriver.cardiacfoam.activation_probes.ActivationProbeReader`
    for ``ACTIVATION_PROBES_FORMAT``, the format ``niederer2011``'s
    ``samplePoints`` output declares."""
    from omnidriver.cardiacfoam.activation_probes import ACTIVATION_PROBES_FORMAT, ActivationProbeReader

    if artifact_format == ACTIVATION_PROBES_FORMAT:
        return ActivationProbeReader()
    return None
