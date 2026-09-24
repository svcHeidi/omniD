"""The one place an ``omnidriver run`` child command is built.

Every command omnidriver spawns or advertises for another process to run --
a sweep's per-case ``run --run-document`` child, and the ``run --strict
--entry`` command a strict plan hands back to its caller -- must rebuild the
SAME provider stack the current process holds. A child process cannot
receive a ``DriverContext`` object, only the selector that rebuilds it, so
the command carries ``--plugin <DriverContext.plugin_selector>``. Without it
the child resolves the entry-point default, which is not the parent's stack
whenever the parent was given one explicitly, and which refuses outright when
two solver-tier adapters are installed.

A context with no selector (hand-built, or itself the default) gets no flag:
inventing one would be a guess. The run document's plugin identity check then
refuses a child whose default is a different stack.

Consolidated 2026-09-25 from three separately hand-built copies: the factory
sweep child (``sweep_runner._case_run_command``), the record sweep child, and
``strict_planning._run_launch_description`` -- the last two never carried
``--plugin`` at all.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


def omnidriver_run_command(driver_context: "DriverContext", *arguments: str) -> list[str]:
    """``python -m omnidriver run [--plugin <selector>] <arguments...>``."""
    command = [sys.executable, "-m", "omnidriver", "run"]
    if driver_context.plugin_selector is not None:
        command.extend(["--plugin", driver_context.plugin_selector])
    command.extend(arguments)
    return command
